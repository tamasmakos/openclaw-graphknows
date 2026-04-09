"""
Hybrid retriever — ChromaDB seeds → wikilink/KG graph expansion → PageRank rerank.
Pure Python PageRank (no networkx dep).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .config import (
    DEFAULT_K,
    NEIGHBOR_SCORE_DECAY,
    PAGERANK_DAMPING,
    PAGERANK_ITERATIONS,
    PAGERANK_WEIGHT,
    SEMANTIC_WEIGHT,
)

if TYPE_CHECKING:
    from .knowledge_graph import KnowledgeGraph
    from .vector_store import VectorStore


# ── PageRank (inline, no networkx) ───────────────────────────────────────────

def compute_pagerank(
    adjacency: dict[str, list[str]],
    damping: float = PAGERANK_DAMPING,
    iterations: int = PAGERANK_ITERATIONS,
) -> dict[str, float]:
    """
    Compute PageRank over an adjacency dict {node: [neighbor, ...]}.
    Returns {node: score}.
    """
    nodes = set(adjacency.keys())
    for neighbors in adjacency.values():
        nodes.update(neighbors)
    nodes = list(nodes)
    n = len(nodes)
    if n == 0:
        return {}

    idx = {node: i for i, node in enumerate(nodes)}
    # Build reverse adjacency for incoming links
    in_links: dict[int, list[int]] = {i: [] for i in range(n)}
    for node, neighbors in adjacency.items():
        ni = idx[node]
        for nb in neighbors:
            if nb in idx:
                in_links[idx[nb]].append(ni)

    out_degree = [len(adjacency.get(node, [])) for node in nodes]
    scores = [1.0 / n] * n

    for _ in range(iterations):
        new_scores = [(1.0 - damping) / n] * n
        for i in range(n):
            for j in in_links[i]:
                od = out_degree[j]
                if od:
                    new_scores[i] += damping * scores[j] / od
        scores = new_scores

    return {nodes[i]: scores[i] for i in range(n)}


# ── Retriever ─────────────────────────────────────────────────────────────────

class Retriever:
    def __init__(self, vector_store: "VectorStore", kg: "KnowledgeGraph"):
        self._vs = vector_store
        self._kg = kg
        self._pagerank_cache: dict | None = None
        self._wikilink_graph: dict | None = None

    def _build_wikilink_graph(self, all_metadata: list[dict]) -> dict[str, list[str]]:
        """Build adjacency dict from wikilink metadata stored in ChromaDB."""
        graph: dict[str, list[str]] = {}
        for item in all_metadata:
            stem = item.get("room", item.get("path", ""))
            links_raw = item.get("wikilinks", "")
            links = links_raw.split("||") if links_raw else []
            graph[stem] = [l for l in links if l]
        return graph

    def _get_pagerank(self) -> dict[str, float]:
        if self._pagerank_cache is None:
            meta = self._vs.get_all_metadata()
            graph = self._build_wikilink_graph(meta)
            self._pagerank_cache = compute_pagerank(graph)
        return self._pagerank_cache

    def invalidate_cache(self) -> None:
        self._pagerank_cache = None
        self._wikilink_graph = None

    def search(
        self,
        query: str,
        k: int = DEFAULT_K,
        project: str | None = None,
    ) -> list[dict]:
        """
        Hybrid search:
        1. Semantic seeds from ChromaDB (vector similarity).
        2. Graph expansion via wikilinks + KG relations.
        3. PageRank rerank.

        Returns list of {id, content, metadata, score, source}.
        """
        where = {"project": project} if project else None
        seeds = self._vs.query(query, k=k * 2, where=where)
        if not seeds:
            return []

        pr = self._get_pagerank()
        all_meta = self._vs.get_all_metadata()

        # Index all notes by room stem for graph expansion
        room_index: dict[str, dict] = {}
        for item in all_meta:
            room = item.get("room", "")
            if room:
                room_index[room.lower()] = item

        scored: dict[str, dict] = {}

        # Score seeds
        for seed in seeds:
            room = seed["metadata"].get("room", "")
            sem_score = seed["score"]
            pr_score = pr.get(room, pr.get(room.lower(), 0.0))
            final = sem_score * SEMANTIC_WEIGHT + pr_score * PAGERANK_WEIGHT
            scored[seed["id"]] = {**seed, "score": final, "source": "semantic"}

        # 1-hop wikilink expansion
        for seed in seeds[:k]:  # expand from top seeds only
            room = seed["metadata"].get("room", "")
            links_raw = seed["metadata"].get("wikilinks", "")
            links = links_raw.split("||") if links_raw else []
            for link in links:
                neighbor = room_index.get(link.lower())
                if neighbor and neighbor.get("id") not in scored:
                    nb_id = neighbor.get("id", "")
                    nb_room = neighbor.get("room", "")
                    nb_pr = pr.get(nb_room, 0.0)
                    nb_score = seed["score"] * NEIGHBOR_SCORE_DECAY + nb_pr * PAGERANK_WEIGHT
                    scored[nb_id] = {
                        "id": nb_id,
                        "content": neighbor.get("content", ""),
                        "metadata": neighbor,
                        "score": nb_score,
                        "source": "wikilink_expansion",
                    }

        # Sort and return top k
        ranked = sorted(scored.values(), key=lambda x: x["score"], reverse=True)
        return ranked[:k]

    def layer2_filter(self, project: str, room: str | None = None) -> list[dict]:
        """
        L2 — fast metadata filter, no embedding. Returns notes for a project/room.
        """
        where: dict = {"project": project}
        if room:
            where["room"] = room
        return self._vs.get_all_metadata()  # filtered client-side (simple for small vaults)

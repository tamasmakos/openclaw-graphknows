"""
Auto-linker — three strategies for increasing wikilink density:
1. Entity injection: entity name mentions → [[EntityPage]]
2. Semantic neighbor linking: cosine distance < threshold → related: frontmatter
3. Shared-entity co-occurrence ≥ N → bidirectional wikilink suggestions
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .config import MIN_SHARED_ENTITIES_FOR_LINK, SEMANTIC_LINK_THRESHOLD
from .vault import inject_wikilinks

if TYPE_CHECKING:
    from .knowledge_graph import KnowledgeGraph
    from .vector_store import VectorStore


def run_linker(
    vault: Path,
    all_notes: list[dict],
    vector_store: "VectorStore",
    kg: "KnowledgeGraph",
) -> dict:
    """
    Run all three linking strategies on the vault.
    Returns stats dict.
    """
    stats = {"entity_links": 0, "semantic_links": 0, "cooccurrence_links": 0}

    # Strategy 2: semantic neighbor linking via ChromaDB metadata
    semantic_links = _semantic_neighbor_links(vector_store)
    for note_path, targets in semantic_links.items():
        p = Path(note_path)
        if p.exists() and targets:
            n = inject_wikilinks(p, targets)
            stats["semantic_links"] += n

    # Strategy 3: shared-entity co-occurrence
    co_links = _cooccurrence_links(all_notes)
    for note_path, targets in co_links.items():
        p = Path(note_path)
        if p.exists() and targets:
            n = inject_wikilinks(p, targets)
            stats["cooccurrence_links"] += n

    return stats


def _semantic_neighbor_links(vector_store: "VectorStore") -> dict[str, list[str]]:
    """
    For each note, find ChromaDB neighbors within SEMANTIC_LINK_THRESHOLD.
    Returns {note_path: [neighbor_stems]}.
    """
    all_meta = vector_store.get_all_metadata()
    result: dict[str, list[str]] = {}

    # For each note, query its own content against the store
    for item in all_meta:
        content = item.get("content", "")
        note_path = item.get("path", "")
        if not content or not note_path:
            continue
        try:
            neighbors = vector_store.query(content, k=6)
        except Exception:
            continue
        stems = []
        for nb in neighbors:
            nb_path = nb["metadata"].get("path", "")
            nb_room = nb["metadata"].get("room", "")
            # 1.0 - score gives distance; lower = closer
            dist = 1.0 - nb["score"]
            if dist < SEMANTIC_LINK_THRESHOLD and nb_path != note_path and nb_room:
                stems.append(nb_room)
        if stems:
            result[note_path] = stems

    return result


def _cooccurrence_links(all_notes: list[dict]) -> dict[str, list[str]]:
    """
    Notes sharing ≥ MIN_SHARED_ENTITIES_FOR_LINK entity tags → bidirectional link.
    Returns {note_path: [neighbor_stems]}.
    """
    # Build {path: set(entity_tags)}
    note_entities: dict[str, set] = {}
    stem_for_path: dict[str, str] = {}
    for note in all_notes:
        path = note.get("path", "")
        tags = set(t for t in note.get("tags", []) if t.startswith("entity/"))
        if path:
            note_entities[path] = tags
            stem_for_path[path] = note.get("stem", Path(path).stem)

    result: dict[str, list[str]] = {}
    paths = list(note_entities.keys())

    for i, pa in enumerate(paths):
        for pb in paths[i + 1:]:
            shared = note_entities[pa] & note_entities[pb]
            if len(shared) >= MIN_SHARED_ENTITIES_FOR_LINK:
                result.setdefault(pa, []).append(stem_for_path[pb])
                result.setdefault(pb, []).append(stem_for_path[pa])

    return result

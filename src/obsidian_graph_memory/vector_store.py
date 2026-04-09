"""ChromaDB vector store with Gemini embeddings."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Optional

from .config import EMBEDDING_DIM, EMBEDDING_MODEL

# ── Gemini embedding function for ChromaDB ────────────────────────────────────

class GeminiEmbeddingFunction:
    """Custom ChromaDB embedding function using Gemini text-embedding-004 (google.genai SDK)."""

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            import google.genai as genai
            api_key = (
                os.environ.get("GOOGLE_API_KEY")
                or os.environ.get("GEMINI_API_KEY")
                or os.environ.get("GOOGLE_GENERATIVEAI_API_KEY")
            )
            if not api_key:
                raise RuntimeError(
                    "Set GOOGLE_API_KEY or GEMINI_API_KEY environment variable for Gemini embeddings."
                )
            self._client = genai.Client(api_key=api_key)
        return self._client

    def __call__(self, input: list[str]) -> list[list[float]]:
        import google.genai as genai
        client = self._get_client()
        results = []
        # Gemini batch limit: 100 texts per call
        for i in range(0, len(input), 100):
            batch = input[i : i + 100]
            response = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=batch,
                config=genai.types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
            )
            for emb in response.embeddings:
                results.append(emb.values)
        return results

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query string for retrieval."""
        import google.genai as genai
        client = self._get_client()
        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=[query],
            config=genai.types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
        )
        return response.embeddings[0].values


# ── deterministic drawer ID ───────────────────────────────────────────────────

def drawer_id(project: str, room: str, content: str) -> str:
    raw = f"{project}::{room}::{content[:100]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ── VectorStore ───────────────────────────────────────────────────────────────

class VectorStore:
    COLLECTION_NAME = "obsidian_notes"

    def __init__(self, artifact_dir: Path):
        self._artifact_dir = artifact_dir
        self._chroma_dir = artifact_dir / "chroma"
        self._chroma_dir.mkdir(parents=True, exist_ok=True)
        self._client = None
        self._collection = None
        self._embed_fn = GeminiEmbeddingFunction()

    def _get_collection(self):
        if self._collection is None:
            import chromadb
            self._client = chromadb.PersistentClient(path=str(self._chroma_dir))
            self._collection = self._client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                # We supply embeddings ourselves so no default fn needed
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def upsert_note(
        self,
        path: str,
        content: str,
        project: str,
        room: str,
        metadata: dict | None = None,
    ) -> str:
        """Embed and upsert a note chunk. Returns drawer ID."""
        col = self._get_collection()
        did = drawer_id(project, room, content)
        embedding = self._embed_fn([content])[0]
        meta = {
            "path": path,
            "project": project,
            "room": room,
            **(metadata or {}),
        }
        # Remove None values (ChromaDB doesn't accept them)
        meta = {k: v for k, v in meta.items() if v is not None}
        col.upsert(
            ids=[did],
            embeddings=[embedding],
            documents=[content],
            metadatas=[meta],
        )
        return did

    def query(
        self,
        query_text: str,
        k: int = 10,
        where: dict | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search. Returns list of {id, content, metadata, score}."""
        col = self._get_collection()
        embedding = self._embed_fn.embed_query(query_text)
        kwargs: dict = {"query_embeddings": [embedding], "n_results": min(k, max(1, col.count()))}
        if where:
            kwargs["where"] = where
        results = col.query(**kwargs)
        output = []
        for i, (did, doc, meta, dist) in enumerate(zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )):
            output.append({
                "id": did,
                "content": doc,
                "metadata": meta,
                "score": 1.0 - dist,  # cosine distance → similarity
            })
        return output

    def get_all_metadata(self) -> list[dict]:
        """Fetch all metadata for graph construction (no embeddings)."""
        col = self._get_collection()
        total = col.count()
        if total == 0:
            return []
        result = col.get(include=["metadatas", "documents"])
        return [
            {"id": did, "content": doc, **meta}
            for did, doc, meta in zip(result["ids"], result["documents"], result["metadatas"])
        ]

    def count(self) -> int:
        return self._get_collection().count()

    def delete(self, drawer_id: str) -> None:
        self._get_collection().delete(ids=[drawer_id])

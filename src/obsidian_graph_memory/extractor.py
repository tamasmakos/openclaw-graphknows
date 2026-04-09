"""GLiNER2-based entity + relation + chunk_type extraction."""
from __future__ import annotations

import re
from typing import Any

from .config import CHUNK_TYPES, ENTITY_LABELS, EXTRACTOR_MODEL, RELATION_LABELS

# ── regex pre-filter (avoid loading model for trivial notes) ──────────────────
_TRIVIAL_RE = re.compile(
    r"^(---\s*\n.*?\n---\s*\n)?\s*$", re.DOTALL
)
_MIN_WORDS = 10


def _is_trivial(text: str) -> bool:
    words = text.split()
    return len(words) < _MIN_WORDS


# ── singleton model ────────────────────────────────────────────────────────────
_model = None


def _get_model():
    global _model
    if _model is None:
        try:
            from gliner2 import GLiNER2
            _model = GLiNER2.from_pretrained(EXTRACTOR_MODEL)
        except Exception as e:
            raise RuntimeError(
                f"Failed to load GLiNER2 model '{EXTRACTOR_MODEL}'. "
                f"Run: pip install gliner2\nError: {e}"
            ) from e
    return _model


# ── public API ────────────────────────────────────────────────────────────────

def extract_note(text: str, title: str = "") -> dict[str, Any]:
    """
    Full multi-task extraction from a note's plain text.

    Returns:
        {
            "entities": [{"name": str, "type": str}],
            "relations": [{"subject": str, "predicate": str, "object": str}],
            "chunk_type": str,
            "trivial": bool,
        }
    """
    if _is_trivial(text):
        return {"entities": [], "relations": [], "chunk_type": "context", "trivial": True}

    # Truncate to ~2000 chars to keep GLiNER2 memory usage bounded per note
    MAX_CHARS = 2000
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]

    model = _get_model()

    # Build multi-task schema
    schema = (
        model.create_schema()
        .entities(ENTITY_LABELS)
        .classification("chunk_type", CHUNK_TYPES)
        .relations(RELATION_LABELS)
    )

    combined = f"{title}\n\n{text}" if title else text
    try:
        raw = model.extract(combined, schema)
    except Exception:
        # Fallback: entities only
        try:
            raw = {"entities": model.extract_entities(combined, list(ENTITY_LABELS.keys()))}
        except Exception:
            return {"entities": [], "relations": [], "chunk_type": "context", "trivial": False}
    finally:
        # Free torch intermediate tensors to avoid OOM during bulk ingestion
        try:
            import gc
            gc.collect()
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    entities = _parse_entities(raw.get("entities", {}))
    relations = _parse_relations(raw.get("relation_extraction", {}))
    chunk_type = raw.get("chunk_type", "context")
    if isinstance(chunk_type, dict):
        chunk_type = chunk_type.get("label", "context")

    return {
        "entities": entities,
        "relations": relations,
        "chunk_type": chunk_type,
        "trivial": False,
    }


def batch_extract(texts: list[str], titles: list[str] | None = None) -> list[dict]:
    """Extract from multiple notes. Returns list of extract_note results."""
    titles = titles or [""] * len(texts)
    return [extract_note(t, ti) for t, ti in zip(texts, titles)]


# ── parsers ───────────────────────────────────────────────────────────────────

def _parse_entities(raw: dict | list) -> list[dict]:
    """Normalise GLiNER2 entity output to [{name, type}]."""
    result = []
    if isinstance(raw, dict):
        for etype, items in raw.items():
            for item in items:
                if isinstance(item, dict):
                    name = item.get("text", "")
                else:
                    name = str(item)
                if name:
                    result.append({"name": name, "type": etype})
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                result.append({"name": item.get("text", ""), "type": item.get("label", "entity")})
    return [e for e in result if e["name"]]


def _parse_relations(raw: dict) -> list[dict]:
    """Normalise GLiNER2 relation output to [{subject, predicate, object}]."""
    result = []
    if not isinstance(raw, dict):
        return result
    for predicate, pairs in raw.items():
        if isinstance(pairs, list):
            for pair in pairs:
                if isinstance(pair, tuple) and len(pair) == 2:
                    result.append({
                        "subject": str(pair[0]),
                        "predicate": predicate,
                        "object": str(pair[1]),
                    })
                elif isinstance(pair, dict):
                    head = pair.get("head", {})
                    tail = pair.get("tail", {})
                    subj = head.get("text", head) if isinstance(head, dict) else str(head)
                    obj = tail.get("text", tail) if isinstance(tail, dict) else str(tail)
                    if subj and obj:
                        result.append({"subject": subj, "predicate": predicate, "object": obj})
    return result

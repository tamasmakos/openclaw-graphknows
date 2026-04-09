"""
FastMCP server — stdio transport.
Run: python -m obsidian_graph_memory.server
Or:  obsidian-memory-server
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .palace import MemoryPalace

# ── server setup ──────────────────────────────────────────────────────────────
mcp = FastMCP(
    name="obsidian-memory",
    instructions=(
        "Graph-enriched Obsidian memory for OpenClaw agents. "
        "ALWAYS call memory_status(agent_name) at session start. "
        "Use memory_query before researching any topic. "
        "Use memory_remember to capture decisions and insights. "
        "ALWAYS call memory_session_end before closing."
    ),
)

_palace: MemoryPalace | None = None


def _get_palace() -> MemoryPalace:
    global _palace
    if _palace is None:
        vault_path = os.environ.get("OPENCLAW_OBSIDIAN_VAULT")
        if vault_path:
            _palace = MemoryPalace(vault=Path(vault_path))
        else:
            _palace = MemoryPalace()
    return _palace


# ── tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def memory_status(agent_name: str) -> dict[str, Any]:
    """
    Session start briefing — call this FIRST every session.
    Returns L0+L1 context: who you are, recent sessions, top entities, and the memory protocol.
    Injecting OPENCLAW_MEMORY_PROTOCOL tells you how to use this memory system.
    """
    return _get_palace().memory_status(agent_name)


@mcp.tool()
def memory_query(query: str, project: str = "", k: int = 10) -> dict[str, Any]:
    """
    Hybrid semantic + graph search over the shared vault.
    Returns XML context with relevant notes, entities, and relationships.
    Call this BEFORE researching any topic to avoid duplicating known work.

    Args:
        query: What you want to find or know about.
        project: Optional — limit search to a specific project folder.
        k: Number of results (default 10).
    """
    return _get_palace().memory_query(query, project=project or None, k=k)


@mcp.tool()
def memory_remember(
    title: str,
    content: str,
    project: str,
    room: str = "",
    chunk_type: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """
    Write a note to the shared Obsidian vault. Entities are auto-extracted and added to the KG.
    Returns the note path, extracted entities, and tags written to frontmatter.

    Args:
        title: Note title (becomes filename stem).
        content: Note body — be specific, include the WHY not just the WHAT.
        project: Project/workspace this belongs to (e.g. "chessdev", "chessgnn").
        room: Optional sub-topic slug (defaults to title).
        chunk_type: One of: decision, preference, milestone, problem, insight, context, question.
        tags: Additional tags (entity tags are added automatically).
    """
    return _get_palace().memory_remember(
        title=title,
        content=content,
        project=project,
        room=room or None,
        chunk_type=chunk_type or None,
        tags=tags,
    )


@mcp.tool()
def memory_kg_add(
    subject: str,
    predicate: str,
    object: str,
    valid_from: str = "",
    confidence: float = 1.0,
) -> dict[str, Any]:
    """
    Add a fact to the knowledge graph: subject →[predicate]→ object.
    Facts are temporal — set valid_from as ISO date (YYYY-MM-DD).
    Example: memory_kg_add("Forge", "works_on", "chessgnn")

    Args:
        subject: Entity name (person, project, concept).
        predicate: Relationship type (works_on, uses, solved_by, depends_on, related_to).
        object: Target entity name.
        valid_from: ISO date when this became true (defaults to today).
        confidence: Confidence score 0.0–1.0 (default 1.0).
    """
    return _get_palace().memory_kg_add(
        subject=subject,
        predicate=predicate,
        obj=object,
        valid_from=valid_from or None,
        confidence=confidence,
    )


@mcp.tool()
def memory_kg_query(entity: str, as_of: str = "") -> dict[str, Any]:
    """
    Query all known facts about an entity from the knowledge graph.
    Supports time-travel: set as_of (ISO date) to query what was true at that date.

    Args:
        entity: Entity name to look up.
        as_of: Optional ISO date for time-travel queries (e.g. "2026-01-01").
    """
    return _get_palace().memory_kg_query(entity, as_of=as_of or None)


@mcp.tool()
def memory_session_end(agent_name: str, summary: str) -> dict[str, Any]:
    """
    Write session log and flush diary. REQUIRED — call before every session close.
    The summary is embedded in the vault and searchable in future sessions.

    Args:
        agent_name: Your agent identifier (e.g. "forge", "vector", "zoe").
        summary: What happened this session — decisions made, progress, open questions.
    """
    return _get_palace().memory_session_end(agent_name, summary)


@mcp.tool()
def memory_memorize(
    query: str = "",
    paths: list[str] | None = None,
    project: str = "",
    limit: int = 10,
) -> dict[str, Any]:
    """
    Turn existing vault notes into enriched memories.

    Runs GLiNER2 entity extraction on chosen notes, writes entity tags into their
    frontmatter, and adds extracted entities + relationships to the knowledge graph.
    Use this to retroactively enrich notes that were ingested without extraction,
    or to process a specific set of notes by query or path.

    Modes:
    - By semantic search: set `query` to find the most relevant notes.
    - By explicit paths: set `paths` to a list of absolute note paths.
    - By un-tagged notes: leave both empty; processes notes with no entity tags yet.

    Args:
        query: Semantic search to find which existing notes to enrich.
        paths: Explicit list of absolute vault note paths to process.
        project: Limit to notes from a specific project folder.
        limit: Max notes to process in one call (default 10, max 50).
    """
    return _get_palace().memorize(
        query=query or None,
        paths=paths,
        project=project or None,
        limit=limit,
    )


# ── entry point ────────────────────────────────────────────────────────────────

def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

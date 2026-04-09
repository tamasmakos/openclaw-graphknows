"""
MemoryPalace — the main façade that ties all components together.
Used by the MCP server and CLI.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from .config import get_artifact_dir, get_vault_path, sanitize_content, sanitize_name
from .context import build_context, build_session_briefing
from .extractor import extract_note
from .knowledge_graph import KnowledgeGraph
from .retriever import Retriever
from .vault import (
    create_note,
    inject_entity_tags,
    read_note,
    walk_vault,
)
from .vector_store import VectorStore
from .wal import WAL

# ── OPENCLAW_MEMORY_PROTOCOL — injected on first memory_status call ───────────
OPENCLAW_MEMORY_PROTOCOL = """
== OPENCLAW MEMORY PROTOCOL ==

You are equipped with structured graph memory. Follow this protocol every session:

1. SESSION START — Call `memory_status(agent_name)` immediately. This briefing is your context.
2. QUERY FIRST — Before researching any topic, call `memory_query(query)`. Check what's known.
3. REMEMBER — Capture decisions, insights, blockers, and entities with `memory_remember(...)`.
   Good notes include: what you decided, why, what you learned, what's still unknown.
   Use project= to organise notes by project/workspace.
4. KG FACTS — For important facts (X uses Y, X solved Z), also call `memory_kg_add(...)`.
5. SESSION END — Always call `memory_session_end(agent_name, summary)` before closing.
   This writes the session log and is required. Do not skip it.

Obsidian note quality standards:
- Use [[wikilinks]] to reference other notes and entities
- Use frontmatter tags: tags: [entity/person/name, project/x, technology/y]
- Be specific: "Decided to use FalkorDB because pgvector was too slow for graph traversal"
  not "discussed database options"
- Capture the WHY, not just the WHAT

== END PROTOCOL ==
""".strip()


class MemoryPalace:
    """Main façade — initialised with a vault path."""

    def __init__(self, vault: Path | None = None):
        self.vault = vault or get_vault_path()
        self.artifact_dir = get_artifact_dir(self.vault)
        self.vs = VectorStore(self.artifact_dir)
        self.kg = KnowledgeGraph(self.artifact_dir)
        self.wal = WAL(self.artifact_dir)
        self.retriever = Retriever(self.vs, self.kg)

    # ── ingest ────────────────────────────────────────────────────────────────

    def ingest(self, project: str | None = None, extract_entities: bool = True) -> dict:
        """
        Scan vault, embed all notes into ChromaDB, extract entities into KG.
        If project is given, only ingest that project subfolder.
        """
        base = self.vault / project if project else self.vault
        notes = list(walk_vault(base))
        ingested = 0
        extracted = 0
        errors = []

        for note_path in notes:
            try:
                note = read_note(note_path)
                proj = _path_to_project(note_path, self.vault)
                room = note_path.stem

                # Store in ChromaDB with metadata
                wikilinks_str = "||".join(note["wikilinks"])
                tags_str = "||".join(note["tags"])
                self.vs.upsert_note(
                    path=str(note_path),
                    content=note["plain_text"] or note["body"],
                    project=proj,
                    room=room,
                    metadata={
                        "title": note["title"],
                        "wikilinks": wikilinks_str,
                        "tags": tags_str,
                        "chunk_type": note["frontmatter"].get("chunk_type", ""),
                    },
                )
                ingested += 1

                if extract_entities and note["plain_text"]:
                    result = extract_note(note["plain_text"], note["title"])
                    if not result["trivial"]:
                        # Write entity tags back to frontmatter
                        inject_entity_tags(note_path, result["entities"])
                        # Add entities + relations to KG
                        self.kg.add_entities(result["entities"])
                        self.kg.add_triples_from_extraction(
                            result["relations"], source_note=str(note_path)
                        )
                        # Update chunk_type in frontmatter if missing
                        if not note["frontmatter"].get("chunk_type"):
                            from .vault import write_note_frontmatter
                            write_note_frontmatter(note_path, {"chunk_type": result["chunk_type"]})
                        extracted += 1

            except Exception as e:
                errors.append({"path": str(note_path), "error": str(e)})

        self.retriever.invalidate_cache()
        self.wal.log("ingest", {"notes": ingested, "extracted": extracted, "errors": len(errors)})

        return {"ingested": ingested, "extracted": extracted, "errors": errors}

    # ── memorize ──────────────────────────────────────────────────────────────

    def memorize(
        self,
        query: str | None = None,
        paths: list[str] | None = None,
        project: str | None = None,
        limit: int = 10,
    ) -> dict:
        """
        Turn existing vault notes into enriched memories.

        Finds notes via semantic search (query), explicit paths, or all un-extracted
        notes in a project, then runs GLiNER2 entity extraction on each one,
        updates frontmatter tags, and adds entities + triples to the KG.

        Args:
            query: Semantic search to find which notes to process.
            paths: Explicit list of absolute note paths to process.
            project: Limit to notes from a specific project folder.
            limit: Max notes to process in one call (default 10, cap 50).
        """
        import gc

        limit = min(max(1, limit), 50)
        processed = []
        errors = []

        # --- Resolve which notes to process ---
        if paths:
            # Explicit paths take priority
            candidates = [Path(p) for p in paths if Path(p).exists()]
        elif query:
            # Semantic search to find relevant notes
            where = {"project": project} if project else None
            hits = self.vs.query(query, k=limit, where=where)
            candidates = [Path(h["metadata"]["path"]) for h in hits if "path" in h["metadata"]]
        else:
            # No query: find notes that have no entity tags yet
            all_meta = self.vs.get_all_metadata()
            if project:
                all_meta = [m for m in all_meta if m.get("project") == project]
            candidates = [
                Path(m["path"])
                for m in all_meta
                if not m.get("tags", "").startswith("entity/")
            ][:limit]

        # --- Process each note ---
        for note_path in candidates[:limit]:
            if not note_path.exists():
                errors.append({"path": str(note_path), "error": "file not found"})
                continue
            try:
                note = read_note(note_path)
                text = note["plain_text"] or note["body"]
                if not text.strip():
                    continue

                result = extract_note(text, note["title"])

                if not result["trivial"]:
                    # Write entity tags to frontmatter
                    new_tags = inject_entity_tags(note_path, result["entities"])
                    # Add to KG
                    self.kg.add_entities(result["entities"])
                    triple_count = self.kg.add_triples_from_extraction(
                        result["relations"], source_note=str(note_path)
                    )
                    # Update chunk_type if missing
                    if not note["frontmatter"].get("chunk_type") and result["chunk_type"]:
                        from .vault import write_note_frontmatter
                        write_note_frontmatter(note_path, {"chunk_type": result["chunk_type"]})

                    processed.append({
                        "path": str(note_path),
                        "title": note["title"],
                        "entities": result["entities"],
                        "entity_count": len(result["entities"]),
                        "triples_added": triple_count,
                        "chunk_type": result["chunk_type"],
                        "tags_written": new_tags,
                    })

                # Free GLiNER2 tensors between notes
                gc.collect()

            except Exception as e:
                errors.append({"path": str(note_path), "error": str(e)})

        self.retriever.invalidate_cache()
        total_entities = sum(n["entity_count"] for n in processed)
        self.wal.log("memorize", {
            "processed": len(processed),
            "entities": total_entities,
            "errors": len(errors),
            "query": query,
        })

        return {
            "processed": len(processed),
            "total_entities": total_entities,
            "notes": processed,
            "errors": errors,
        }

    # ── MCP tool implementations ──────────────────────────────────────────────

    def memory_status(self, agent_name: str) -> dict:
        """L0+L1 briefing + protocol injection."""
        agent_name = sanitize_name(agent_name, "agent_name")
        kg_stats = self.kg.stats()
        vs_count = self.vs.count()

        # Get recent session logs from vault
        recent_sessions = self._get_recent_sessions(agent_name)

        # Top entities by occurrence in triples
        top_entities = self._top_entities(limit=8)

        briefing = build_session_briefing(
            agent_name=agent_name,
            recent_sessions=recent_sessions,
            top_entities=top_entities,
            kg_stats={**kg_stats, "notes": vs_count},
            protocol=OPENCLAW_MEMORY_PROTOCOL,
        )
        return {
            "briefing": briefing,
            "vault_notes": vs_count,
            "kg_entities": kg_stats["entities"],
            "kg_facts": kg_stats["triples"],
            "protocol": OPENCLAW_MEMORY_PROTOCOL,
        }

    def memory_query(self, query: str, project: str | None = None, k: int = 10) -> dict:
        """Hybrid semantic + graph search. Returns XML context."""
        query = sanitize_content(query)
        results = self.retriever.search(query, k=k, project=project)
        context_xml = build_context(results, self.kg, query=query)
        return {
            "context": context_xml,
            "result_count": len(results),
            "results": [
                {
                    "path": r["metadata"].get("path", ""),
                    "room": r["metadata"].get("room", ""),
                    "project": r["metadata"].get("project", ""),
                    "score": round(r["score"], 4),
                    "chunk_type": r["metadata"].get("chunk_type", ""),
                    "snippet": r["content"][:200],
                }
                for r in results
            ],
        }

    def memory_remember(
        self,
        title: str,
        content: str,
        project: str,
        room: str | None = None,
        chunk_type: str | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        """Write a note to Obsidian + embed + extract entities."""
        title = sanitize_name(title, "title")
        content = sanitize_content(content)
        project = sanitize_name(project, "project")
        room_name = sanitize_name(room or title, "room")

        # Extract entities before writing
        extraction = extract_note(content, title)

        # Build frontmatter
        entity_tags = [
            f"entity/{e['type'].lower()}/{e['name'].lower().replace(' ','_')}"
            for e in extraction["entities"]
        ]
        all_tags = list(dict.fromkeys((tags or []) + entity_tags))
        ct = chunk_type or extraction["chunk_type"] or "context"

        meta = {
            "title": title,
            "created": date.today().isoformat(),
            "chunk_type": ct,
            "tags": all_tags,
            "project": project,
        }

        # Write to Obsidian vault under project folder
        folder = f"03_Projects/{project}"
        note_path = create_note(self.vault, folder, room_name, content, meta)

        # Embed in ChromaDB
        drawer = self.vs.upsert_note(
            path=str(note_path),
            content=content,
            project=project,
            room=room_name,
            metadata={
                "title": title,
                "chunk_type": ct,
                "tags": "||".join(all_tags),
                "wikilinks": "",
            },
        )

        # Add to KG
        self.kg.add_entities(extraction["entities"])
        triple_count = self.kg.add_triples_from_extraction(
            extraction["relations"], source_note=str(note_path)
        )

        self.wal.log("remember", {
            "path": str(note_path),
            "project": project,
            "room": room_name,
            "entities": len(extraction["entities"]),
        })
        self.retriever.invalidate_cache()

        return {
            "path": str(note_path),
            "drawer_id": drawer,
            "entities_extracted": len(extraction["entities"]),
            "entities": extraction["entities"],
            "triples_added": triple_count,
            "chunk_type": ct,
            "tags": all_tags,
        }

    def memory_kg_add(
        self,
        subject: str,
        predicate: str,
        obj: str,
        valid_from: str | None = None,
        confidence: float = 1.0,
    ) -> dict:
        """Directly add a KG triple."""
        sanitize_name(subject, "subject")
        sanitize_name(predicate, "predicate")
        sanitize_name(obj, "object")
        tid = self.kg.add_triple(subject, predicate, obj, valid_from, confidence)
        self.wal.log("kg_add", {"subject": subject, "predicate": predicate, "object": obj})
        return {"triple_id": tid, "subject": subject, "predicate": predicate, "object": obj}

    def memory_kg_query(self, entity: str, as_of: str | None = None) -> dict:
        """Query all KG facts about an entity."""
        entity = sanitize_name(entity, "entity")
        return self.kg.query_entity(entity, as_of=as_of)

    def memory_session_end(self, agent_name: str, summary: str) -> dict:
        """Write session log note + WAL entry."""
        agent_name = sanitize_name(agent_name, "agent_name")
        summary = sanitize_content(summary)
        today = date.today().isoformat()
        stem = f"{today}-{agent_name}"
        folder = "01_Sessions"
        body = f"## Session Summary\n\n{summary}\n"

        meta = {
            "agent": agent_name,
            "date": today,
            "chunk_type": "milestone",
            "tags": [f"session/{agent_name}"],
        }
        note_path = create_note(self.vault, folder, stem, body, meta)

        # Also embed the summary
        self.vs.upsert_note(
            path=str(note_path),
            content=summary,
            project="_sessions",
            room=stem,
            metadata={"agent": agent_name, "date": today, "chunk_type": "milestone"},
        )

        self.wal.log("session_end", {"agent": agent_name, "path": str(note_path)})
        self.retriever.invalidate_cache()

        return {"path": str(note_path), "agent": agent_name, "date": today}

    # ── private helpers ───────────────────────────────────────────────────────

    def _get_recent_sessions(self, agent_name: str, limit: int = 5) -> list[dict]:
        sessions_dir = self.vault / "01_Sessions"
        if not sessions_dir.exists():
            return []
        results = []
        for p in sorted(sessions_dir.glob(f"*-{agent_name}.md"), reverse=True)[:limit]:
            try:
                note = read_note(p)
                results.append({
                    "agent": agent_name,
                    "date": p.stem.split("-")[0] if "-" in p.stem else "",
                    "summary": note["plain_text"][:300],
                })
            except Exception:
                pass
        return results

    def _top_entities(self, limit: int = 8) -> list[dict]:
        conn = self.kg._get_conn()
        rows = conn.execute(
            "SELECT e.name, e.type, COUNT(t.id) as cnt "
            "FROM entities e LEFT JOIN triples t ON (t.subject=e.id OR t.object=e.id) "
            "WHERE t.valid_to IS NULL "
            "GROUP BY e.id ORDER BY cnt DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [{"name": r["name"], "type": r["type"], "fact_count": r["cnt"]} for r in rows]


# ── helpers ───────────────────────────────────────────────────────────────────

def _path_to_project(note_path: Path, vault: Path) -> str:
    """Derive project name from note's relative path (first meaningful folder)."""
    try:
        rel = note_path.relative_to(vault)
        parts = rel.parts
        if len(parts) > 1:
            # Skip index folders like 00_, 01_, etc.
            for part in parts[:-1]:
                if not re.match(r"^\d+_", part):
                    return part
            return parts[0]
        return "default"
    except ValueError:
        return "default"

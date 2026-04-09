"""
XML context builder — formats retrieval results for LLM consumption.
Output sections: <entities>, <relationships>, <sessions>, <notes>
"""
from __future__ import annotations

import xml.sax.saxutils as saxutils
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .knowledge_graph import KnowledgeGraph


def _esc(s: str) -> str:
    return saxutils.escape(str(s))


def build_context(
    search_results: list[dict],
    kg: "KnowledgeGraph",
    query: str = "",
) -> str:
    """
    Build XML context from retrieval results and KG facts.
    """
    parts = [f'<memory_context query="{_esc(query)}" date="{date.today().isoformat()}">']

    # ── <notes> section ────────────────────────────────────────────────────────
    if search_results:
        parts.append("  <notes>")
        for r in search_results:
            meta = r.get("metadata", {})
            proj = meta.get("project", "")
            room = meta.get("room", "")
            chunk_type = meta.get("chunk_type", "")
            score = r.get("score", 0.0)
            content = r.get("content", "")[:800]  # truncate long notes
            parts.append(
                f'    <note project="{_esc(proj)}" room="{_esc(room)}" '
                f'type="{_esc(chunk_type)}" score="{score:.3f}">'
            )
            parts.append(f"      {_esc(content)}")
            parts.append("    </note>")
        parts.append("  </notes>")

    # ── <entities> section — extracted from KG ─────────────────────────────────
    entity_names_in_results = set()
    for r in search_results:
        for tag in r.get("metadata", {}).get("tags", "").split("||"):
            if tag.startswith("entity/"):
                parts_tag = tag.split("/")
                if len(parts_tag) >= 3:
                    entity_names_in_results.add(parts_tag[2].replace("_", " "))

    if entity_names_in_results:
        parts.append("  <entities>")
        for name in sorted(entity_names_in_results)[:20]:
            result = kg.query_entity(name)
            if result["entity"]:
                ent = result["entity"]
                parts.append(
                    f'    <entity name="{_esc(ent["name"])}" type="{_esc(ent["type"])}">'
                )
                for triple in result["triples"][:5]:
                    parts.append(
                        f'      <fact predicate="{_esc(triple["predicate"])}" '
                        f'object="{_esc(triple["object"])}" />'
                    )
                parts.append("    </entity>")
        parts.append("  </entities>")

    # ── <relationships> section ────────────────────────────────────────────────
    all_triples: list[tuple] = []
    for name in list(entity_names_in_results)[:10]:
        result = kg.query_entity(name)
        for t in result["triples"][:3]:
            all_triples.append((t["subject"], t["predicate"], t["object"]))

    if all_triples:
        parts.append("  <relationships>")
        seen = set()
        for subj, pred, obj in all_triples:
            key = f"{subj}|{pred}|{obj}"
            if key not in seen:
                seen.add(key)
                parts.append(f"    <rel>{_esc(subj)} --[{_esc(pred)}]--> {_esc(obj)}</rel>")
        parts.append("  </relationships>")

    parts.append("</memory_context>")
    return "\n".join(parts)


def build_session_briefing(
    agent_name: str,
    recent_sessions: list[dict],
    top_entities: list[dict],
    kg_stats: dict,
    protocol: str,
) -> str:
    """Build the L0+L1 briefing returned by memory_status."""
    lines = [
        f"<session_briefing agent=\"{_esc(agent_name)}\" date=\"{date.today().isoformat()}\">",
        "",
        protocol,
        "",
    ]

    if kg_stats:
        lines.append(
            f"  <vault_stats entities=\"{kg_stats.get('entities',0)}\" "
            f"facts=\"{kg_stats.get('triples',0)}\" />"
        )

    if top_entities:
        lines.append("  <key_entities>")
        for ent in top_entities[:8]:
            lines.append(f"    <entity name=\"{_esc(ent.get('name',''))}\" type=\"{_esc(ent.get('type',''))}\" />")
        lines.append("  </key_entities>")

    if recent_sessions:
        lines.append("  <recent_sessions>")
        for s in recent_sessions[:5]:
            lines.append(
                f"    <session agent=\"{_esc(s.get('agent',''))}\" "
                f"date=\"{_esc(s.get('date',''))}\">{_esc(s.get('summary','')[:300])}</session>"
            )
        lines.append("  </recent_sessions>")

    lines.append("</session_briefing>")
    return "\n".join(lines)

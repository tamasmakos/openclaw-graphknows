"""SQLite temporal knowledge graph — entities and triples."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date
from pathlib import Path
from typing import Optional


def _entity_id(name: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", name.lower().strip())[:64]


def _triple_id(subject: str, predicate: str, obj: str) -> str:
    raw = f"{subject}|{predicate}|{obj}"
    return "t_" + hashlib.sha256(raw.encode()).hexdigest()[:16]


class KnowledgeGraph:
    def __init__(self, artifact_dir: Path):
        self._db_path = artifact_dir / "knowledge_graph.sqlite3"
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT DEFAULT 'unknown',
                properties TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS triples (
                id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object TEXT NOT NULL,
                valid_from TEXT,
                valid_to TEXT,
                confidence REAL DEFAULT 1.0,
                source_note TEXT,
                FOREIGN KEY (subject) REFERENCES entities(id),
                FOREIGN KEY (object) REFERENCES entities(id)
            );
            CREATE INDEX IF NOT EXISTS idx_triples_subject ON triples(subject);
            CREATE INDEX IF NOT EXISTS idx_triples_object ON triples(object);
            CREATE INDEX IF NOT EXISTS idx_triples_valid ON triples(valid_to);
        """)
        conn.commit()

    def _ensure_entity(self, name: str, etype: str = "unknown") -> str:
        eid = _entity_id(name)
        conn = self._get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO entities(id, name, type) VALUES (?, ?, ?)",
            (eid, name, etype),
        )
        conn.commit()
        return eid

    # ── public write API ───────────────────────────────────────────────────────

    def add_entities(self, entities: list[dict]) -> list[str]:
        """Upsert list of {name, type} dicts. Returns entity IDs."""
        ids = []
        for ent in entities:
            eid = self._ensure_entity(ent.get("name", ""), ent.get("type", "unknown"))
            ids.append(eid)
        return ids

    def add_triple(
        self,
        subject: str,
        predicate: str,
        obj: str,
        valid_from: str | None = None,
        confidence: float = 1.0,
        source_note: str | None = None,
    ) -> str:
        """Add subject→predicate→object. Idempotent; returns triple ID."""
        sub_id = self._ensure_entity(subject)
        obj_id = self._ensure_entity(obj)
        tid = _triple_id(sub_id, predicate.lower(), obj_id)
        conn = self._get_conn()
        # Check idempotency: same triple still valid?
        existing = conn.execute(
            "SELECT id FROM triples WHERE id=? AND valid_to IS NULL", (tid,)
        ).fetchone()
        if existing:
            return tid
        vf = valid_from or date.today().isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO triples(id, subject, predicate, object, valid_from, confidence, source_note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tid, sub_id, predicate.lower(), obj_id, vf, confidence, source_note),
        )
        conn.commit()
        return tid

    def add_triples_from_extraction(
        self, relations: list[dict], source_note: str | None = None
    ) -> int:
        """Bulk-add relations from extractor output. Returns count added."""
        count = 0
        for rel in relations:
            subj = rel.get("subject", "")
            pred = rel.get("predicate", "")
            obj = rel.get("object", "")
            if subj and pred and obj:
                self.add_triple(subj, pred, obj, source_note=source_note)
                count += 1
        return count

    def invalidate_triple(self, triple_id: str) -> None:
        """Set valid_to = today (fact no longer true)."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE triples SET valid_to=? WHERE id=?",
            (date.today().isoformat(), triple_id),
        )
        conn.commit()

    # ── public read API ────────────────────────────────────────────────────────

    def query_entity(self, name: str, as_of: str | None = None) -> dict:
        """Return all facts about an entity, optionally as of a date."""
        eid = _entity_id(name)
        conn = self._get_conn()
        entity = conn.execute(
            "SELECT id, name, type, properties FROM entities WHERE id=?", (eid,)
        ).fetchone()
        if not entity:
            return {"entity": None, "triples": []}

        if as_of:
            rows = conn.execute(
                "SELECT * FROM triples WHERE (subject=? OR object=?) "
                "AND (valid_from IS NULL OR valid_from <= ?) "
                "AND (valid_to IS NULL OR valid_to > ?)",
                (eid, eid, as_of, as_of),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM triples WHERE (subject=? OR object=?) AND valid_to IS NULL",
                (eid, eid),
            ).fetchall()

        return {
            "entity": {"id": entity["id"], "name": entity["name"], "type": entity["type"]},
            "triples": [dict(r) for r in rows],
        }

    def stats(self) -> dict:
        conn = self._get_conn()
        return {
            "entities": conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
            "triples": conn.execute("SELECT COUNT(*) FROM triples WHERE valid_to IS NULL").fetchone()[0],
            "predicates": conn.execute(
                "SELECT COUNT(DISTINCT predicate) FROM triples WHERE valid_to IS NULL"
            ).fetchone()[0],
        }

    def get_entity_names(self) -> list[tuple[str, str]]:
        """Return [(name, stem_id)] for all entities — used for auto-wikification."""
        conn = self._get_conn()
        rows = conn.execute("SELECT name, id FROM entities ORDER BY LENGTH(name) DESC").fetchall()
        return [(r["name"], r["id"]) for r in rows]

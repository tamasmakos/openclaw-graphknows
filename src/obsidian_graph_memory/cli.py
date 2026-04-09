"""CLI entry point — ingest, query, lint, status."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        prog="obsidian-memory",
        description="Obsidian Graph Memory — OpenClaw agent memory system",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ingest
    p_ingest = sub.add_parser("ingest", help="Scan vault, embed notes, extract entities")
    p_ingest.add_argument("--vault", help="Override OPENCLAW_OBSIDIAN_VAULT env var")
    p_ingest.add_argument("--project", help="Only ingest a specific project subfolder")
    p_ingest.add_argument("--no-extract", action="store_true", help="Skip GLiNER2 entity extraction")
    p_ingest.add_argument("--json", action="store_true", help="JSON output")

    # query
    p_query = sub.add_parser("query", help="Semantic search the vault")
    p_query.add_argument("query", nargs="+", help="Query terms")
    p_query.add_argument("--vault", help="Override vault path")
    p_query.add_argument("--project", help="Limit to project")
    p_query.add_argument("--k", type=int, default=5)
    p_query.add_argument("--json", action="store_true")

    # status
    p_status = sub.add_parser("status", help="Show vault + KG stats")
    p_status.add_argument("--vault")
    p_status.add_argument("--agent", default="cli")

    # kg-query
    p_kgq = sub.add_parser("kg-query", help="Query knowledge graph for an entity")
    p_kgq.add_argument("entity", help="Entity name")
    p_kgq.add_argument("--vault")
    p_kgq.add_argument("--as-of", help="ISO date for time-travel")

    # memorize
    p_mem = sub.add_parser("memorize", help="Extract entities from existing notes and enrich the KG")
    p_mem.add_argument("--query", help="Semantic search to find which notes to enrich")
    p_mem.add_argument("--paths", nargs="+", help="Explicit note paths to process")
    p_mem.add_argument("--project", help="Limit to a specific project folder")
    p_mem.add_argument("--limit", type=int, default=10, help="Max notes to process (default 10)")
    p_mem.add_argument("--json", action="store_true")

    args = parser.parse_args()

    # Set vault path
    if hasattr(args, "vault") and args.vault:
        os.environ["OPENCLAW_OBSIDIAN_VAULT"] = args.vault

    from .palace import MemoryPalace

    palace = MemoryPalace()

    if args.command == "ingest":
        result = palace.ingest(
            project=getattr(args, "project", None),
            extract_entities=not getattr(args, "no_extract", False),
        )
        if getattr(args, "json", False):
            print(json.dumps(result, indent=2))
        else:
            print(f"Ingested: {result['ingested']} notes")
            print(f"Entities extracted from: {result['extracted']} notes")
            if result["errors"]:
                print(f"Errors: {len(result['errors'])}")
                for e in result["errors"][:5]:
                    print(f"  {e['path']}: {e['error']}")

    elif args.command == "query":
        q = " ".join(args.query)
        result = palace.memory_query(q, project=args.project, k=args.k)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(result["context"])

    elif args.command == "status":
        result = palace.memory_status(args.agent)
        print(result["briefing"])

    elif args.command == "kg-query":
        result = palace.memory_kg_query(args.entity, as_of=getattr(args, "as_of", None))
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "memorize":
        result = palace.memorize(
            query=getattr(args, "query", None),
            paths=getattr(args, "paths", None),
            project=getattr(args, "project", None),
            limit=getattr(args, "limit", 10),
        )
        if getattr(args, "json", False):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Processed: {result['processed']} notes | Total entities: {result['total_entities']}")
            for n in result["notes"]:
                ents = ", ".join(f"{e['name']} [{e['type']}]" for e in n["entities"][:5])
                print(f"  [{n['chunk_type']}] {n['title']}: {ents}")
            if result["errors"]:
                print(f"\nErrors ({len(result['errors'])}):")
                for e in result["errors"][:5]:
                    print(f"  {e['path']}: {e['error']}")


if __name__ == "__main__":
    main()

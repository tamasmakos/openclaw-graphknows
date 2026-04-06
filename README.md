# Obsidian Graph Memory

A local-first OpenClaw extension that compiles an Obsidian vault into graph memory artifacts for retrieval and linting.

## Current scope

This first implementation slice provides:

- vault compilation into `.obsidian-graph-memory/manifest.json`, `notes.json`, and `graph.json`
- lexical plus graph-expanded querying over markdown notes and wikilinks
- vault linting for broken links, orphan notes, missing index entries, and missing frontmatter
- an OpenClaw extension manifest with configurable vault path and artifact directory

## Commands

```bash
node ./bin/openclaw-obsidian-memory.js ingest --vault /path/to/vault
node ./bin/openclaw-obsidian-memory.js query --vault /path/to/vault --mode graph graph native intelligence
node ./bin/openclaw-obsidian-memory.js lint --vault /path/to/vault
npm run smoke -- /path/to/vault
```

## Smoke test

The package includes a zero-dependency smoke test that exercises the direct extension API plus the compiled artifacts:

```bash
npm run smoke -- /data/.openclaw/workspace-coder1/notes/chessdev
```

It validates ingest, graph query, lint, and artifact consistency against a real vault.

## Next steps

- add incremental compilation and cached reloads
- add source-summary generation and metadata write-back proposals
- add embeddings and semantic search
- validate the OpenClaw loader hook and register runtime tools directly

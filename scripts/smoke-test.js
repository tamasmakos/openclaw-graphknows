#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { activate } from "../index.js";

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function main() {
  const vaultPath = process.argv[2] ?? process.env.OPENCLAW_OBSIDIAN_VAULT;
  if (!vaultPath) {
    throw new Error("Pass a vault path as the first argument or set OPENCLAW_OBSIDIAN_VAULT.");
  }

  const plugin = activate({ vaultPath });
  const ingest = await plugin.commands.ingest();
  const query = await plugin.commands.query("graph native intelligence", { mode: "graph", limit: 5 });
  const lint = await plugin.commands.lint();

  const artifactDir = path.join(vaultPath, ingest.config.artifactDirName);
  const manifest = JSON.parse(await fs.readFile(path.join(artifactDir, "manifest.json"), "utf8"));
  const notes = JSON.parse(await fs.readFile(path.join(artifactDir, "notes.json"), "utf8"));
  const graph = JSON.parse(await fs.readFile(path.join(artifactDir, "graph.json"), "utf8"));

  assert(plugin.id === "obsidian-graph-memory", "Unexpected plugin id.");
  assert(ingest.manifest.stats.noteCount > 0, "Ingest produced no notes.");
  assert(manifest.stats.noteCount === notes.length, "Manifest note count does not match notes.json.");
  assert(graph.nodes.length === notes.length, "graph.json node count does not match notes.json.");
  assert(query.hits.length > 0, "Query returned no hits.");
  assert(query.hits[0].path === "99_Concepts/Graph-Native_Intelligence.md", "Unexpected top query hit.");
  assert(typeof lint.issues.length === "number", "Lint did not return an issues array.");
  assert(notes.every((note) => typeof note.machine?.pagerank === "number"), "Missing machine pagerank on compiled notes.");

  console.log(JSON.stringify({
    ok: true,
    pluginId: plugin.id,
    noteCount: ingest.manifest.stats.noteCount,
    edgeCount: ingest.manifest.stats.edgeCount,
    queryTopHit: query.hits[0].path,
    lintIssueCount: lint.issues.length,
  }, null, 2));
}

main().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  console.error(message);
  process.exit(1);
});

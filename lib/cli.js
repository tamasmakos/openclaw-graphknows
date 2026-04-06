import { resolvePluginConfig } from "./config.js";
import { compileVault } from "./compiler.js";
import { queryVault } from "./query.js";
import { lintVault } from "./lint.js";

function parseArgs(argv) {
  const [command, ...rest] = argv;
  const options = {};
  const positionals = [];
  const booleanFlags = new Set(["json"]);
  const valueFlags = new Set([
    "vault",
    "artifact-dir",
    "mode",
    "source-summary-dir",
    "limit",
  ]);

  for (let index = 0; index < rest.length; index += 1) {
    const value = rest[index];
    if (!value.startsWith("--")) {
      positionals.push(value);
      continue;
    }

    const key = value.slice(2);
    if (booleanFlags.has(key)) {
      options[key] = true;
      continue;
    }

    if (!valueFlags.has(key)) {
      throw new Error(`Unknown option: --${key}`);
    }

    const next = rest[index + 1];
    if (!next || next.startsWith("--")) {
      throw new Error(`Option --${key} requires a value.`);
    }

    options[key] = next;
    index += 1;
  }

  return { command, options, positionals };
}

function buildConfig(options) {
  return resolvePluginConfig({
    vaultPath: options.vault,
    artifactDirName: options["artifact-dir"],
    defaultQueryMode: options.mode,
    sourceSummaryDir: options["source-summary-dir"],
  });
}

function printHumanIngest(result) {
  console.log(`Vault: ${result.manifest.vaultPath}`);
  console.log(`Notes: ${result.manifest.stats.noteCount}`);
  console.log(`Edges: ${result.manifest.stats.edgeCount}`);
  console.log(`Broken links: ${result.manifest.stats.brokenLinkCount}`);
  console.log(`Orphans: ${result.manifest.stats.orphanCount}`);
  console.log(`Artifacts: ${result.config.artifactDirName}/manifest.json, notes.json, graph.json`);
}

function printHumanQuery(result) {
  console.log(`Query: ${result.query}`);
  console.log(`Mode: ${result.mode}`);
  console.log("");
  for (const hit of result.hits) {
    console.log(`- ${hit.title} (${hit.path})`);
    console.log(`  score=${hit.score.toFixed(3)} pagerank=${hit.pagerank.toFixed(4)}`);
    if (hit.reasons.length > 0) {
      console.log(`  reasons=${hit.reasons.join(", ")}`);
    }
    if (hit.snippet) {
      console.log(`  ${hit.snippet}`);
    }
  }
}

function printHumanLint(result) {
  console.log(`Notes: ${result.summary.noteCount}`);
  console.log(`Edges: ${result.summary.edgeCount}`);
  console.log(`Issues: ${result.issues.length}`);
  console.log("");

  for (const issue of result.issues) {
    console.log(`[${issue.severity}] ${issue.path} :: ${issue.rule} :: ${issue.message}`);
  }
}

function printHelp() {
  console.log(`openclaw-obsidian-memory <command> [options]\n`);
  console.log(`Commands:`);
  console.log(`  ingest --vault <path> [--json]`);
  console.log(`  query --vault <path> --mode <lookup|graph> <terms...> [--limit 10] [--json]`);
  console.log(`  lint --vault <path> [--json]`);
}

export async function runCli(argv) {
  const { command, options, positionals } = parseArgs(argv);
  if (!command || command === "--help" || command === "help") {
    printHelp();
    return;
  }

  const config = buildConfig(options);

  if (command === "ingest") {
    const result = await compileVault(config, { writeArtifacts: true });
    if (options.json) {
      console.log(JSON.stringify(result.manifest, null, 2));
      return;
    }
    printHumanIngest(result);
    return;
  }

  if (command === "query") {
    const queryText = positionals.join(" ").trim();
    const result = await queryVault(config, queryText, {
      mode: options.mode,
      limit: options.limit,
    });
    if (options.json) {
      console.log(JSON.stringify(result, null, 2));
      return;
    }
    printHumanQuery(result);
    return;
  }

  if (command === "lint") {
    const result = await lintVault(config, { writeArtifacts: false });
    if (options.json) {
      console.log(JSON.stringify(result, null, 2));
      return;
    }
    printHumanLint(result);
    return;
  }

  throw new Error(`Unknown command: ${command}`);
}

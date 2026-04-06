import path from "node:path";

const DEFAULT_ARTIFACT_DIR_NAME = ".obsidian-graph-memory";
const DEFAULT_QUERY_MODE = "graph";
const DEFAULT_SOURCE_SUMMARY_DIR = "98_Sources";

function assertObject(value) {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

function asTrimmedString(value, fallback) {
  if (typeof value !== "string") {
    return fallback;
  }

  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : fallback;
}

export function resolvePluginConfig(rawConfig = {}) {
  if (!assertObject(rawConfig)) {
    throw new Error("Plugin config must be an object.");
  }

  const envVaultPath = asTrimmedString(process.env.OPENCLAW_OBSIDIAN_VAULT, null);
  const configuredVaultPath = asTrimmedString(rawConfig.vaultPath, envVaultPath);
  const vaultPath = configuredVaultPath ? path.resolve(configuredVaultPath) : null;

  const defaultQueryMode = asTrimmedString(rawConfig.defaultQueryMode, DEFAULT_QUERY_MODE);
  if (!["lookup", "graph"].includes(defaultQueryMode)) {
    throw new Error(`Unsupported defaultQueryMode: ${defaultQueryMode}`);
  }

  const artifactDirName = asTrimmedString(rawConfig.artifactDirName, DEFAULT_ARTIFACT_DIR_NAME);
  const sourceSummaryDir = asTrimmedString(rawConfig.sourceSummaryDir, DEFAULT_SOURCE_SUMMARY_DIR);

  return {
    vaultPath,
    artifactDirName,
    defaultQueryMode,
    sourceSummaryDir,
  };
}

export function ensureVaultPath(config) {
  if (!config?.vaultPath) {
    throw new Error(
      "A vault path is required. Pass --vault /path/to/vault or set OPENCLAW_OBSIDIAN_VAULT.",
    );
  }

  return config.vaultPath;
}

export function resolveArtifactDirectory(config) {
  return path.join(ensureVaultPath(config), config.artifactDirName);
}

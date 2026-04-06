import { resolvePluginConfig } from "./lib/config.js";
import { compileVault } from "./lib/compiler.js";
import { queryVault } from "./lib/query.js";
import { lintVault } from "./lib/lint.js";

export const pluginId = "obsidian-graph-memory";

export function activate(rawConfig = {}) {
  const config = resolvePluginConfig(rawConfig);

  return {
    id: pluginId,
    config,
    commands: {
      ingest: (options = {}) => compileVault({ ...config, ...options }),
      query: (query, options = {}) => queryVault({ ...config, ...options }, query, options),
      lint: (options = {}) => lintVault({ ...config, ...options }, options),
    },
  };
}

export default {
  id: pluginId,
  activate,
};

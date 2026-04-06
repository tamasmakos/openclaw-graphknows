import fs from "node:fs/promises";
import path from "node:path";

const MARKDOWN_EXTENSIONS = new Set([".md", ".markdown"]);
const SKIPPED_DIRECTORIES = new Set([".git", ".obsidian", "node_modules"]);

export function toPosixRelative(rootPath, filePath) {
  return path.relative(rootPath, filePath).split(path.sep).join("/");
}

export function withoutMarkdownExtension(filePath) {
  return filePath.replace(/\.(md|markdown)$/i, "");
}

export async function ensureDirectory(dirPath) {
  await fs.mkdir(dirPath, { recursive: true });
}

export async function readText(filePath) {
  return fs.readFile(filePath, "utf8");
}

export async function writeJson(filePath, value) {
  await fs.writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

export async function listMarkdownFiles(rootPath, config) {
  const results = [];
  const artifactDirName = config?.artifactDirName;

  async function walk(currentPath) {
    const entries = await fs.readdir(currentPath, { withFileTypes: true });

    for (const entry of entries) {
      if (entry.name.startsWith(".") && entry.name !== artifactDirName) {
        if (entry.isDirectory()) {
          continue;
        }
      }

      if (entry.isDirectory()) {
        if (SKIPPED_DIRECTORIES.has(entry.name) || entry.name === artifactDirName) {
          continue;
        }

        await walk(path.join(currentPath, entry.name));
        continue;
      }

      const extension = path.extname(entry.name).toLowerCase();
      if (!MARKDOWN_EXTENSIONS.has(extension)) {
        continue;
      }

      results.push(path.join(currentPath, entry.name));
    }
  }

  await walk(rootPath);
  results.sort((left, right) => left.localeCompare(right));
  return results;
}

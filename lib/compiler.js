import path from "node:path";
import { resolvePluginConfig, ensureVaultPath, resolveArtifactDirectory } from "./config.js";
import { listMarkdownFiles, toPosixRelative, readText, ensureDirectory, writeJson } from "./files.js";
import { parseFrontmatter, extractWikiLinks, extractHashTags, stripMarkdown, deriveTitle } from "./markdown.js";
import { buildSchemaMetadata, collectFrontmatterIssues } from "./schema.js";
import { buildNoteGraph } from "./graph.js";

function countTokenMatches(text, token) {
  if (!text) {
    return 0;
  }

  const matches = text.match(new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"));
  return matches ? matches.length : 0;
}

function buildNoteRecord(vaultPath, absolutePath, content) {
  const relativePath = toPosixRelative(vaultPath, absolutePath);
  const basename = path.posix.basename(relativePath);
  const { data: frontmatter, body, raw: frontmatterRaw } = parseFrontmatter(content);
  const plainText = stripMarkdown(body);
  const title = deriveTitle(relativePath, body);
  const wikiLinks = extractWikiLinks(body);
  const hashTags = extractHashTags(body);
  const words = plainText.length === 0 ? [] : plainText.split(/\s+/).filter(Boolean);
  const schemaMetadata = buildSchemaMetadata({
    relativePath,
    basename,
    frontmatter,
    frontmatterRaw,
    hashTags,
    title,
  });

  return {
    id: relativePath,
    absolutePath,
    relativePath,
    basename,
    title,
    frontmatter,
    frontmatterRaw,
    body,
    plainText,
    wikiLinks,
    hashTags,
    wordCount: words.length,
    noteKind: schemaMetadata.noteKind,
    aliases: schemaMetadata.aliases,
    tags: schemaMetadata.tags,
    sources: schemaMetadata.sources,
    explicitCentrality: schemaMetadata.explicitCentrality,
  };
}

function attachGraphFields(notes, graph) {
  const incoming = graph.incomingEdges;
  const outgoing = graph.outgoingEdges;

  return notes.map((note) => ({
    ...note,
    incomingLinks: incoming.get(note.id) ?? [],
    outgoingLinks: outgoing.get(note.id) ?? [],
    machine: {
      pagerank: graph.pagerank[note.id] ?? 0,
      orphan: (incoming.get(note.id) ?? []).length === 0 && (outgoing.get(note.id) ?? []).length === 0,
      suggestedTokens: note.plainText
        .toLowerCase()
        .split(/[^a-z0-9_-]+/)
        .filter((token) => token.length >= 5)
        .slice(0, 25),
    },
    frontmatterIssues: collectFrontmatterIssues(note),
  }));
}

function buildStats(notes, graph) {
  const orphans = notes.filter((note) => note.machine.orphan).length;
  const indexedRoot = notes.find((note) => note.relativePath === "index.md");
  const logRoot = notes.find((note) => note.relativePath === "log.md");
  const topCentralNotes = [...notes]
    .sort((left, right) => (right.machine.pagerank ?? 0) - (left.machine.pagerank ?? 0))
    .slice(0, 10)
    .map((note) => ({
      path: note.relativePath,
      title: note.title,
      pagerank: note.machine.pagerank,
    }));

  return {
    noteCount: notes.length,
    edgeCount: graph.edges.length,
    brokenLinkCount: graph.brokenLinks.length,
    orphanCount: orphans,
    hasIndex: Boolean(indexedRoot),
    hasLog: Boolean(logRoot),
    topCentralNotes,
  };
}

export async function compileVault(rawConfig = {}, options = {}) {
  const config = resolvePluginConfig(rawConfig);
  const vaultPath = ensureVaultPath(config);
  const markdownFiles = await listMarkdownFiles(vaultPath, config);
  const notes = [];

  for (const markdownFile of markdownFiles) {
    const content = await readText(markdownFile);
    notes.push(buildNoteRecord(vaultPath, markdownFile, content));
  }

  const graph = buildNoteGraph(notes);
  const compiledNotes = attachGraphFields(notes, graph);
  const stats = buildStats(compiledNotes, graph);
  const manifest = {
    generatedAt: new Date().toISOString(),
    vaultPath,
    artifactDirName: config.artifactDirName,
    defaultQueryMode: config.defaultQueryMode,
    stats,
  };

  if (options.writeArtifacts !== false) {
    const artifactDirectory = resolveArtifactDirectory(config);
    await ensureDirectory(artifactDirectory);
    await writeJson(path.join(artifactDirectory, "manifest.json"), manifest);
    await writeJson(path.join(artifactDirectory, "notes.json"), compiledNotes);
    await writeJson(path.join(artifactDirectory, "graph.json"), {
      nodes: graph.nodes,
      edges: graph.edges,
      brokenLinks: graph.brokenLinks,
    });
  }

  return {
    config,
    manifest,
    notes: compiledNotes,
    graph: {
      nodes: graph.nodes,
      edges: graph.edges,
      brokenLinks: graph.brokenLinks,
      outgoingEdges: graph.outgoingEdges,
      incomingEdges: graph.incomingEdges,
    },
  };
}

export function scoreNote(note, tokens) {
  const loweredTitle = note.title.toLowerCase();
  const loweredBody = note.plainText.toLowerCase();
  const loweredAliases = note.aliases.map((alias) => alias.toLowerCase());
  const loweredTags = note.tags.map((tag) => tag.toLowerCase());
  const reasons = [];
  let score = 0;

  for (const token of tokens) {
    const escapedToken = token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const titleMatches = countTokenMatches(loweredTitle, escapedToken);
    const bodyMatches = countTokenMatches(loweredBody, escapedToken);
    const aliasMatches = loweredAliases.filter((alias) => alias.includes(token)).length;
    const tagMatches = loweredTags.filter((tag) => tag.includes(token)).length;

    if (titleMatches > 0) {
      score += titleMatches * 10;
      reasons.push(`title:${token}`);
    }
    if (aliasMatches > 0) {
      score += aliasMatches * 8;
      reasons.push(`alias:${token}`);
    }
    if (tagMatches > 0) {
      score += tagMatches * 5;
      reasons.push(`tag:${token}`);
    }
    if (bodyMatches > 0) {
      score += Math.min(bodyMatches, 5);
      reasons.push(`body:${token}`);
    }
  }

  score += (note.machine.pagerank ?? 0) * 10;

  return {
    score,
    reasons: Array.from(new Set(reasons)),
  };
}

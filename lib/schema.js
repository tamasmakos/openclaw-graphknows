const FOLDER_KIND_MAP = [
  ["01_Business", "business"],
  ["02_Product", "product"],
  ["03_Tech", "tech"],
  ["04_Machine_Learning", "machine-learning"],
  ["04_Repos", "repo"],
  ["05_Chess_Knowledge", "domain"],
  ["99_Concepts", "concept"],
  ["99_Agents", "agent"],
];

function asArray(value) {
  if (Array.isArray(value)) {
    return value.filter((item) => typeof item === "string" && item.trim().length > 0);
  }

  if (typeof value === "string" && value.trim().length > 0) {
    return [value.trim()];
  }

  return [];
}

export function inferNoteKind(note) {
  if (typeof note.frontmatter["entity-type"] === "string" && note.frontmatter["entity-type"].trim()) {
    return note.frontmatter["entity-type"].trim();
  }

  for (const [folder, kind] of FOLDER_KIND_MAP) {
    if (note.relativePath === `${folder}` || note.relativePath.startsWith(`${folder}/`)) {
      return kind;
    }
  }

  if (note.relativePath === "index.md") {
    return "index";
  }

  if (note.relativePath === "log.md") {
    return "log";
  }

  return "note";
}

export function buildSchemaMetadata(note) {
  const aliases = asArray(note.frontmatter.aliases);
  const tags = Array.from(new Set([...asArray(note.frontmatter.tags), ...note.hashTags]));
  const sources = asArray(note.frontmatter.sources);
  const explicitCentrality = typeof note.frontmatter.centrality === "number" ? note.frontmatter.centrality : null;

  return {
    noteKind: inferNoteKind(note),
    aliases,
    tags,
    sources,
    explicitCentrality,
  };
}

export function collectFrontmatterIssues(note) {
  const issues = [];

  if (!note.frontmatterRaw && !["index", "log"].includes(note.noteKind)) {
    issues.push({
      rule: "missing-frontmatter",
      severity: "warning",
      message: "Note has no YAML frontmatter.",
    });
  }

  if (note.noteKind === "concept" && note.aliases.length === 0) {
    issues.push({
      rule: "missing-aliases",
      severity: "info",
      message: "Concept note has no aliases.",
    });
  }

  return issues;
}

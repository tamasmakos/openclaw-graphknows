import { compileVault } from "./compiler.js";

function isUtilityNote(note) {
  return ["index", "log"].includes(note.noteKind) || note.relativePath === "index.md" || note.relativePath === "log.md";
}

function collectIndexedPaths(notes) {
  const indexNote = notes.find((note) => note.relativePath === "index.md");
  const registered = new Set();

  if (!indexNote) {
    return registered;
  }

  for (const link of indexNote.outgoingLinks) {
    registered.add(link);
  }

  return registered;
}

export async function lintVault(rawConfig, options = {}) {
  const compiled = await compileVault(rawConfig, { writeArtifacts: options.writeArtifacts ?? false });
  const indexedPaths = collectIndexedPaths(compiled.notes);
  const issues = [];

  for (const brokenLink of compiled.graph.brokenLinks) {
    issues.push({
      severity: "error",
      rule: "broken-link",
      path: brokenLink.sourcePath,
      message: `Broken wikilink target: ${brokenLink.target}`,
    });
  }

  for (const note of compiled.notes) {
    for (const issue of note.frontmatterIssues) {
      issues.push({
        severity: issue.severity,
        rule: issue.rule,
        path: note.relativePath,
        message: issue.message,
      });
    }

    if (!isUtilityNote(note) && note.machine.orphan) {
      issues.push({
        severity: "warning",
        rule: "orphan-note",
        path: note.relativePath,
        message: "Note has no inbound or outbound wikilinks.",
      });
    }

    if (!isUtilityNote(note) && !indexedPaths.has(note.id)) {
      issues.push({
        severity: "info",
        rule: "missing-index-entry",
        path: note.relativePath,
        message: "Note is not linked from index.md.",
      });
    }
  }

  issues.sort((left, right) => {
    const severityRank = { error: 0, warning: 1, info: 2 };
    const severityDelta = severityRank[left.severity] - severityRank[right.severity];
    if (severityDelta !== 0) {
      return severityDelta;
    }
    return left.path.localeCompare(right.path);
  });

  return {
    summary: compiled.manifest.stats,
    issues,
  };
}

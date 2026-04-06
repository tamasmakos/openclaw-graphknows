import path from "node:path";
import { withoutMarkdownExtension } from "./files.js";

function normalizePath(value) {
  return value.split(path.sep).join("/");
}

function normalizeLinkTarget(target) {
  return withoutMarkdownExtension(target.trim()).replace(/^\.\//, "");
}

function buildLookupMaps(notes) {
  const byId = new Map();
  const byRelative = new Map();
  const byBasename = new Map();
  const byTitle = new Map();

  for (const note of notes) {
    byId.set(note.id, note);
    byRelative.set(normalizeLinkTarget(note.relativePath), note);
    byRelative.set(normalizeLinkTarget(note.relativePath.toLowerCase()), note);

    const basename = normalizeLinkTarget(note.basename);
    if (!byBasename.has(basename)) {
      byBasename.set(basename, note);
    }
    if (!byBasename.has(basename.toLowerCase())) {
      byBasename.set(basename.toLowerCase(), note);
    }

    const normalizedTitle = note.title.trim().toLowerCase();
    if (!byTitle.has(normalizedTitle)) {
      byTitle.set(normalizedTitle, note);
    }
  }

  return { byId, byRelative, byBasename, byTitle };
}

function resolveTarget(sourceNote, rawTarget, lookup) {
  const normalized = normalizeLinkTarget(rawTarget);
  const lowerNormalized = normalized.toLowerCase();

  if (lookup.byRelative.has(normalized)) {
    return lookup.byRelative.get(normalized);
  }
  if (lookup.byRelative.has(lowerNormalized)) {
    return lookup.byRelative.get(lowerNormalized);
  }
  if (lookup.byBasename.has(normalized)) {
    return lookup.byBasename.get(normalized);
  }
  if (lookup.byBasename.has(lowerNormalized)) {
    return lookup.byBasename.get(lowerNormalized);
  }
  if (lookup.byTitle.has(lowerNormalized)) {
    return lookup.byTitle.get(lowerNormalized);
  }

  if (normalized.includes("/")) {
    const sourceDirectory = normalizePath(path.posix.dirname(sourceNote.relativePath));
    const relativeTarget = normalizeLinkTarget(path.posix.normalize(path.posix.join(sourceDirectory, normalized)));
    if (lookup.byRelative.has(relativeTarget)) {
      return lookup.byRelative.get(relativeTarget);
    }
    if (lookup.byRelative.has(relativeTarget.toLowerCase())) {
      return lookup.byRelative.get(relativeTarget.toLowerCase());
    }
  }

  return null;
}

function computePageRank(notes, outgoingEdges, incomingEdges, iterations = 20, damping = 0.85) {
  const ids = notes.map((note) => note.id);
  const total = ids.length || 1;
  const pagerank = Object.fromEntries(ids.map((id) => [id, 1 / total]));

  for (let step = 0; step < iterations; step += 1) {
    const next = {};

    for (const id of ids) {
      let rank = (1 - damping) / total;
      for (const sourceId of incomingEdges.get(id) ?? []) {
        const outgoing = outgoingEdges.get(sourceId) ?? [];
        const sourceRank = pagerank[sourceId] ?? 0;
        const contribution = outgoing.length > 0 ? sourceRank / outgoing.length : sourceRank / total;
        rank += damping * contribution;
      }
      next[id] = rank;
    }

    Object.assign(pagerank, next);
  }

  return pagerank;
}

export function buildNoteGraph(notes) {
  const lookup = buildLookupMaps(notes);
  const outgoingEdges = new Map(notes.map((note) => [note.id, []]));
  const incomingEdges = new Map(notes.map((note) => [note.id, []]));
  const edges = [];
  const brokenLinks = [];

  for (const note of notes) {
    for (const link of note.wikiLinks) {
      const target = resolveTarget(note, link.target, lookup);
      if (!target) {
        brokenLinks.push({
          sourceId: note.id,
          sourcePath: note.relativePath,
          target: link.target,
        });
        continue;
      }

      outgoingEdges.get(note.id).push(target.id);
      incomingEdges.get(target.id).push(note.id);
      edges.push({
        sourceId: note.id,
        targetId: target.id,
        rawTarget: link.target,
      });
    }
  }

  const pagerank = computePageRank(notes, outgoingEdges, incomingEdges);

  return {
    nodes: notes.map((note) => ({
      id: note.id,
      path: note.relativePath,
      title: note.title,
      pagerank: pagerank[note.id] ?? 0,
      outgoingCount: (outgoingEdges.get(note.id) ?? []).length,
      incomingCount: (incomingEdges.get(note.id) ?? []).length,
    })),
    edges,
    pagerank,
    outgoingEdges,
    incomingEdges,
    brokenLinks,
  };
}

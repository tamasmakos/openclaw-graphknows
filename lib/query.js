import { compileVault, scoreNote } from "./compiler.js";

function tokenize(query) {
  return query
    .toLowerCase()
    .split(/[^a-z0-9_-]+/)
    .filter((token) => token.length > 1);
}

function buildSnippet(note, tokens) {
  if (!note.plainText) {
    return "";
  }

  const lowered = note.plainText.toLowerCase();
  let start = 0;
  for (const token of tokens) {
    const index = lowered.indexOf(token);
    if (index !== -1) {
      start = Math.max(0, index - 80);
      break;
    }
  }

  return note.plainText.slice(start, start + 220).trim();
}

function rankLookupHits(notes, tokens, limit) {
  return notes
    .map((note) => {
      const { score, reasons } = scoreNote(note, tokens);
      return {
        id: note.id,
        path: note.relativePath,
        title: note.title,
        noteKind: note.noteKind,
        score,
        pagerank: note.machine.pagerank,
        reasons,
        snippet: buildSnippet(note, tokens),
      };
    })
    .filter((hit) => hit.score > 0)
    .sort((left, right) => right.score - left.score)
    .slice(0, limit);
}

function expandGraphHits(seedHits, noteMap, graph, limit) {
  const scores = new Map();
  const reasons = new Map();

  for (const seed of seedHits) {
    scores.set(seed.id, Math.max(scores.get(seed.id) ?? 0, seed.score));
    reasons.set(seed.id, new Set(seed.reasons));

    const outgoing = graph.outgoingEdges.get(seed.id) ?? [];
    const incoming = graph.incomingEdges.get(seed.id) ?? [];
    const neighbors = new Set([...outgoing, ...incoming]);

    for (const neighborId of neighbors) {
      const neighbor = noteMap.get(neighborId);
      if (!neighbor) {
        continue;
      }

      const nextScore = seed.score * 0.35 + (neighbor.machine.pagerank ?? 0) * 5;
      scores.set(neighborId, Math.max(scores.get(neighborId) ?? 0, nextScore));
      const reasonSet = reasons.get(neighborId) ?? new Set();
      reasonSet.add(`graph:${seed.path}`);
      reasons.set(neighborId, reasonSet);
    }
  }

  return [...scores.entries()]
    .map(([id, score]) => {
      const note = noteMap.get(id);
      return {
        id,
        path: note.relativePath,
        title: note.title,
        noteKind: note.noteKind,
        score,
        pagerank: note.machine.pagerank,
        reasons: Array.from(reasons.get(id) ?? []),
        snippet: buildSnippet(note, []),
      };
    })
    .sort((left, right) => right.score - left.score)
    .slice(0, limit);
}

export async function queryVault(rawConfig, query, options = {}) {
  if (typeof query !== "string" || query.trim().length === 0) {
    throw new Error("A non-empty query string is required.");
  }

  const mode = options.mode ?? rawConfig.defaultQueryMode ?? "graph";
  const limit = Number(options.limit ?? 10);
  const compiled = await compileVault(rawConfig, { writeArtifacts: false });
  const tokens = tokenize(query);
  const lookupHits = rankLookupHits(compiled.notes, tokens, Math.max(limit, 5));
  const noteMap = new Map(compiled.notes.map((note) => [note.id, note]));

  const hits = mode === "graph"
    ? expandGraphHits(lookupHits, noteMap, compiled.graph, limit)
    : lookupHits.slice(0, limit);

  return {
    query,
    mode,
    tokens,
    hits,
    stats: {
      scannedNotes: compiled.notes.length,
      brokenLinks: compiled.graph.brokenLinks.length,
    },
  };
}

function parseScalar(rawValue) {
  const value = rawValue.trim();
  if (value.length === 0) {
    return "";
  }

  if ((value.startsWith(`"`) && value.endsWith(`"`)) || (value.startsWith(`'`) && value.endsWith(`'`))) {
    return value.slice(1, -1);
  }

  if (value === "true") {
    return true;
  }

  if (value === "false") {
    return false;
  }

  if (value === "null") {
    return null;
  }

  if (/^-?\d+(\.\d+)?$/.test(value)) {
    return Number(value);
  }

  if (value.startsWith("[") && value.endsWith("]")) {
    return value
      .slice(1, -1)
      .split(",")
      .map((entry) => entry.trim())
      .filter(Boolean)
      .map((entry) => parseScalar(entry));
  }

  return value;
}

export function parseFrontmatter(content) {
  if (!content.startsWith("---\n")) {
    return { data: {}, body: content, raw: null };
  }

  const closingIndex = content.indexOf("\n---\n", 4);
  if (closingIndex === -1) {
    return { data: {}, body: content, raw: null };
  }

  const raw = content.slice(4, closingIndex);
  const lines = raw.split(/\r?\n/);
  const data = {};

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (!line.trim()) {
      continue;
    }

    const match = line.match(/^([A-Za-z0-9_-]+):\s*(.*)$/);
    if (!match) {
      continue;
    }

    const [, key, value] = match;
    if (value.length > 0) {
      data[key] = parseScalar(value);
      continue;
    }

    const items = [];
    let cursor = index + 1;
    while (cursor < lines.length) {
      const itemLine = lines[cursor];
      const itemMatch = itemLine.match(/^\s*-\s*(.*)$/);
      if (!itemMatch) {
        break;
      }
      items.push(parseScalar(itemMatch[1]));
      cursor += 1;
    }

    if (items.length > 0) {
      data[key] = items;
      index = cursor - 1;
    } else {
      data[key] = "";
    }
  }

  return {
    data,
    body: content.slice(closingIndex + 5),
    raw,
  };
}

export function extractWikiLinks(markdownBody) {
  const results = [];
  const pattern = /\[\[([^\]]+)\]\]/g;
  for (const match of markdownBody.matchAll(pattern)) {
    const rawInner = match[1].trim();
    const [rawTarget, rawLabel] = rawInner.split("|");
    const [target, anchor] = rawTarget.split("#");
    results.push({
      raw: rawInner,
      target: target.trim(),
      anchor: anchor?.trim() ?? null,
      label: rawLabel?.trim() ?? null,
    });
  }
  return results;
}

export function extractHashTags(markdownBody) {
  const results = [];
  const pattern = /(^|\s)#([A-Za-z0-9_/-]+)/g;
  for (const match of markdownBody.matchAll(pattern)) {
    results.push(match[2]);
  }
  return Array.from(new Set(results));
}

export function stripMarkdown(markdownBody) {
  return markdownBody
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")
    .replace(/\[[^\]]+\]\(([^)]+)\)/g, "$1")
    .replace(/\[\[([^\]|]+)(?:\|[^\]]+)?\]\]/g, "$1")
    .replace(/^>\s+/gm, "")
    .replace(/^#+\s+/gm, "")
    .replace(/[*_~]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function deriveTitle(relativePath, markdownBody) {
  const heading = markdownBody.match(/^#\s+(.+)$/m);
  if (heading) {
    return heading[1].trim();
  }

  const segments = relativePath.split("/");
  return segments[segments.length - 1].replace(/\.(md|markdown)$/i, "");
}

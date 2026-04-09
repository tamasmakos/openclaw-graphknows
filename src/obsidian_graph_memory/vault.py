"""Vault I/O — read/write Obsidian markdown with frontmatter."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Iterator

import frontmatter

from .config import ARTIFACT_DIR, sanitize_name

# Regex patterns
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]+)?\]\]")
_HASHTAG_RE = re.compile(r"(?<!\w)#([a-zA-Z][a-zA-Z0-9_/\-]+)")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)


def _skip_dir(d: Path) -> bool:
    name = d.name
    return name.startswith(".") or name in {"node_modules", "__pycache__", ".git"}


def walk_vault(vault: Path) -> Iterator[Path]:
    """Yield all .md files in vault, skipping hidden dirs and artifact dir."""
    for path in sorted(vault.rglob("*.md")):
        rel = path.relative_to(vault)
        # Only check dirs *inside* the vault (not vault's own ancestors)
        if any(_skip_dir(Path(part)) for part in rel.parts[:-1]):
            continue
        if ARTIFACT_DIR in rel.parts:
            continue
        yield path


def read_note(path: Path) -> dict:
    """Parse a single .md file. Returns note record dict."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    post = frontmatter.loads(raw)
    body: str = post.content or ""
    meta: dict = dict(post.metadata)

    wikilinks = _WIKILINK_RE.findall(body)
    hashtags = _HASHTAG_RE.findall(body)
    headings = _HEADING_RE.findall(body)

    return {
        "path": str(path),
        "stem": path.stem,
        "frontmatter": meta,
        "body": body,
        "plain_text": _strip_markdown(body),
        "wikilinks": [w.strip() for w in wikilinks],
        "hashtags": hashtags,
        "headings": headings,
        "tags": _normalise_tags(meta.get("tags", meta.get("tag", []))),
        "aliases": _as_list(meta.get("aliases", meta.get("alias", []))),
        "title": meta.get("title", path.stem),
    }


def write_note_frontmatter(path: Path, updates: dict) -> None:
    """Merge `updates` into a note's frontmatter in-place, preserving body."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    post = frontmatter.loads(raw)
    for k, v in updates.items():
        post[k] = v
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


def create_note(vault: Path, folder: str, stem: str, body: str, meta: dict | None = None) -> Path:
    """Create a new .md note. Does not overwrite existing files."""
    # folder may contain '/' for subdirectories — validate each component separately
    for part in folder.split("/"):
        if part:
            sanitize_name(part, "folder")
    sanitize_name(stem, "note name")
    target_dir = vault / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{stem}.md"
    if path.exists():
        # append a timestamp suffix to avoid collision
        path = target_dir / f"{stem}-{date.today().isoformat()}.md"
    fm = meta or {}
    post = frontmatter.Post(body, **fm)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return path


def inject_entity_tags(path: Path, entities: list[dict]) -> list[str]:
    """
    Write extracted entity tags into frontmatter.
    Tags follow the pattern: entity/type/name (e.g. entity/person/alice).
    Returns the list of new tags added.
    """
    existing_raw = path.read_text(encoding="utf-8", errors="replace")
    post = frontmatter.loads(existing_raw)
    current_tags: list = _normalise_tags(post.metadata.get("tags", post.metadata.get("tag", [])))

    new_tags = []
    for ent in entities:
        ent_type = ent.get("type", "entity").lower().replace(" ", "_")
        ent_name = ent.get("name", "").lower().replace(" ", "_").replace("/", "-")
        if not ent_name:
            continue
        tag = f"entity/{ent_type}/{ent_name}"
        if tag not in current_tags:
            new_tags.append(tag)

    if new_tags:
        merged = list(dict.fromkeys(current_tags + new_tags))  # preserve order, dedup
        post["tags"] = merged
        path.write_text(frontmatter.dumps(post), encoding="utf-8")

    return new_tags


def inject_wikilinks(path: Path, link_targets: list[str]) -> int:
    """
    Append a 'Related' section to a note body with wikilinks.
    Returns number of new links injected.
    """
    existing_raw = path.read_text(encoding="utf-8", errors="replace")
    post = frontmatter.loads(existing_raw)
    body: str = post.content or ""

    existing_links = set(_WIKILINK_RE.findall(body))
    new_links = [t for t in link_targets if t not in existing_links and t != path.stem]

    if not new_links:
        return 0

    related_section = "\n\n## Related\n" + "\n".join(f"- [[{t}]]" for t in new_links)
    post.content = body + related_section
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return len(new_links)


def autofill_wikilinks(path: Path, entity_map: dict[str, str]) -> int:
    """
    Replace bare entity name mentions in body with [[EntityPage]] wikilinks.
    entity_map: {canonical_name -> entity_page_stem}
    Returns count of replacements.
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    post = frontmatter.loads(raw)
    body = post.content or ""
    count = 0
    for name, stem in sorted(entity_map.items(), key=lambda x: -len(x[0])):
        # Only replace whole words not already inside [[...]]
        pattern = re.compile(
            r"(?<!\[\[)(?<!\w)" + re.escape(name) + r"(?!\w)(?!\]\])",
            re.IGNORECASE,
        )
        new_body, n = pattern.subn(f"[[{stem}]]", body)
        if n:
            body = new_body
            count += n
    if count:
        post.content = body
        path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return count


# ── helpers ──────────────────────────────────────────────────────────────────

def _normalise_tags(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(t) for t in raw]
    if isinstance(raw, str):
        return [t.strip() for t in raw.split(",") if t.strip()]
    return []


def _as_list(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        return [raw]
    return []


def _strip_markdown(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", text)
    text = _HEADING_RE.sub(r"\1", text)
    text = re.sub(r"[*_~]{1,3}(.+?)[*_~]{1,3}", r"\1", text)
    text = re.sub(r"^\s*[-*+>|]\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

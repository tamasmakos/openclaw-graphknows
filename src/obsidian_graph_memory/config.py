"""Configuration — vault path, model settings, artifact dirs."""
from __future__ import annotations

import os
import re
from pathlib import Path

_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_ .'\-]{0,126}[a-zA-Z0-9]?$")

VAULT_ENV_VAR = "OPENCLAW_OBSIDIAN_VAULT"
ARTIFACT_DIR = ".obsidian-graph-memory"

# Gemini embedding model
EMBEDDING_MODEL = "models/gemini-embedding-001"
EMBEDDING_DIM = 3072

# GLiNER2 extraction model
EXTRACTOR_MODEL = "fastino/gliner2-base-v1"

# Entity labels for GLiNER2
ENTITY_LABELS = {
    "person": "People, agents, collaborators, authors mentioned",
    "project": "Codebases, repos, products, systems being worked on",
    "technology": "Languages, frameworks, libraries, APIs, databases, tools",
    "concept": "Ideas, algorithms, architectural patterns, theoretical constructs",
    "problem": "Bugs, errors, blockers, unknowns, failure modes",
    "insight": "Discoveries, breakthroughs, lessons learned, conclusions",
}

# Relation labels for GLiNER2
RELATION_LABELS = {
    "works_on":  "Person or agent actively working on a project or task",
    "uses":      "Project or person uses a technology or tool",
    "solved_by": "A problem was resolved by a decision, insight, or action",
    "depends_on":"A project or component depends on another",
    "related_to":"General semantic connection between two entities",
}

# Note chunk type classification labels
CHUNK_TYPES = [
    "decision",   # A choice was made
    "preference", # Stylistic or technical preference
    "milestone",  # Something works, shipped, completed
    "problem",    # Bug, blocker, error
    "insight",    # Discovery, lesson, breakthrough
    "context",    # Background information
    "question",   # Open question, unknown
]

# PageRank config
PAGERANK_DAMPING = 0.85
PAGERANK_ITERATIONS = 30

# Retrieval
DEFAULT_K = 10
SEMANTIC_WEIGHT = 0.7
PAGERANK_WEIGHT = 0.3
NEIGHBOR_SCORE_DECAY = 0.4
SEMANTIC_LINK_THRESHOLD = 0.25  # cosine distance below which notes get auto-linked
MIN_SHARED_ENTITIES_FOR_LINK = 3


def get_vault_path() -> Path:
    """Resolve vault path from env var or raise."""
    raw = os.environ.get(VAULT_ENV_VAR, "")
    if not raw:
        raise RuntimeError(
            f"Set {VAULT_ENV_VAR} environment variable to your Obsidian vault path.\n"
            f"Example: export {VAULT_ENV_VAR}=/data/.openclaw/memory/vault"
        )
    p = Path(raw).expanduser().resolve()
    if not p.exists():
        raise RuntimeError(f"Vault path does not exist: {p}")
    return p


def get_artifact_dir(vault: Path) -> Path:
    d = vault / ARTIFACT_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def sanitize_name(name: str, field: str = "name") -> str:
    """Validate and sanitize wing/room/entity names against path traversal."""
    name = name.strip()
    if not name:
        raise ValueError(f"{field} must not be empty")
    if len(name) > 128:
        raise ValueError(f"{field} must be ≤128 chars")
    if ".." in name or "/" in name or "\\" in name or "\x00" in name:
        raise ValueError(f"{field} contains unsafe characters")
    if not _SAFE_NAME_RE.match(name):
        raise ValueError(f"{field} contains invalid characters: {name!r}")
    return name


def sanitize_content(content: str) -> str:
    if not content or not content.strip():
        raise ValueError("content must not be empty")
    if len(content) > 200_000:
        raise ValueError("content exceeds 200,000 char limit")
    if "\x00" in content:
        raise ValueError("content contains null bytes")
    return content

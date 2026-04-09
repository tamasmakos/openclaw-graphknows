#!/usr/bin/env bash
# install.sh — Install Obsidian Graph Memory for a new OpenClaw workspace
# Usage: bash install.sh [--vault /path/to/vault]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_VAULT="/data/.openclaw/memory/vault"
VAULT="${1:-$DEFAULT_VAULT}"

echo "=== Obsidian Graph Memory — Installer ==="
echo "Vault target: $VAULT"
echo ""

# 1. Install Python package with all deps
echo "[1/4] Installing Python package..."
pip install -e "$SCRIPT_DIR" --break-system-packages -q \
  --root-user-action=ignore 2>&1 | grep -v "^WARNING: Running pip" || true
echo "  ✓ obsidian-graph-memory installed"

# 2. Create vault structure
echo "[2/4] Creating vault structure..."
mkdir -p "$VAULT"/{00_Index,01_Sessions,02_Entities,03_Projects,04_Insights,05_Archive}
echo "  ✓ Vault directories created at $VAULT"

# 3. Verify entry points
echo "[3/4] Verifying CLI..."
if command -v obsidian-memory &>/dev/null; then
  echo "  ✓ obsidian-memory CLI available"
else
  echo "  ✗ obsidian-memory CLI not found — check PATH"
  exit 1
fi

# 4. Quick smoke test (no API key needed)
echo "[4/4] Running smoke test..."
OPENCLAW_OBSIDIAN_VAULT="$VAULT" obsidian-memory status --agent install-test 2>/dev/null | grep -q "OPENCLAW MEMORY PROTOCOL"
echo "  ✓ Status tool OK"

echo ""
echo "=== Installation complete! ==="
echo ""
echo "Environment variable required for embeddings:"
echo "  export GOOGLE_API_KEY=your-gemini-api-key"
echo "  # or: export GEMINI_API_KEY=your-gemini-api-key"
echo ""
echo "Set vault path:"
echo "  export OPENCLAW_OBSIDIAN_VAULT=$VAULT"
echo ""
echo "First ingest (embeds all existing notes, extracts entities):"
echo "  OPENCLAW_OBSIDIAN_VAULT=$VAULT obsidian-memory ingest"
echo ""
echo "GLiNER2 model (~830MB) downloads on first ingest. Subsequent runs are instant."
echo ""
echo "MCP server command for your agent config:"
echo "  python3 -m obsidian_graph_memory.server"

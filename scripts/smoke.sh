#!/usr/bin/env bash
# Smoke test against a running API: health, then one real question through the model.
# Usage: scripts/smoke.sh [api_url] [question]
set -euo pipefail

API="${1:-http://localhost:8000}"
Q="${2:-How has our view on ASML changed since Q1 2026?}"

echo "→ GET $API/health"
curl -fsS "$API/health"
echo

echo "→ POST $API/chat  \"$Q\""
OUT="$(mktemp)"
trap 'rm -f "$OUT"' EXIT
curl -fsSN -X POST "$API/chat" \
  -H 'content-type: application/json' \
  -d "{\"message\": \"$Q\", \"session_id\": \"smoke-$(date +%s)\"}" | tee "$OUT" |
  grep --line-buffered -E '^event: (tool_call|error|done)' || true

if grep -q '^event: error' "$OUT"; then
  echo "✗ stream reported an error:"
  grep -A1 '^event: error' "$OUT" | tail -1
  exit 1
fi
if ! grep -q '^event: done' "$OUT"; then
  echo "✗ stream ended without a done event"
  exit 1
fi

DONE="$(grep -A1 '^event: done' "$OUT" | tail -1 | sed 's/^data: //')"
python3 - "$DONE" <<'PY'
import json, sys
d = json.loads(sys.argv[1])
print("\nanswer:\n" + d["answer"])
print("\ncited:", ", ".join(d["cited"]) or "(none)")
print("tool calls:", [ (t["name"], {k: v for k, v in (t["input"] or {}).items() if k != "query"}) for t in d["trajectory"] ])
assert d["cited"], "answer has no citations"
assert d["trajectory"], "agent did not call any tools"
print("\n✓ smoke test passed (run_id %s)" % d["run_id"])
PY

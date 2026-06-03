#!/usr/bin/env bash
# Discovery-only plugin check.
#
# This script only verifies whether Claude CLI can discover plugin-provided
# slash entrypoints. It is not a runtime validation harness and must not be
# used as the sole release gate after Phase 3.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="${PLUGIN_ROOT:-}"
CLAUDE_BIN="${CLAUDE_BIN:-claude}"

if [[ -z "$PLUGIN_ROOT" ]]; then
  for candidate in \
    "$SCRIPT_DIR/.." \
    "$SCRIPT_DIR/../../dist/plugin" \
    "$SCRIPT_DIR/../dist/plugin"; do
    if [[ -f "$candidate/.claude-plugin/plugin.json" ]]; then
      PLUGIN_ROOT="$(cd "$candidate" && pwd)"
      break
    fi
  done
fi

if [[ -z "$PLUGIN_ROOT" ]]; then
  echo "Could not resolve plugin root. Set PLUGIN_ROOT explicitly." >&2
  exit 1
fi

checks=(
  "/workflowprogram-cn:workflowprogram-orchestrate smoke-test"
  "/workflowprogram-cn:develop smoke-test"
  "/workflowprogram-cn:ship"
  "/workflowprogram-cn:preflight"
  "/workflowprogram-cn:hotfix smoke-test"
  "/workflowprogram-cn:evolve-workflow ."
  "/workflowprogram-cn:iterate-workflow --dry-run ."
  "/review"
  "/test"
  "/commit"
  "/doc"
  "/workflow-audit"
  "/workflowprogram-cn:workflowprogram-develop smoke-test"
  "/workflowprogram-cn:workflowprogram-audit"
  "/workflowprogram-cn:workflowprogram-validate"
  "/workflowprogram-cn:workflowprogram-iterate"
)

pass=0
fail=0

for cmd in "${checks[@]}"; do
  output="$($CLAUDE_BIN -p --plugin-dir "$PLUGIN_ROOT" --output-format json "$cmd" 2>&1 || true)"
  if [[ "$output" == *"Unknown skill:"* ]] || [[ "$output" == *"Unknown command"* ]]; then
    echo "[FAIL] $cmd -> not discovered"
    fail=$((fail + 1))
  elif [[ "$output" == *"Not logged in · Please run /login"* ]] || [[ "$output" == *'"subtype":"success"'* ]]; then
    echo "[PASS] $cmd -> discovered"
    pass=$((pass + 1))
  else
    echo "[FAIL] $cmd -> unexpected response"
    echo "$output"
    fail=$((fail + 1))
  fi
done

echo "PASS: $pass"
echo "FAIL: $fail"

if [[ $fail -ne 0 ]]; then
  exit 1
fi

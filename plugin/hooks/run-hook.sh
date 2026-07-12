#!/bin/sh
# Wrapper for llm-wiki's SessionEnd/SessionStart hooks.
#
# Claude Code invokes hook commands with a single JSON object on stdin
# (fields include "session_id", "cwd", "hook_event_name", ...). This
# wrapper reads that JSON exactly once, pulls out "cwd" (both
# subcommands need it) and "session_id" (breadcrumb only), and dispatches
# to session_ops.py. Never fails loudly -- a hook that breaks a session
# is worse than a hook that silently no-ops, so stdin/python failures
# fall back to sane defaults rather than aborting.
#
# Usage: run-hook.sh <breadcrumb|session-check>

set -eu

SUBCOMMAND="${1:-}"
if [ -z "$SUBCOMMAND" ]; then
    echo "run-hook.sh: missing subcommand (breadcrumb|session-check)" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# No python3 -> exit silently rather than failing every session.
command -v python3 >/dev/null 2>&1 || exit 0

# Read stdin once. Tolerate empty/absent stdin (e.g. manual invocation).
STDIN_JSON="$(cat 2>/dev/null || true)"

HOOK_CWD="$(printf '%s' "$STDIN_JSON" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get("cwd") or "")
except Exception:
    print("")
' 2>/dev/null || true)"
[ -n "$HOOK_CWD" ] || HOOK_CWD="$PWD"

case "$SUBCOMMAND" in
    breadcrumb)
        HOOK_SESSION_ID="$(printf '%s' "$STDIN_JSON" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get("session_id") or "")
except Exception:
    print("")
' 2>/dev/null || true)"
        [ -n "$HOOK_SESSION_ID" ] || HOOK_SESSION_ID="unknown"
        HOOK_DATE="$(date +%F)"
        exec python3 "${PLUGIN_ROOT}/scripts/session_ops.py" breadcrumb \
            --cwd "$HOOK_CWD" --session-id "$HOOK_SESSION_ID" --date "$HOOK_DATE"
        ;;
    session-check)
        exec python3 "${PLUGIN_ROOT}/scripts/session_ops.py" session-check \
            --cwd "$HOOK_CWD"
        ;;
    *)
        echo "run-hook.sh: unknown subcommand '$SUBCOMMAND'" >&2
        exit 1
        ;;
esac

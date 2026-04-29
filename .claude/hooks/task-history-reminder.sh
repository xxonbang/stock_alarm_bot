#!/usr/bin/env bash
# PostToolUse hook — git commit 후 task_history 업데이트 알림
# CLAUDE.md 규칙 #6 준수 보조

set -euo pipefail

INPUT="$(cat)"
TOOL_NAME="$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null || echo "")"
COMMAND="$(echo "$INPUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('command',''))" 2>/dev/null || echo "")"

if [[ "$TOOL_NAME" != "Bash" ]]; then
    exit 0
fi

# git commit 명령에만 반응 (commit -m, commit -F 등)
if ! echo "$COMMAND" | grep -qE '\bgit[[:space:]]+commit\b'; then
    exit 0
fi

PROJECT_ROOT="/Users/sonbyeongcheol/DEV/trade_info_sender"
TASK_HISTORY="$PROJECT_ROOT/docs/task_history.md"
TODAY=$(date +%Y-%m-%d)

# task_history.md에 오늘 날짜가 있는지 확인
if [[ -f "$TASK_HISTORY" ]] && head -50 "$TASK_HISTORY" | grep -q "## $TODAY"; then
    # 오늘자 이력이 이미 있음 — 단순 알림
    echo "ℹ️ task_history 알림: docs/task_history.md에 오늘($TODAY) 항목 존재. 새 커밋 이력 추가 검토 권장." >&2
else
    # 오늘자 이력 없음 — 강한 알림
    echo "⚠️ task_history 알림: docs/task_history.md에 오늘($TODAY) 항목 없음. CLAUDE.md 규칙 #6에 따라 이력 추가 권장." >&2
fi

exit 0

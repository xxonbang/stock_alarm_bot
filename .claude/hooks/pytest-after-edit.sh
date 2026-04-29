#!/usr/bin/env bash
# PostToolUse hook — src/ 또는 tests/ 변경 후 pytest 자동 실행
# 입력: stdin JSON {"tool_name": "Edit"|"Write", "tool_input": {"file_path": "..."}}
# 출력: 테스트 결과를 stderr로 출력 (Claude가 자동 인지)

set -euo pipefail

INPUT="$(cat)"
TOOL_NAME="$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null || echo "")"
FILE_PATH="$(echo "$INPUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null || echo "")"

# Edit/Write/MultiEdit만 처리
case "$TOOL_NAME" in
    Edit|Write|MultiEdit) ;;
    *) exit 0 ;;
esac

# 프로젝트 루트
PROJECT_ROOT="/Users/sonbyeongcheol/DEV/trade_info_sender"

# src/ 또는 tests/ 하위 .py 파일만 트리거
case "$FILE_PATH" in
    "$PROJECT_ROOT/src/"*.py|"$PROJECT_ROOT/tests/"*.py) ;;
    *) exit 0 ;;
esac

# venv 존재 확인
if [[ ! -x "$PROJECT_ROOT/venv/bin/pytest" ]]; then
    exit 0
fi

# pytest 짧은 출력으로 실행 (--quiet)
cd "$PROJECT_ROOT"
RESULT="$("$PROJECT_ROOT/venv/bin/pytest" tests/ --tb=line -q 2>&1 | tail -10)"
EXIT_CODE=$?

if [[ $EXIT_CODE -ne 0 ]]; then
    echo "❌ pytest 실패 (변경: $FILE_PATH):" >&2
    echo "$RESULT" >&2
    exit 1
fi

# 성공 시 짧은 알림
LAST_LINE="$(echo "$RESULT" | grep -E '^[0-9]+ passed' || echo '')"
if [[ -n "$LAST_LINE" ]]; then
    echo "✅ pytest: $LAST_LINE (변경 $FILE_PATH)" >&2
fi
exit 0

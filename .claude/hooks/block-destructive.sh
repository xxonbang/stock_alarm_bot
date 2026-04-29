#!/usr/bin/env bash
# PreToolUse hook — 위험한 명령 차단
# 차단 대상: rm -rf, git push --force, GitHub secret 삭제, Supabase 테이블 drop
#
# 입력: stdin JSON {"tool_name": "Bash", "tool_input": {"command": "..."}}
# 출력: 차단할 경우 stdout에 사유 + exit 2 (Claude에게 차단 알림)

set -euo pipefail

INPUT="$(cat)"
TOOL_NAME="$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null || echo "")"
COMMAND="$(echo "$INPUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('command',''))" 2>/dev/null || echo "")"

if [[ "$TOOL_NAME" != "Bash" ]]; then
    exit 0
fi

# rm -rf (현재 디렉토리, 홈, src/, tests/ 등 위험 위치)
if echo "$COMMAND" | grep -qE 'rm[[:space:]]+(-[a-zA-Z]*r[a-zA-Z]*f|-rf|-fr)\b'; then
    echo "차단: rm -rf 명령은 사용자 확인 없이 차단됩니다. 정말 필요하면 사용자에게 명시적 동의를 받으세요." >&2
    exit 2
fi

# git push --force / -f (origin/main 등 공유 브랜치)
if echo "$COMMAND" | grep -qE 'git[[:space:]]+push[[:space:]]+(--force|-f)\b'; then
    echo "차단: git push --force는 차단됩니다. 공유 브랜치 히스토리 손상 위험." >&2
    exit 2
fi

# GitHub secret 삭제
if echo "$COMMAND" | grep -qE 'gh[[:space:]]+secret[[:space:]]+(remove|delete)\b'; then
    echo "차단: gh secret remove/delete는 차단됩니다. 의도치 않은 운영 키 손실 방지." >&2
    exit 2
fi

# Supabase: portfolio 테이블 전체 삭제 (개별 row 삭제는 OK)
if echo "$COMMAND" | grep -qE 'DROP[[:space:]]+TABLE|TRUNCATE[[:space:]]+(TABLE[[:space:]]+)?portfolio\b'; then
    echo "차단: portfolio 테이블 DROP/TRUNCATE는 차단됩니다." >&2
    exit 2
fi

# .env 또는 secrets 파일 삭제
if echo "$COMMAND" | grep -qE 'rm[[:space:]]+.*\.env\b|rm[[:space:]]+.*secrets\b'; then
    echo "차단: .env / secrets 파일 삭제는 차단됩니다." >&2
    exit 2
fi

exit 0

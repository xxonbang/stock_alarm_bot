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

# 위험 명령이 실제 명령 위치에 있는지 검사 (heredoc/주석/문자열 내부의 단순 텍스트는 제외).
# 명령 위치 = 줄 시작, 또는 `;`, `&&`, `||`, `|`, `(` 직후.
# 정확한 shell 파싱은 어려우니 근사: 명령 시작 후 첫 토큰이 "rm" 같은지만 확인.

# 명령의 첫 토큰 추출 (heredoc body 제외)
# heredoc(<<...EOF\n...EOF)는 stdin인 줄을 따로 처리. 여기서는 명령 라인 첫 부분만 본다.
FIRST_TOKEN=$(echo "$COMMAND" | head -1 | awk '{print $1}')
SECOND_TOKEN=$(echo "$COMMAND" | head -1 | awk '{print $2}')

# rm -rf 실제 명령 (heredoc 안의 message text는 무시)
if [[ "$FIRST_TOKEN" == "rm" ]]; then
    if echo "$SECOND_TOKEN" | grep -qE '^(-[a-zA-Z]*r[a-zA-Z]*f|-rf|-fr)$'; then
        echo "차단: rm -rf 명령은 사용자 확인 없이 차단됩니다. 정말 필요하면 사용자에게 명시적 동의를 받으세요." >&2
        exit 2
    fi
    # rm <something>.env 또는 rm secrets/...
    if echo "$COMMAND" | head -1 | grep -qE '^rm[[:space:]].*\.env\b|^rm[[:space:]].*secrets\b'; then
        echo "차단: .env / secrets 파일 삭제는 차단됩니다." >&2
        exit 2
    fi
fi

# git push --force / -f (실제 git push 명령일 때만)
if [[ "$FIRST_TOKEN" == "git" && "$SECOND_TOKEN" == "push" ]]; then
    if echo "$COMMAND" | head -1 | grep -qE 'git[[:space:]]+push[[:space:]]+.*(--force|[[:space:]]-f([[:space:]]|$))'; then
        echo "차단: git push --force는 차단됩니다. 공유 브랜치 히스토리 손상 위험." >&2
        exit 2
    fi
fi

# GitHub secret 삭제 (실제 gh 명령)
if [[ "$FIRST_TOKEN" == "gh" && "$SECOND_TOKEN" == "secret" ]]; then
    if echo "$COMMAND" | head -1 | grep -qE 'gh[[:space:]]+secret[[:space:]]+(remove|delete)\b'; then
        echo "차단: gh secret remove/delete는 차단됩니다. 의도치 않은 운영 키 손실 방지." >&2
        exit 2
    fi
fi

# Supabase: portfolio 테이블 전체 삭제 (SQL 형태)
if echo "$COMMAND" | grep -qiE '\b(DROP[[:space:]]+TABLE|TRUNCATE[[:space:]]+(TABLE[[:space:]]+)?)\s*portfolio\b'; then
    echo "차단: portfolio 테이블 DROP/TRUNCATE는 차단됩니다." >&2
    exit 2
fi

exit 0

#!/usr/bin/env bash
# SessionStart hook — 세션 시작 시 프로젝트 현황 브리핑
# 출력 stdout이 Claude의 SessionStart additional context로 주입됨

set -euo pipefail

PROJECT_ROOT="/Users/sonbyeongcheol/DEV/trade_info_sender"
cd "$PROJECT_ROOT" 2>/dev/null || exit 0

echo "[trade_info_sender 세션 브리핑]"
echo

# 1) 브랜치 + main vs origin/main 차이
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
echo "📂 브랜치: $BRANCH"
if git remote get-url origin >/dev/null 2>&1; then
    AHEAD="$(git rev-list --count origin/main..main 2>/dev/null || echo '?')"
    BEHIND="$(git rev-list --count main..origin/main 2>/dev/null || echo '?')"
    if [[ "$AHEAD" != "0" || "$BEHIND" != "0" ]]; then
        echo "⚠️  origin/main 대비: ahead=$AHEAD, behind=$BEHIND (push/pull 필요 가능)"
    fi
fi

# 2) 최근 git 커밋 3개
echo
echo "📝 최근 커밋:"
git log --oneline -3 2>/dev/null | sed 's/^/   /'

# 3) 최근 GitHub Actions 실행 (3건, gh CLI 가능 시)
if command -v gh >/dev/null 2>&1 && [[ -d .git ]]; then
    echo
    echo "🚀 최근 trend_scan 실행:"
    gh run list --workflow=trend_scan.yml --limit 3 2>/dev/null \
        | awk '{printf "   %-10s %-10s %s\n", $1, $2, $9}' | head -3
fi

# 4) 오늘자 task_history 항목 수
TASK_HISTORY="docs/task_history.md"
TODAY=$(date +%Y-%m-%d)
if [[ -f "$TASK_HISTORY" ]]; then
    TODAY_COUNT=$(awk -v d="## $TODAY" '
        $0 == d { in_today = 1; next }
        /^## [0-9]/ && in_today { exit }
        in_today && /^### / { count++ }
        END { print count + 0 }
    ' "$TASK_HISTORY")
    echo
    if [[ "$TODAY_COUNT" -gt 0 ]]; then
        echo "📅 task_history: 오늘($TODAY) $TODAY_COUNT건"
    else
        # 직전 작업일 찾기
        LAST_DATE=$(grep -E '^## [0-9]{4}-[0-9]{2}-[0-9]{2}$' "$TASK_HISTORY" | head -1 | sed 's/^## //')
        echo "📅 task_history: 오늘 항목 없음. 직전 작업일=$LAST_DATE"
    fi
fi

# 5) 워킹 트리 상태
DIRTY=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ' || echo 0)
if [[ -n "${DIRTY:-}" && "$DIRTY" -gt 0 ]]; then
    echo
    echo "💾 워킹 트리: ${DIRTY}개 변경"
fi

echo

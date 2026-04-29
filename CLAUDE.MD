# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## 5. 세션/컴팩팅 시 작업 연속성 유지

**새 세션 시작 또는 context compacting 발생 시, 반드시 `docs/task_history.md`에서 오늘자 작업 이력을 읽고 확인한 뒤 작업을 이어갈 것.** 이전 작업 맥락을 파악하여 연속성을 최대화한다.

- 오늘자 이력이 있으면: **"[task_history 확인 완료] 오늘자 N건 확인"** 형식으로 표시.
- 오늘자 이력이 없으면: **직전 작업일** 이력을 확인하고 **"[task_history 확인 완료] 오늘자 이력 없음, 직전 작업일(YYYY-MM-DD) N건 확인"** 형식으로 표시.
- 확인하지 않은 채 작업을 시작하지 말 것.

## 6. Task History 기록

**기록 시점**: 커밋 완료 직후 또는 단위 작업 종료 시, 다음 작업으로 넘어가기 전에 반드시 `docs/task_history.md`에 이력을 기록한다.

**포맷 규칙:**

- 날짜별 `## YYYY-MM-DD` 헤더 (최신 날짜가 상단)
- 각 항목은 `### [카테고리] 제목 (YYYY-MM-DD HH:MM KST)` 형식 — 날짜와 시각 모두 포함, **KST 기준**
- 같은 날짜 내에서도 **최신 항목이 상단**에 위치하도록 역순 정렬
  - 카테고리: `기능`, `버그픽스`, `개선`, `리팩토링`, `설정`, `진단` 중 택1
- 필수 항목: 변경 파일, 내용 (1~2줄 요약)
- 선택 항목: 커밋 해시, 원인 (버그픽스 시)
- 최신 항목이 해당 날짜의 하단에 추가되도록 기록

## 6. Research 문서 관리

조사/연구/진단 결과로 생성되는 md 문서는 `docs/research/` 폴더에 저장한다.

**파일명 규칙:** `YYYY-MM-DD-<단어1>-<단어2>.md`

- 날짜 뒤에 작업의 성격과 내용을 대표하는 **2개 단어**를 하이픈으로 연결
- 예: `2026-03-11-project-diagnostic.md`, `2026-04-01-api-latency.md`

## Doc Sync (doc-sync 스킬)

프로젝트 진행 중 `docs/` 하위 9개 문서를 자동 관리하고 세션 간 작업 상태를 복구한다.

- 모든 관리 문서는 **`docs/`** 폴더에 생성
- **누적형** 문서(`todo.md`, `decision.md`)는 기존 내용을 절대 삭제하지 않음
- 문서 업데이트 후 반드시 사용자에게 알림 출력
- UI와 문서 생성은 한국어 기본

---

## 8. trade_info_sender 도메인 컨텍스트

### 8.1 시스템 개요

매일 KST 07:30·20:00 cron-job.org가 GitHub Actions의 `trend_scan.yml`을 트리거하여
미국·한국 뉴스/커뮤니티/유튜브를 수집·분석한 뒤 텔레그램 3 메시지(미국·한국·유튜브) 발송.

핵심 흐름 (`src/trend_scanner.py::main()`):
1. **수집**: 4 batches + youtube
   - `us_news`: Google News RSS (영문)
   - `us_community`: HN(Algolia API) + StockTwits trending
   - `kr_news`: Google News RSS (한글)
   - `kr_community`: 에펨코리아 + 38커뮤 + 클리앙
   - `youtube`: YouTube Data API + youtube-transcript-api (7개 채널 + 키워드)
2. **AI 콜 #1**: 4 batches → 종목·섹터 10개씩 (`extract_per_batch`)
3. **AI 콜 #2**: TOP3 종목·섹터 (`select_top3` + 인덱스 필터 + 저빈도 필터)
4. **AI 콜 #3**: Google Search grounding으로 1주일 보수적 전망 (`generate_outlook`)
5. **YouTube AI 콜**: 영상 10개 → TOP3 + 영상 내용 (`analyze_youtube`)
6. **검증**: `verify_indices` 인덱스 매핑
7. **발송**: 텔레그램 3 메시지

### 8.2 외부 의존성

| 서비스 | 용도 | 환경변수 |
|---|---|---|
| Gemini API | LLM 추출/요약/grounding (5개 키 풀) | `GOOGLE_API_KEY_01`~`05` |
| Telegram Bot | 메시지 발송 | `TELEGRAM_TOKEN`, `CHAT_ID` |
| YouTube Data API v3 | 영상 메타 + 검색 | `YOUTUBE_API_KEY` |
| Supabase | 포트폴리오 종목 DB | `SUPABASE_URL`, `SUPASECRET_KEY` |
| cron-job.org | GitHub workflow_dispatch 트리거 | `CRONJOB_API_KEY` |
| GitHub PAT | cron-job.org → GH Actions 호출용 | `GITHUB_PAT` |

### 8.3 자주 쓰는 명령

```bash
# 테스트
./venv/bin/pytest tests/

# 로컬 트렌드 스캐너 실행 (--test 모드: 콘솔 출력만)
./venv/bin/python -m src.trend_scanner --test

# GitHub Actions 수동 트리거
gh workflow run trend_scan.yml --ref main

# 최근 실행 확인
gh run list --workflow=trend_scan.yml --limit 5

# 실패 run 로그 분석
gh run view <ID> --log-failed | grep -E "ERROR|JSON 파싱|429|503|MAX_TOKENS"

# cron-job.org 등록 작업 조회
./venv/bin/python scripts/register_cron.py --list

# 포트폴리오 종목 조회
./venv/bin/python -c "
from config import settings
from src.portfolio_manager import PortfolioManager
pm = PortfolioManager()
print('보유:', [(it['ticker'], it['name']) for it in pm.list_by_category('possession')])
print('관심:', [(it['ticker'], it['name']) for it in pm.list_by_category('interest')])
"
```

### 8.4 안전 규칙 (.claude/hooks가 강제)

- **차단**: `rm -rf`, `git push --force`, `gh secret delete`, `DROP TABLE portfolio`
- **자동 실행**: `src/` 또는 `tests/` Edit 후 pytest 자동
- **자동 알림**: `git commit` 후 task_history.md 갱신 알림
- **세션 시작**: main↔origin 차이, 최근 failed runs, 오늘 task_history 자동 표시

### 8.5 알려진 운영 패턴

- **Gemini 모델**: `gemini-2.5-flash-lite` (RPD 한도 풍부, grounding 지원)
- **유튜브 자막**: 로컬에서 OK, GH Actions runner IP에서 차단 (제목·설명만 분석됨 — 정상 동작)
- **kr_community**: 3개 사이트 best-effort. 1개 실패해도 나머지로 진행
- **저빈도 필터**: TOP3 stocks ≥ 10/60, sectors ≥ 15/60, youtube ≥ 4/10. 미달 시 TOP3 비울 수 있음 (정상)
- **인덱스 필터**: 코스피/코스닥/S&P 500/Nasdaq/QQQ 등은 stocks·sectors에서 자동 제거
- **재시도 정책**: RPM 한도(retryDelay < 60s)는 같은 키로 wait+retry, daily quota는 fallback key로 전환

### 8.6 .claude/ 구성요소

- `.claude/agents/`: `trend-scanner-debugger`, `portfolio-manager`
- `.claude/skills/`: `trigger-trend-scan`, `analyze-failed-run`, `verify-pipeline`
- `.claude/hooks/`: `block-destructive`, `pytest-after-edit`, `task-history-reminder`, `session-start-brief`
- `.claude/settings.json`: permissions (allow/deny) + hooks 등록

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

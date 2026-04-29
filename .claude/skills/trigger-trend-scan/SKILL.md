---
name: trigger-trend-scan
description: trend_scan.yml 워크플로우 수동 트리거 + 백그라운드 모니터링 + 결과 보고. 사용 — 사용자가 "수동 실행", "트리거", "테스트 실행" 등을 요청할 때.
---

trend_scan.yml 워크플로우를 수동 실행하고 완료까지 모니터링한 뒤 결과를 보고합니다.

## 흐름

1. **트리거**:
   ```bash
   gh workflow run trend_scan.yml --ref main
   sleep 4
   gh run list --workflow=trend_scan.yml --limit 1
   ```
   → run ID 확보 (예: `25092528971`)

2. **백그라운드 모니터링** (Bash run_in_background=true 사용):
   ```bash
   until [ "$(gh run view <RUN_ID> --json status -q .status 2>/dev/null)" = "completed" ]; do
     sleep 25
   done
   gh run view <RUN_ID> --json status,conclusion
   ```
   백그라운드 시작 후 다른 작업 진행. 완료 시 system이 task-notification으로 알림.

3. **결과 분석**:
   - `conclusion: success` 시:
     - `gh run view <ID> --log | grep -E "AI [0-9]/3|발송 결과|필터|수집 완료"` 으로 핵심 흐름 추출
     - 텔레그램 발송 결과 (us/kr/youtube) 보고
     - 필터링 (인덱스 제거, 저빈도 제거) 통계
   - `conclusion: failure` 시:
     - `trend-scanner-debugger` agent 호출 또는 `analyze-failed-run` skill 사용
     - 실패 원인 분류 + 수정 필요 여부 판단

## 보고 양식

성공:
- ⏱ 총 소요 시간
- 🤖 AI 호출 횟수 + 토큰 사용 (있으면)
- 📊 수집 결과 (배치별 갯수, 필터 적용 건수)
- 📨 텔레그램 발송 결과 (us/kr/youtube ✅/❌)

실패:
- 🚨 실패 단계 (수집 / AI 추출 / TOP3 / 전망 / 발송)
- 🔍 핵심 에러 (1~2줄)
- 🛠 다음 조치 (코드 수정 / 외부 장애 대기 / 재시도)

## 주의

- 트리거 후 항상 백그라운드 모니터링 사용. 폴링 루프를 foreground로 돌려 컨텍스트 낭비 금지.
- run ID는 항상 명시적으로 확보 (sleep 후 list로). 다른 사용자나 cron-job 실행과 혼동 금지.
- conclusion 외에 actual telegram 발송 여부도 로그로 확인 (sometimes `success` but no telegram if logic skipped).
- 사용자에게 "실패" 보고 시 반드시 원인 분류와 다음 조치를 함께 제시 — "실패했습니다"만으로 끝내지 마세요.

---
name: analyze-failed-run
description: 최근 실패한 trend_scan.yml run의 로그를 자동 추출·분류·요약. 사용 — 사용자가 "실패 원인 봐줘", "왜 안 됐어" 등 묻거나 텔레그램 에러 메시지 받았을 때.
---

GitHub Actions의 trend_scan.yml 실패 run을 분석합니다.

## 흐름

1. **실패 run 찾기**:
   ```bash
   gh run list --workflow=trend_scan.yml --limit 5 --json databaseId,conclusion,createdAt,status \
     | python3 -c "import json,sys; runs=[r for r in json.load(sys.stdin) if r['conclusion']=='failure']; print(runs[0]['databaseId'] if runs else 'none')"
   ```
   사용자가 특정 run ID 제공 시 그것 사용.

2. **핵심 에러 추출** (한 번의 grep으로):
   ```bash
   gh run view <ID> --log-failed | grep -E "ERROR|JSON 파싱|429|503|MAX_TOKENS|finish_reason|할당량|시도 [0-9]/[0-9]|모든 API|abort" | head -40
   ```

3. **패턴 매핑** (`.claude/agents/trend-scanner-debugger.md`의 알려진 실패 패턴 표 참고):
   | 키워드 | 분류 |
   |---|---|
   | `MAX_TOKENS finish_reason` | LLM 출력 한도 (코드: max_output_tokens 증가) |
   | `Expecting property name` JSON 에러 | 잘린 JSON (위 결과로 인한 2차 증상) |
   | `429 RESOURCE_EXHAUSTED` retryDelay 짧음(<60s) | RPM 한도 (외부, 자동 회복) |
   | `429 RESOURCE_EXHAUSTED` retryDelay 길거나 모든 키 동시 | daily quota — model 변경 또는 paid plan |
   | `503 UNAVAILABLE` 카스케이드 | Gemini 서버 과부하 (외부, 자동 회복) |
   | `Gemini API 외부 장애` 텔레그램 | _call_ai 모든 retry 실패 후 sentinel |
   | `kr_community fetch 실패 (HTTP 430)` | 사이트 일시 차단 (정상, 다른 소스로 채움) |

4. **수집 단계 정상성 확인**:
   ```bash
   gh run view <ID> --log | grep -E "수집 완료|fetch 실패" | head -10
   ```

5. **보고**:
   - **분류**: 외부 일시 장애 / 코드 버그 / 환경 설정 (3개 중 1)
   - **핵심 에러 요약**: 1~2줄
   - **다음 조치**: 자동 회복 대기 / 코드 수정 필요 / 환경 변수 확인

## 보고 양식

```
🔍 분석 결과 (run #<ID>):

분류: <외부 일시 장애 | 코드 버그 | 환경 설정>

증상:
- <key error 1줄>
- <key error 1줄>

원인: <root cause 1~2 sentence>

조치:
- <action 1>
- <action 2>
```

## 주의

- secret 노출 금지: 로그에 키 값이 나타나도 출력 금지 (Gemini 등 키 값을 절대 마스킹 안 한 채 출력하지 마세요).
- "코드 버그"로 분류할 때는 반드시 어느 파일·줄을 어떻게 수정해야 할지 구체적으로 제시.
- 외부 일시 장애 (RPM 한도, 503 카스케이드)는 **반드시 "외부"라고 명시** — 사용자가 코드 수정 기다리지 않게.
- 1차 분석 후 사용자가 추가 질문하면 `gh run view --log` 전체 또는 특정 step만 더 자세히 추출.

# Task History

## 2026-03-19

### [기능] 장중 실시간 수급 + 프로그램 매매 수집 (2026-03-19 22:00 KST)
- 커밋: f02d157
- 변경 파일: `src/dual_source/sources/kis_source.py`, `src/dual_source/types.py`, `src/dual_source/validation_engine.py`, `src/crawler.py`, `src/analysis.py`, `src/alert_engine.py`
- 내용:
  1. KIS `HHPTJ04160200` (외인기관 추정가집계) 엔드포인트 추가 — 장중 당일 실시간 외국인/기관 수급
  2. `program_net_1d` 필드 추가 — `inquire-price`의 `pgtr_ntby_qty`로 종목별 프로그램 매매 수집
  3. 리포트 3개 모드에 프로그램 매매 표시 ("💻 프로그램: ±N만주")
  4. 수집 우선순위: HHPTJ04160200(장중 가집계) → FHKST01010900(전일 fallback)

### [버그픽스] 수급 데이터 4건 버그 수정 (2026-03-19 21:00 KST)
- 커밋: 91dc39f
- 변경 파일: `src/dual_source/sources/kis_source.py`, `src/dual_source/sources/api_source.py`, `src/dual_source/types.py`, `src/dual_source/validation_engine.py`, `src/alert_engine.py`, `src/analysis.py`, `src/crawler.py`
- 내용:
  1. KIS API `pgtr_ntby_qty`(프로그램매매)를 기관 순매수로 잘못 매핑하던 버그 수정 → `FHKST01010900`(투자자별 매매동향)의 `orgn_ntby_qty` 사용
  2. 전일 결산 데이터를 당일 데이터처럼 표시하던 문제 수정 → `data_date` 필드 추가, "(전일)" 라벨 표시, 전일 데이터 쌍끌이 판정 제외
  3. pykrx 미설치 해결
  4. 배치 캐시 경로 `data_date` 전달 누락 수정
- 원인: KIS `inquire-price`의 `frgn_ntby_qty`가 장중에 전일 결산값을 반환하고, `pgtr_ntby_qty`는 프로그램매매인데 기관으로 잘못 매핑

## 2026-03-14

### [기능] v3 리포트 시스템 전면 재설계 (2026-03-14 23:30 KST)
- 변경 파일: `src/main.py`, `src/alert_engine.py`(신규), `src/cross_project_data.py`(신규), `config/config.yaml`, `config/prompts/gemini_briefing_prompt_compact.txt`, `config/prompts/gemini_briefing_prompt.txt`, `docs/research/2026-03-14-report-improvement.md`, `docs/research/2026-03-14-report-optimization.md`
- 내용:
  - 3모드 리포트 시스템 도입 (평시/경보/주간)
  - 평시: AI 호출 없이 1메시지, 경보: 임계값 돌파 시 2메시지+AI, 주간: 월요일 심층분석
  - 보유 종목 전체 제거, 관심종목 SK하이닉스 1개로 집중
  - 프롬프트 v3 교체 (친절하고 상세한 톤, 반도체/HBM 전문)
  - cross_project_data.py로 theme_analysis/signal_analysis 데이터 활용
  - 행동재무학 기반 설계 (정보 과부하 방지, 비행동 우선)

### [설정] phase1 소스 상태 정리 커밋 (2026-03-14 22:00 KST)
- 커밋: d920220
- 내용: CLAUDE.md 가이드라인, KIS 토큰/환율 API 개선사항, Supabase 문서 등 일괄 정리

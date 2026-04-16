# Task History

## 2026-04-15

### [진단] 포트폴리오 Update UX 리서치 (2026-04-15 15:30 KST)
- 변경 파일: `docs/research/2026-04-15-portfolio-update.md`
- 내용: `/pf` 봇이 CRD만 지원(Update 부재) 문제 진단. 기존 대화형 UX 유지하며 `UPDATE_SELECT_STOCK/FIELD/INPUT/CONFIRM` 4개 상태 추가안. `PortfolioManager.update(id, field, value)` API 스펙. 구현 체크리스트 8항목.

### [진단] 리포트 실효성 개선 리서치 (2026-04-15 15:25 KST)
- 변경 파일: `docs/research/2026-04-15-report-effectiveness.md`
- 내용: "특이사항 없는 하루" 반복 원인 진단. **핵심 발견: `settings.tickers_interest_domestic`가 공백이어서 `_extract_stock_analysis_results()`가 빈 리스트 반환 → 본문 자체가 비어있음**. 4축 개선안(P0 분석대상 버그, P1 톤 전환/동적 헤드라인, P2 yellow 모드). Yellow 임계값 테이블, 관찰·행동 템플릿 12개, 헤드라인 우선순위 알고리즘.

### [기능] Supabase 포트폴리오에 셀트리온 추가 (2026-04-15 15:10 KST)
- 변경 파일: Supabase `portfolio` 테이블 (코드 변경 없음)
- 내용: 셀트리온(068270.KS) 보유 카테고리로 추가 — 매수가 202,500원, 9주, 매수일 2026-04-15. 삼성전자(005930.KS)는 기 등록 상태 확인. 최종 보유 3종목: SK하이닉스/삼성전자/셀트리온.
- 비고: 현재 `main.py:125-131`이 `tickers_interest_domestic`만 참조해 등록된 보유 종목이 분석 대상에 미포함 — research 문서 P0 항목으로 반영됨.

## 2026-04-06

### [진단] AI 프롬프트 품질 고도화 리서치 (2026-04-06 23:30 KST)
- 변경 파일: `docs/research/2026-04-06-ai-prompt-enhancement.md`
- 내용: 10개 카테고리(CoT/ToT/Self-Consistency, 편향교정, 페르소나, 인과분석, 리스크정량화, 멀티에이전트, 뉴스해석, 매크로내러티브, Confidence Calibration, 기타) 웹 리서치. 구체적 프롬프트 예시 및 우선순위 정리.

### [기능] 리포트 투자 지표 고도화 (2026-04-06 22:30 KST)
- 변경 파일: `src/analysis.py`, `src/alert_engine.py`
- 내용:
  1. 9개 지표 함수 추가 (볼린저밴드, 스토캐스틱, OBV, ATR, 골든/데드크로스, 거래량이상, 공매도, PER/PBR, MDD/베타)
  2. 평시/경보/주간 3모드 리포트에 반영 (평시: 이상 징후만, 주간: 전체)
  3. 포트폴리오 매수가 대비 수익률 표시

### [기능] 텔레그램 포트폴리오 CRUD 봇 (2026-04-06 21:30 KST)
- 변경 파일: `src/telegram_bot.py`(신규), `src/portfolio_manager.py`(신규), `src/stock_search.py`(신규), `src/__main__.py`(신규), `config/settings.py`, `requirements.txt`
- 내용:
  1. `/pf` 명령어로 인라인 버튼 기반 보유/관심 종목 CRUD
  2. Supabase `portfolio` 테이블 primary, config.yaml fallback
  3. 종목 검색: 네이버 금융 크롤링 3,800+ 종목 캐시 (한글), yfinance (영문)
  4. settings.py가 Supabase 포트폴리오를 자동 로드하여 리포트 연동
  5. 실행: `python -m src`

### [진단] 투자 리포트 품질 고도화 리서치 (2026-04-06 21:00 KST)
- 변경 파일: `docs/research/2026-04-06-report-enhancement.md`
- 내용: 8개 카테고리(수익률 분석, 기술 지표, 밸류에이션, 옵션/선물, 섹터, 리스크, 센티먼트, 타이밍) 웹 리서치. 우선순위 정리.

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

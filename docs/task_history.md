# Task History

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

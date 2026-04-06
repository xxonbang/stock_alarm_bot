# 포트폴리오 CRUD 텔레그램 봇 설계

## 개요
텔레그램 인라인 버튼 기반 포트폴리오(보유/관심 종목) CRUD 기능.
Supabase를 primary 저장소로, config.yaml을 fallback으로 사용.

## 데이터 모델

**Supabase `portfolio` 테이블:**

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | uuid (PK) | 자동생성 |
| ticker | text | 종목코드 (000660.KS, AAPL) |
| name | text | 종목명 |
| category | text | possession / interest |
| buy_price | numeric | 매수가 (nullable) |
| buy_quantity | integer | 매수수량 (nullable) |
| buy_date | date | 매수일자 (nullable) |
| market | text | domestic / overseas (자동판별) |
| created_at | timestamptz | 생성일 |
| updated_at | timestamptz | 수정일 |

market 자동판별: `.KS`/`.KQ` → domestic, 그 외 → overseas

## 텔레그램 봇 UX

- 진입: `/pf`
- 메인 메뉴: [보유종목 조회] [관심종목 조회] [종목 추가] [종목 삭제]
- 추가: 카테고리 선택 → 종목명 입력 → 검색결과 버튼 선택 → 매수정보 입력 → 완료
- 삭제: 종목 선택 버튼 → 확인 버튼
- 수정: 삭제 후 재등록 (MVP)
- 종목 검색: 한글 → pykrx, 영문 → yfinance

## 파일 구조

- `src/telegram_bot.py` — 봇 메인 (polling, 핸들러)
- `src/portfolio_manager.py` — Supabase CRUD + config.yaml fallback
- `src/stock_search.py` — 종목명 → 종목코드 검색
- `config/settings.py` — Supabase 포트폴리오 로드 추가
- `requirements.txt` — python-telegram-bot 추가

## 보안

- CHAT_ID 일치하는 사용자만 응답
- 기존 환경변수 재활용 (TELEGRAM_TOKEN, CHAT_ID)

## 실행

```bash
python -m src.telegram_bot
```

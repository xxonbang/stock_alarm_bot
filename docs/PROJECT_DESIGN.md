# Stock Insight Bot - 프로젝트 설계서

## 1. 프로젝트 개요

**프로젝트명:** Stock Insight Bot
**버전:** 2.0
**최종 업데이트:** 2026년 1월
**목적:** AI 기반 주식 투자 인사이트 자동 생성 및 텔레그램 알림 시스템

### 1.1 주요 기능 요약
- 국내/해외 주식 데이터 자동 수집 (yfinance, pykrx, KRX API)
- 기술적 지표 분석 (RSI, 이동평균선, 눌림목 판별)
- 시장 뉴스 및 매크로 경제 지표 수집
- Google Gemini AI를 활용한 투자 인사이트 생성
- 텔레그램 봇을 통한 리포트 자동 발송

---

## 2. 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                        Stock Insight Bot                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│  │   main.py   │───▶│  analysis.py │    │  crawler.py  │          │
│  │ (오케스트레이터) │    │ (기술적 분석) │    │ (데이터 수집) │          │
│  └─────────────┘    └─────────────┘    └─────────────┘          │
│         │                  │                  │                  │
│         │                  ▼                  ▼                  │
│         │           ┌─────────────────────────────┐              │
│         │           │    외부 데이터 소스          │              │
│         │           │ - yfinance (주가 데이터)    │              │
│         │           │ - pykrx (KRX 공식 데이터)   │              │
│         │           │ - KRX API (수급/ETF 데이터) │              │
│         │           │ - 네이버 금융 (뉴스)        │              │
│         │           │ - Yahoo Finance (해외 뉴스) │              │
│         │           │ - FRED API (매크로 지표)    │              │
│         │           └─────────────────────────────┘              │
│         │                                                        │
│         ▼                                                        │
│  ┌─────────────┐                                                │
│  │ai_researcher│                                                │
│  │ (AI 분석)   │◀──────────────────────────────────────────────│
│  └─────────────┘                                                │
│         │                                                        │
│         │    ┌─────────────┐                                    │
│         └───▶│  notifier.py │───▶ Telegram Bot                   │
│              │ (알림 발송)  │                                    │
│              └─────────────┘                                    │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 디렉토리 구조

```
trade_info_sender/
├── src/                          # 소스 코드
│   ├── __init__.py
│   ├── main.py                   # 메인 실행 파일 (오케스트레이터)
│   ├── analysis.py               # 기술적 분석 모듈
│   ├── crawler.py                # 데이터 수집 모듈
│   ├── ai_researcher.py          # AI 리서치 모듈
│   └── notifier.py               # 텔레그램 알림 모듈
├── config/                       # 설정 파일
│   ├── config.yaml               # 티커 목록 및 스케줄 설정
│   ├── settings.py               # 환경변수 로더
│   ├── ticker_names.py           # 티커 이름 매핑
│   └── prompts/                  # AI 프롬프트 템플릿
│       ├── gemini_briefing_prompt.txt
│       └── gemini_briefing_prompt_compact.txt
├── docs/                         # 문서
│   └── PROJECT_DESIGN.md         # 프로젝트 설계서
├── .github/                      # GitHub Actions 설정
│   └── workflows/
│       └── stock_analysis.yaml   # 자동 실행 워크플로우
├── requirements.txt              # Python 의존성
├── README.md                     # 프로젝트 설명
└── CLAUDE.md                     # Claude Code 지침
```

---

## 4. 기능 목록

### 4.1 데이터 수집 기능

| 기능 | 모듈 | 설명 |
|------|------|------|
| 주가 데이터 수집 | analysis.py | yfinance를 통한 국내/해외 주가 데이터 수집 |
| 수급 데이터 수집 | crawler.py | pykrx/KRX API를 통한 외국인/기관 순매매량 수집 |
| ETF 괴리율 수집 | crawler.py | KRX API를 통한 ETF NAV 괴리율 수집 |
| 시장 뉴스 수집 | crawler.py | 네이버/Yahoo Finance 뉴스 크롤링 |
| 매크로 지표 수집 | crawler.py | FRED API를 통한 경제 지표 수집 |
| 공포/탐욕 지수 | crawler.py | VIX 기반 시장 심리 지표 계산 |

### 4.2 분석 기능

| 기능 | 모듈 | 설명 |
|------|------|------|
| 기간별 수익률 계산 | analysis.py | 1일/3일/1주/1개월/3개월/6개월/1년 수익률 |
| RSI 계산 | analysis.py | Wilder's Smoothing 방식 RSI (14일) |
| 이동평균선 분석 | analysis.py | 20일/60일 이동평균선 및 괴리율 계산 |
| 눌림목 판별 | analysis.py | 4대 조건 기반 눌림목 발생 여부 판별 |
| 52주 신고가 위치 | analysis.py | 현재가의 52주 신고가 대비 위치 (%) |

### 4.3 AI 분석 기능

| 기능 | 모듈 | 설명 |
|------|------|------|
| Compact 리포트 생성 | ai_researcher.py | 모바일 최적화 간략 리포트 |
| Detailed 리포트 생성 | ai_researcher.py | 상세 분석 리포트 |
| API 키 Fallback | ai_researcher.py | 할당량 초과 시 대체 키 자동 전환 |
| 종목명 후처리 | ai_researcher.py | AI 응답에 종목명 자동 추가 |

### 4.4 알림 기능

| 기능 | 모듈 | 설명 |
|------|------|------|
| 메시지 발송 | notifier.py | 텔레그램 메시지 발송 |
| HTML 태그 처리 | notifier.py | 지원/미지원 HTML 태그 필터링 |
| 메시지 분할 | notifier.py | 4096자 초과 메시지 자동 분할 |

---

## 5. 프로세스 흐름

### 5.1 전체 실행 흐름

```
[Step 1] 주가 데이터 수집 및 요약
    │
    ├─▶ 보유 종목 (국내) 분석
    ├─▶ 보유 종목 (해외) 분석
    ├─▶ 관심 종목 (국내) 분석
    └─▶ 관심 종목 (해외) 분석
    │
[Step 2] 매크로 경제 지표 수집
    │
    ├─▶ FRED API (금리, 인플레이션 등)
    ├─▶ VIX 지수 및 공포/탐욕 지수
    └─▶ 주요 지수 (S&P500, KOSPI 등)
    │
[Step 2-1~2-5] 추가 데이터 수집
    │
    ├─▶ 미국 Top Movers (급등/급락)
    ├─▶ 한국 Hot Themes (테마주)
    ├─▶ 한경 컨센서스 (국내 시장 재료)
    ├─▶ Google News RSS (해외 시장 재료)
    └─▶ 기술적 분석 신호
    │
[Step 3] 시장 뉴스 수집
    │
    ├─▶ Yahoo Finance (해외)
    ├─▶ 네이버 금융 (국내)
    └─▶ 포트폴리오 관련성 필터링
    │
[Step 4] 뉴스 포맷팅 및 번역
    │
    └─▶ deep-translator로 영어 뉴스 한국어 번역
    │
[Step 4-1~4-2] Hot 뉴스 수집 및 번역
    │
[Step 5] 데이터 통합
    │
    └─▶ AI 분석용 구조화된 텍스트 생성
    │
[Step 6] AI 초기화
    │
    └─▶ Google Gemini 클라이언트 초기화
    │
[Step 7] AI 리포트 생성
    │
    ├─▶ Compact 리포트 생성
    └─▶ Detailed 리포트 생성
    │
[Step 8] 텔레그램 발송
    │
    ├─▶ 바리케이트 시작 메시지
    ├─▶ 카테고리별 주가 정보
    ├─▶ 매크로 경제 지표
    ├─▶ 시장 뉴스
    ├─▶ Hot 뉴스
    ├─▶ AI 인사이트 (Compact)
    ├─▶ AI 인사이트 (Detailed)
    └─▶ 바리케이트 종료 메시지
```

### 5.2 수급 데이터 수집 흐름 (Fallback 메커니즘)

```
[1순위] pykrx 라이브러리
    │
    ├─▶ 성공 → 데이터 반환
    └─▶ 실패 → 2순위로 진행
    │
[2순위] KRX API (공식 API)
    │
    ├─▶ 성공 → 데이터 반환
    └─▶ 실패 (401 등) → 3순위로 진행
    │
[3순위] 네이버 금융 크롤링
    │
    ├─▶ 성공 → 데이터 반환
    └─▶ 실패 → None 반환
```

---

## 6. 핵심 모듈 상세

### 6.1 main.py - 오케스트레이터

**목적:** 전체 프로세스 조율 및 실행 순서 관리

**주요 기능:**
- 각 모듈 호출 순서 관리
- 수집된 데이터 통합
- 텔레그램 메시지 발송 순서 관리
- KRX API 상태 확인 및 경고 메시지 처리

**핵심 함수:**
```python
def main():
    """메인 실행 함수 - 전체 워크플로우 오케스트레이션"""
```

---

### 6.2 analysis.py - 기술적 분석 모듈

**목적:** 순수 수치 계산 전용 모듈 (AI API 호출 금지)

**주요 기능:**
- yfinance 데이터 캐싱 (중복 호출 방지)
- 기술적 지표 계산 (RSI, MA, 괴리율)
- 눌림목 판별 로직
- 멀티스레딩 기반 병렬 분석

**핵심 함수:**

| 함수명 | 목적 |
|--------|------|
| `calculate_rsi()` | Wilder's Smoothing 방식 RSI 계산 |
| `calculate_pullback_status()` | 눌림목 4대 조건 판별 |
| `calculate_returns()` | 기간별 수익률 및 종합 데이터 수집 |
| `get_technical_indicators()` | 기술적 지표 통합 계산 |
| `analyze_all_tickers()` | 멀티스레딩 기반 전체 종목 분석 |
| `get_stock_summary_by_category()` | 카테고리별 주가 요약 생성 |
| `format_stock_summary_by_category()` | 텔레그램용 메시지 포맷팅 |

**데이터 캐싱:**
```python
_yfinance_cache = {}  # {ticker: {'hist_data': DataFrame, 'info': dict, 'timestamp': datetime}}
_CACHE_TTL_SECONDS = 3600  # 1시간
```

---

### 6.3 crawler.py - 데이터 수집 모듈

**목적:** 외부 데이터 소스에서 시장 정보 수집

**주요 기능:**
- 시장 뉴스 수집 (Yahoo, 네이버, Google RSS)
- 매크로 경제 지표 수집 (FRED API)
- 수급 데이터 수집 (pykrx, KRX API, 네이버)
- 뉴스 필터링 및 번역

**핵심 함수:**

| 함수명 | 목적 |
|--------|------|
| `get_supply_demand_pykrx()` | pykrx 기반 외국인/기관 순매매량 수집 |
| `get_kr_stock_data_krx_api()` | KRX API 기반 수급 데이터 수집 |
| `get_kr_stock_data()` | 수급 데이터 통합 수집 (Fallback 메커니즘) |
| `get_market_news_with_context()` | 시장 뉴스 수집 및 필터링 |
| `get_market_indicators()` | 매크로 경제 지표 수집 |
| `get_fear_greed_index()` | VIX 기반 공포/탐욕 지수 계산 |
| `translate_headlines()` | 영어 뉴스 한국어 번역 |
| `filter_relevant_news()` | 포트폴리오 관련 뉴스 필터링 |

**API 캐싱:**
```python
_krx_api_cache = {}      # KRX API 응답 캐시
_krx_etf_api_cache = {}  # KRX ETF API 응답 캐시
```

---

### 6.4 ai_researcher.py - AI 리서치 모듈

**목적:** Google Gemini AI를 활용한 투자 인사이트 생성

**주요 기능:**
- Gemini 2.5 Flash 모델 활용
- Compact/Detailed 두 가지 리포트 형식 지원
- API 키 Fallback (할당량 초과 시 자동 전환)
- Exponential Backoff (Rate Limit 대응)
- 종목 코드 → 종목명 자동 변환

**핵심 함수:**

| 함수명 | 목적 |
|--------|------|
| `_call_ai()` | AI API 호출 (재시도 및 에러 핸들링) |
| `generate_briefing()` | Compact + Detailed 리포트 동시 생성 |
| `_add_stock_names_to_codes()` | AI 응답에 종목명 후처리 |
| `_switch_to_fallback()` | API 키 자동 전환 |

**에러 처리:**
- Rate Limit: 10초 → 30초 → 60초 → 120초 → 180초 대기
- DNS 오류: 5초 → 10초 → 20초 → 30초 → 60초 대기
- Quota 초과: Fallback 키로 자동 전환

---

### 6.5 notifier.py - 텔레그램 알림 모듈

**목적:** 텔레그램을 통한 리포트 발송

**주요 기능:**
- HTML 파싱 모드 지원
- 4096자 초과 메시지 자동 분할
- HTML 태그 유효성 검증 및 수정

**핵심 함수:**

| 함수명 | 목적 |
|--------|------|
| `send_message()` | 메시지 발송 (자동 분할 포함) |
| `_clean_html_tags()` | 미지원 HTML 태그 제거 |
| `_split_html_message()` | HTML 태그 고려한 메시지 분할 |

---

## 7. 설정 파일

### 7.1 config.yaml - 티커 및 스케줄 설정

```yaml
# 보유 종목 (국내/해외)
tickers_possession_domestic:
  - "360200.KS"  # ACE 미국S&P500
  - "379810.KS"  # KODEX 미국나스닥100
  # ...

tickers_possession_overseas: []

# 관심 종목 (국내/해외)
tickers_interest_domestic:
  - "449170.KS"  # TIGER KOFR금리액티브
  - "005930.KS"  # 삼성전자
  # ...

tickers_interest_overseas:
  - "TSLA"
  - "NVDA"
  # ...

# 스케줄 설정
schedule_times:
  - "08:00"
  - "18:00"
```

### 7.2 환경변수 (GitHub Secrets / .env)

| 변수명 | 필수 | 설명 |
|--------|------|------|
| `TELEGRAM_TOKEN` | O | 텔레그램 봇 토큰 |
| `CHAT_ID` | O | 텔레그램 채팅 ID |
| `GOOGLE_API_KEY_01` | O | Google AI API 키 (기본) |
| `GOOGLE_API_KEY_02` | X | Google AI API 키 (Fallback) |
| `KRX_API_KEY` | X | KRX Open API 키 |
| `KRX_API_KEY_EXPIRY` | X | KRX API 키 만료일 (YYYY-MM-DD) |

---

## 8. 의존성

### 8.1 Python 패키지 (requirements.txt)

| 패키지 | 버전 | 용도 |
|--------|------|------|
| yfinance | >=1.0.0,<2.0.0 | 주가 데이터 수집 |
| pykrx | >=1.0.0 | KRX 공식 데이터 수집 |
| google-genai | >=1.0.0 | Google Gemini AI |
| curl_cffi | >=0.7.0 | TLS Fingerprint 우회 |
| beautifulsoup4 | >=4.11.1 | 웹 크롤링 |
| PyYAML | >=6.0.1 | 설정 파일 파싱 |
| python-dotenv | >=1.0.0 | 환경변수 로드 |
| fredapi | >=0.5.1 | FRED API |
| feedparser | >=6.0.10 | RSS 피드 파싱 |
| deep-translator | >=1.11.4 | 뉴스 번역 |
| urllib3 | >=2.0.0 | HTTP 클라이언트 |

---

## 9. 성능 최적화

### 9.1 캐싱 전략

- **yfinance 데이터 캐시:** TTL 1시간, 중복 API 호출 방지
- **KRX API 캐시:** 일일 단위 캐싱 (API 호출 제한 대응)
- **뉴스 데이터:** 메모리 캐시 (세션 단위)

### 9.2 병렬 처리

- **ThreadPoolExecutor:** 최대 10개 스레드로 티커별 병렬 분석
- **멀티스레드 안전:** Lock 기반 캐시 접근 제어

### 9.3 에러 복원력

- **Exponential Backoff:** API Rate Limit 대응
- **Multi-tier Fallback:** pykrx → KRX API → 네이버 크롤링
- **API 키 자동 전환:** 할당량 초과 시 대체 키 사용

---

## 10. 확장 가이드

### 10.1 새 데이터 소스 추가

1. `crawler.py`에 새 수집 함수 추가
2. `main.py`의 실행 흐름에 호출 추가
3. 수집된 데이터를 `collected_data`에 통합

### 10.2 새 기술적 지표 추가

1. `analysis.py`에 계산 함수 추가
2. `get_technical_indicators()`에 결과 통합
3. `format_stock_summary_by_category()`에 표시 로직 추가

### 10.3 새 티커 추가

1. `config/config.yaml`에 티커 추가
2. `config/ticker_names.py`에 한글 이름 매핑 추가

---

## 11. 버전 히스토리

| 버전 | 날짜 | 주요 변경사항 |
|------|------|---------------|
| 2.0 | 2026-01 | pykrx 도입, zoneinfo 적용, 코드 정리 |
| 1.5 | 2025-12 | Gemini 2.5 Flash 적용, Dual-report 시스템 |
| 1.0 | 2025-10 | 초기 버전 |

---

*이 문서는 2026년 1월 기준으로 작성되었습니다.*

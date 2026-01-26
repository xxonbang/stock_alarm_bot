# 데이터 소스 및 수집 방식 가이드

## 개요

이 프로젝트는 다양한 소스에서 주식 시장 데이터를 수집하여 AI 분석을 통해 투자 인사이트를 제공합니다.

```
┌─────────────────────────────────────────────────────────────┐
│                     데이터 수집 흐름                          │
├─────────────────────────────────────────────────────────────┤
│  [주가/기술지표]  [수급데이터]  [뉴스]  [매크로]  [AI분석]    │
│       │              │          │        │         │        │
│   yfinance      Dual Source   RSS     FRED    Gemini       │
│                  │      │    크롤링   yfinance  Vision      │
│              Agentic   API                                  │
│            (Screenshot) (pykrx)                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 1. 주가 및 기술 지표

### 1.1 yfinance API

| 항목 | 내용 |
|------|------|
| **파일** | `src/analysis.py` |
| **방식** | REST API (Yahoo Finance) |
| **라이브러리** | `yfinance` |

**수집 데이터:**
- 현재가, 전일 종가, 전일비 (%)
- 거래량, 평균 거래량
- 52주 최고가/최저가
- 수익률 (1주, 1개월, 3개월, 6개월, 1년)

**기술 지표 (자체 계산):**
| 지표 | 계산 방식 | 용도 |
|------|----------|------|
| RSI | Wilder's Smoothing (14일) | 과매수/과매도 판단 |
| MACD | EMA(12) - EMA(26), Signal(9) | 추세 전환 신호 |
| 이동평균 | MA20, MA50, MA200 | 지지/저항선 |
| 괴리율 | (현재가 - MA) / MA × 100 | 평균 회귀 판단 |

**주요 함수:**
```python
get_stock_data(ticker)           # 기본 주가 정보
calculate_returns(ticker)        # 기간별 수익률
calculate_rsi(data, period=14)   # RSI 계산
calculate_macd(data)             # MACD 계산
get_technical_indicators(ticker) # 모든 기술 지표
```

---

## 2. 수급 데이터 (외국인/기관 순매매)

### 2.1 Dual Source System (병렬 수집)

두 가지 독립적인 소스에서 병렬로 수집 후 교차 검증합니다.

```
┌──────────────────────────────────────────────────────────┐
│                 DualSourceCollector                       │
│                                                          │
│  ┌─────────────────┐      ┌─────────────────┐           │
│  │   Source A      │      │   Source B      │           │
│  │   (Agentic)     │      │   (API)         │           │
│  │                 │      │                 │           │
│  │ Playwright      │      │ pykrx (1순위)   │           │
│  │     ↓           │      │     ↓           │           │
│  │ Screenshot      │      │ KRX API (2순위) │           │
│  │     ↓           │      │     ↓           │           │
│  │ Gemini Vision   │      │ 네이버 (3순위)  │           │
│  └────────┬────────┘      └────────┬────────┘           │
│           │                        │                     │
│           └────────┬───────────────┘                     │
│                    ↓                                     │
│           ┌────────────────┐                            │
│           │ Validation     │                            │
│           │ Engine         │                            │
│           │ (교차 검증)    │                            │
│           └────────────────┘                            │
└──────────────────────────────────────────────────────────┘
```

---

### 2.2 Source A: Agentic Screenshot

| 항목 | 내용 |
|------|------|
| **파일** | `src/dual_source/sources/agentic_source.py` |
| **방식** | 브라우저 스크린샷 → AI Vision 분석 |
| **라이브러리** | `playwright`, `google-genai` |

**수집 과정:**
1. Playwright로 네이버 금융 페이지 렌더링
2. 수급 데이터 테이블 스크린샷 캡처
3. Gemini Vision AI로 이미지에서 데이터 추출
4. JSON 형식으로 파싱

**수집 데이터:**
- 외국인 순매매량 (1일, 3일 합계)
- 기관 순매매량 (1일, 3일 합계)
- ETF NAV 괴리율 (%)

**장점:**
- CSS 셀렉터 하드코딩 불필요
- 웹사이트 구조 변경에 자동 적응

**단점:**
- 상대적으로 느림 (5-10초/요청)
- Vision AI API 비용 발생

---

### 2.3 Source B: Traditional API

| 항목 | 내용 |
|------|------|
| **파일** | `src/dual_source/sources/api_source.py` |
| **방식** | Fallback Chain (API → 크롤링) |

**Fallback 순서:**

| 순위 | 소스 | 방식 | 특징 |
|------|------|------|------|
| 1 | pykrx | Python 라이브러리 | 가장 빠름, 안정적 |
| 2 | KRX API | REST API | 공식 데이터, 인증 필요 |
| 3 | 네이버 금융 | HTML 크롤링 | 최후 수단 |

**pykrx:**
```python
from pykrx import stock
df = stock.get_market_trading_volume_by_date(start, end, code)
```

**KRX API:**
```
URL: https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd
인증: AUTH_KEY 헤더
```

**네이버 금융 크롤링:**
```
URL: https://finance.naver.com/item/frgn.naver?code={code}
인코딩: EUC-KR
파싱: BeautifulSoup (HTML Table)
```

---

### 2.4 Validation Engine

| 항목 | 내용 |
|------|------|
| **파일** | `src/dual_source/validation_engine.py` |
| **기능** | 두 소스 데이터 교차 검증 및 병합 |

**신뢰도 계산:**
| 상태 | 신뢰도 | 설명 |
|------|--------|------|
| MATCH | 98% | 두 소스 일치 |
| PARTIAL | 85% | 부분 일치 |
| CONFLICT | 70% | 데이터 충돌 |
| SINGLE | 65% | 단일 소스만 성공 |

---

## 3. 뉴스 데이터

### 3.1 포트폴리오 관련 뉴스

| 항목 | 내용 |
|------|------|
| **파일** | `src/crawler.py` |
| **함수** | `get_market_news_with_context()` |

**소스:**

| 소스 | URL | 방식 |
|------|-----|------|
| Yahoo Finance | `feeds.finance.yahoo.com/rss/2.0/headline` | RSS (feedparser) |
| 네이버 금융 | `finance.naver.com/news/news_list.naver` | HTML 크롤링 |

**필터링 점수:**
| 조건 | 점수 |
|------|------|
| 포트폴리오 종목 매칭 | +5점 |
| 시장 키워드 (Fed, AI, 반도체 등) | +2점 |
| **최소 기준** | 2점 이상 |

---

### 3.2 Hot 뉴스 (인기 뉴스)

| 항목 | 내용 |
|------|------|
| **함수** | `get_hot_news()` |

**해외 뉴스 소스:**
| 소스 | 방식 |
|------|------|
| Bloomberg | RSS |
| CNBC | RSS |
| Reuters | RSS |
| WSJ | RSS |
| Yahoo Finance | RSS / yfinance `.news` |

**국내 뉴스:**
- 네이버 금융 (필터링 없이 상위 뉴스)

---

### 3.3 Google News RSS

| 항목 | 내용 |
|------|------|
| **함수** | `get_google_news_rss()` |
| **방식** | Google News RSS API |
| **용도** | 특정 종목/키워드 뉴스 집계 |

---

## 4. 매크로 경제 데이터

### 4.1 FRED API (연준 경제 지표)

| 항목 | 내용 |
|------|------|
| **파일** | `src/crawler.py` |
| **함수** | `get_fred_macro_data()` |
| **API** | Federal Reserve Economic Data |

**수집 지표:**
| 코드 | 지표명 | 용도 |
|------|--------|------|
| DGS10 | 미국 10년물 국채 | 무위험 수익률 |
| T10Y2Y | 10Y-2Y 수익률 곡선 | 경기 침체 신호 |
| BAMLH0A0HYM2 | 하이일드 스프레드 | 신용 위험 |
| T10YIE | 기대 인플레이션 | 물가 전망 |

---

### 4.2 yfinance 기반 시장 지표

| 항목 | 내용 |
|------|------|
| **함수** | `get_market_indicators()` |

**수집 데이터:**
| 티커 | 지표명 |
|------|--------|
| ^TNX | 미국 10년물 금리 |
| CL=F | WTI 원유 선물 |
| GC=F | 금 선물 |
| ^VIX | 변동성 지수 |
| KRW=X | 원/달러 환율 |

---

### 4.3 공포/탐욕 지수

| 항목 | 내용 |
|------|------|
| **함수** | `get_fear_greed_index()` |

**수집 방식:**
| 순위 | 방식 | 상세 |
|------|------|------|
| 1 | CNN API | `production.dataviz.cnn.io/index/fearandgreed/graphdata` |
| 2 | 자체 계산 | VIX(40%) + S&P500 RSI(40%) + 기타(20%) |

**분류:**
- 0-25: Extreme Fear
- 25-45: Fear
- 45-55: Neutral
- 55-75: Greed
- 75-100: Extreme Greed

---

### 4.4 미국 Top Movers

| 항목 | 내용 |
|------|------|
| **함수** | `get_us_top_movers()` |
| **URL** | `finance.yahoo.com/gainers` |
| **방식** | HTML 크롤링 |
| **필터** | 가격 $5 이상, 양수 등락률 |

---

### 4.5 한국 핫 테마

| 항목 | 내용 |
|------|------|
| **함수** | `get_korea_hot_themes()` |
| **URL** | `finance.naver.com/sise/theme/` |
| **방식** | HTML 크롤링 |
| **데이터** | 테마명, 등락률, 구성 종목 |

---

## 5. AI 분석

### 5.1 Gemini Vision (스크린샷 분석)

| 항목 | 내용 |
|------|------|
| **파일** | `src/dual_source/sources/agentic_source.py` |
| **모델** | Gemini 2.5 Flash |
| **용도** | 네이버 금융 스크린샷에서 수급 데이터 추출 |

---

### 5.2 AI 리서처 (리포트 생성)

| 항목 | 내용 |
|------|------|
| **파일** | `src/ai_researcher.py` |
| **모델** | Gemini 2.5 Flash |
| **입력** | 모든 수집 데이터 통합 |
| **출력** | Compact 리포트 + Detailed 리포트 |

**API 키 관리:**
- 공유 키 매니저 (`GoogleAPIKeyManager`)
- 최대 3개 키 순환 사용
- 할당량 초과 시 자동 Fallback

---

## 6. 크롤링 기술

### 6.1 TLS Fingerprint 우회

| 항목 | 내용 |
|------|------|
| **라이브러리** | `curl_cffi` |
| **방식** | Chrome 브라우저 TLS 지문 복제 |
| **옵션** | `impersonate="chrome120"` |
| **목적** | CloudFlare 등 봇 차단 우회 |

```python
from curl_cffi.requests import Session
session = Session(impersonate="chrome120")
response = session.get(url, headers=headers)
```

---

### 6.2 User-Agent 위장

```python
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36...',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8',
    'Referer': 'https://www.google.com/'
}
```

---

### 6.3 인코딩 처리

| 사이트 | 인코딩 |
|--------|--------|
| 네이버 금융 | EUC-KR |
| Yahoo Finance | UTF-8 |
| Google News | UTF-8 |

---

## 7. 오류 처리

### 7.1 재시도 정책

| 상황 | 재시도 | 대기 시간 |
|------|--------|----------|
| DNS 실패 | 5회 | 5→10→20→30→60초 |
| 타임아웃 | 5회 | 5→10→20→30→60초 |
| Rate Limit (429) | 5회 | 10→30→60→120→180초 |
| Quota 초과 | 키 전환 | 즉시 다음 키 |

---

### 7.2 KRX API 상태 추적

| 항목 | 내용 |
|------|------|
| **함수** | `get_krx_api_status()` |
| **만료 감지** | 401 오류 또는 유효기간 확인 |
| **경고** | 7일 이내 만료 시 알림 |
| **Fallback** | 네이버 크롤링으로 전환 |

---

## 8. 파일별 데이터 소스 요약

| 파일 | 주요 소스 | 데이터 종류 |
|------|----------|-----------|
| `analysis.py` | yfinance | 주가, 기술 지표, 수익률 |
| `crawler.py` | RSS, 크롤링, FRED, yfinance | 뉴스, 매크로 지표 |
| `dual_source/sources/agentic_source.py` | Playwright + Gemini Vision | 수급 데이터 (스크린샷) |
| `dual_source/sources/api_source.py` | pykrx, KRX API, 크롤링 | 수급 데이터 (API) |
| `ai_researcher.py` | Gemini 2.5 Flash | AI 분석 리포트 |

---

## 9. 환경 변수

| 변수명 | 용도 | 필수 |
|--------|------|------|
| `GOOGLE_API_KEY_01` | Gemini API (기본) | O |
| `GOOGLE_API_KEY_02` | Gemini API (Fallback 1) | X |
| `GOOGLE_API_KEY_03` | Gemini API (Fallback 2) | X |
| `KRX_API_KEY` | KRX OpenAPI | X |
| `KRX_API_KEY_EXPIRY` | KRX API 만료일 | X |
| `TELEGRAM_TOKEN` | 텔레그램 봇 | O |
| `CHAT_ID` | 텔레그램 채팅 ID | O |

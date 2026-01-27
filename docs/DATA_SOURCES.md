# 데이터 소스 및 수집 방식 가이드

## 개요

이 프로젝트는 다양한 소스에서 주식 시장 데이터를 수집하여 AI 분석을 통해 투자 인사이트를 제공합니다.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        데이터 수집 흐름 (v2.0)                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  [한국 주식]              [미국 주식]              [AI 분석]             │
│       │                       │                       │                │
│  KIS API (1순위)        Yahoo Chart (1순위)      Gemini 2.5 Flash      │
│       ↓                       ↓                       │                │
│  pykrx (2순위)          yfinance (기관보유)      (다중 키 관리)         │
│       ↓                       ↓                                        │
│  KRX API (3순위)        Twelve Data (백업)                             │
│       ↓                       ↓                                        │
│  네이버 크롤링           Finnhub/FMP                                    │
│                                                                         │
│  [뉴스]                 [매크로]                 [수급 검증]            │
│    │                       │                       │                   │
│  RSS (7개 소스)         FRED API              Dual Source             │
│  네이버 크롤링          yfinance 지표         (Agentic + API)          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 1. 한국 주식 데이터 (Fallback Chain)

### 1.1 수집 순서

```
┌─────────────────────────────────────────────────────────────┐
│                  한국 주식 Fallback Chain                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1순위: KIS API (한국투자증권)                               │
│         └─ 공식 증권사 API, 실시간 수급                      │
│                    ↓ 실패 시                                │
│  2순위: pykrx                                               │
│         └─ 무료, 안정적, Python 라이브러리                   │
│                    ↓ 실패 시                                │
│  3순위: KRX API (한국거래소)                                 │
│         └─ 공식 API, 인증 필요                              │
│                    ↓ 실패 시                                │
│  4순위: 네이버 금융 크롤링                                   │
│         └─ 최종 폴백, HTML 파싱                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 KIS API (한국투자증권) - 1순위

| 항목 | 내용 |
|------|------|
| **파일** | `src/dual_source/sources/kis_source.py` |
| **방식** | REST API (OAuth2 토큰 인증) |
| **Base URL** | `https://openapi.koreainvestment.com:9443` |

**인증 흐름:**
```
1. POST /oauth2/tokenP (토큰 발급)
2. 토큰 캐싱 (24시간 유효)
3. Bearer 토큰으로 API 호출
4. 401 오류 시 자동 재발급
```

**수집 데이터:**
- 외국인 순매수량 (`frgn_ntby_qty`)
- 기관 순매수량 (`pgtr_ntby_qty`)
- 거래량, 52주 고저가, PER, PBR

**환경변수:**
- `KIS_APP_KEY`: 앱키
- `KIS_APP_SECRET`: 앱 시크릿

---

### 1.3 pykrx - 2순위

| 항목 | 내용 |
|------|------|
| **방식** | Python 라이브러리 |
| **장점** | 무료, 빠름, 안정적 |

```python
from pykrx import stock
df = stock.get_market_trading_volume_by_date(start, end, code)
```

---

### 1.4 KRX API - 3순위

| 항목 | 내용 |
|------|------|
| **URL** | `https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd` |
| **인증** | AUTH_KEY 헤더 |
| **제한** | 일일 10,000회 |

---

### 1.5 네이버 금융 크롤링 - 4순위

| 항목 | 내용 |
|------|------|
| **URL** | `https://finance.naver.com/item/frgn.naver?code={code}` |
| **인코딩** | EUC-KR |
| **파싱** | BeautifulSoup |

---

## 2. 미국 주식 데이터 (Fallback Chain)

### 2.1 수집 순서

```
┌─────────────────────────────────────────────────────────────┐
│                  미국 주식 Fallback Chain                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1순위: Yahoo Chart API (Direct)                            │
│         └─ crumb 불필요, ~250ms, 안정적                     │
│                    ↓ 실패 시                                │
│  2순위: yfinance (기관보유 전용)                             │
│         └─ institutionalHolders (Chart API 미제공)          │
│                    ↓ 실패 시                                │
│  3순위: Twelve Data                                         │
│         └─ 800 calls/day, 안정적                            │
│                    ↓ 실패 시                                │
│  4순위: Finnhub                                             │
│         └─ 60 calls/min                                     │
│                    ↓ 실패 시                                │
│  5순위: FMP (기관보유 백업)                                  │
│         └─ 250 calls/day, 기관보유 제공                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Yahoo Chart API (Direct) - 1순위 ⭐

| 항목 | 내용 |
|------|------|
| **파일** | `src/dual_source/sources/yahoo_chart_source.py` |
| **방식** | REST API (Direct 호출) |
| **Base URL** | `https://query1.finance.yahoo.com/v8/finance/chart` |

**핵심 장점:**
- **crumb 토큰 불필요** → Rate Limit에 강함
- **~250ms 응답** (yfinance ~900ms 대비 3-4배 빠름)
- **장기 운영 안정성** (토큰 만료 없음)

**요청 예시:**
```python
url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
params = {'interval': '1d', 'range': '6mo'}
response = requests.get(url, params=params, headers=HEADERS)
```

**수집 데이터:**
- 현재가, 전일 종가, 변동률
- 거래량, 평균 거래량 (20일)
- 52주 최고가/최저가
- OHLCV 히스토리컬 데이터

---

### 2.3 yfinance - 2순위 (기관보유 전용)

| 항목 | 내용 |
|------|------|
| **파일** | `src/dual_source/sources/api_source.py` |
| **방식** | Python 라이브러리 |
| **용도** | 기관보유 데이터 (Chart API 미제공) |

```python
import yfinance as yf
stock = yf.Ticker(ticker)
institutional = stock.info.get('heldPercentInstitutions')
```

**주의:** crumb 토큰 의존으로 Rate Limit 발생 가능

---

### 2.4 Twelve Data - 3순위

| 항목 | 내용 |
|------|------|
| **파일** | `src/dual_source/sources/twelvedata_source.py` |
| **Base URL** | `https://api.twelvedata.com` |
| **제한** | 800 calls/day (무료) |

**환경변수:** `TWELVE_DATA_API_KEY`

---

### 2.5 Finnhub - 4순위

| 항목 | 내용 |
|------|------|
| **파일** | `src/dual_source/sources/finnhub_source.py` |
| **Base URL** | `https://finnhub.io/api/v1` |
| **제한** | 60 calls/min (무료) |

**환경변수:** `FINNHUB_API_KEY`

---

### 2.6 FMP (Financial Modeling Prep) - 5순위

| 항목 | 내용 |
|------|------|
| **파일** | `src/dual_source/sources/fmp_source.py` |
| **Base URL** | `https://financialmodelingprep.com/stable` |
| **제한** | 250 calls/day (무료) |
| **용도** | 기관보유 데이터 백업 |

**환경변수:** `FMP_API_KEY`

---

## 3. 수급 데이터 교차 검증 (Dual Source)

### 3.1 Dual Source System

```
┌──────────────────────────────────────────────────────────┐
│                 DualSourceCollector                       │
│                                                          │
│  ┌─────────────────┐      ┌─────────────────┐           │
│  │   Source A      │      │   Source B      │           │
│  │   (Agentic)     │      │   (API)         │           │
│  │                 │      │                 │           │
│  │ Playwright      │      │ KIS (1순위)     │           │
│  │     ↓           │      │     ↓           │           │
│  │ Screenshot      │      │ pykrx (2순위)   │           │
│  │     ↓           │      │     ↓           │           │
│  │ Gemini Vision   │      │ KRX API (3순위) │           │
│  │                 │      │     ↓           │           │
│  │                 │      │ 네이버 (4순위)  │           │
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

### 3.2 Source A: Agentic Screenshot

| 항목 | 내용 |
|------|------|
| **파일** | `src/dual_source/sources/agentic_source.py` |
| **방식** | 브라우저 스크린샷 → AI Vision 분석 |
| **라이브러리** | `playwright`, `google-genai` |

**장점:**
- CSS 셀렉터 하드코딩 불필요
- 웹사이트 구조 변경에 자동 적응

---

### 3.3 Validation Engine

| 상태 | 신뢰도 | 설명 |
|------|--------|------|
| MATCH | 98% | 두 소스 일치 |
| PARTIAL | 85% | 부분 일치 |
| CONFLICT | 70% | 데이터 충돌 |
| SINGLE | 65% | 단일 소스만 성공 |

---

## 4. 뉴스 데이터

### 4.1 해외 뉴스 소스 (RSS)

| 소스 | 방식 |
|------|------|
| Bloomberg | RSS |
| CNBC | RSS |
| Reuters | RSS |
| WSJ | RSS |
| Yahoo Finance | RSS / yfinance `.news` |

### 4.2 국내 뉴스

| 소스 | 방식 |
|------|------|
| 네이버 금융 | HTML 크롤링 |
| Google News RSS | RSS API |

---

## 5. 매크로 경제 데이터

### 5.1 FRED API

| 코드 | 지표명 | 용도 |
|------|--------|------|
| DGS10 | 미국 10년물 국채 | 무위험 수익률 |
| T10Y2Y | 10Y-2Y 수익률 곡선 | 경기 침체 신호 |
| BAMLH0A0HYM2 | 하이일드 스프레드 | 신용 위험 |
| T10YIE | 기대 인플레이션 | 물가 전망 |

### 5.2 시장 지표 (yfinance)

| 티커 | 지표명 |
|------|--------|
| ^TNX | 미국 10년물 금리 |
| CL=F | WTI 원유 선물 |
| GC=F | 금 선물 |
| ^VIX | 변동성 지수 |
| KRW=X | 원/달러 환율 |

### 5.3 공포/탐욕 지수

| 순위 | 방식 | 상세 |
|------|------|------|
| 1 | CNN API | `production.dataviz.cnn.io/index/fearandgreed/graphdata` |
| 2 | 자체 계산 | VIX(40%) + S&P500 RSI(40%) + 기타(20%) |

---

## 6. AI 분석

### 6.1 Gemini Vision (수급 데이터)

| 항목 | 내용 |
|------|------|
| **파일** | `src/dual_source/sources/agentic_source.py` |
| **모델** | Gemini 2.5 Flash |
| **용도** | 스크린샷에서 수급 데이터 추출 |

### 6.2 AI 리서처 (리포트 생성)

| 항목 | 내용 |
|------|------|
| **파일** | `src/ai_researcher.py` |
| **모델** | Gemini 2.5 Flash |
| **키 관리** | `GoogleAPIKeyManager` (최대 3개 키 순환) |

---

## 7. 파일별 데이터 소스 요약

| 파일 | 주요 소스 | 데이터 종류 |
|------|----------|-----------|
| `analysis.py` | yfinance | 주가, 기술 지표, 수익률 |
| `crawler.py` | RSS, 크롤링, FRED | 뉴스, 매크로 지표 |
| `dual_source/sources/yahoo_chart_source.py` | Yahoo Chart API | 미국 주식 (1순위) |
| `dual_source/sources/kis_source.py` | 한국투자증권 API | 한국 주식 (1순위) |
| `dual_source/sources/api_source.py` | 통합 Fallback | 수급 데이터 |
| `dual_source/sources/twelvedata_source.py` | Twelve Data | 미국 주식 (3순위) |
| `dual_source/sources/finnhub_source.py` | Finnhub | 미국 주식 (4순위) |
| `dual_source/sources/fmp_source.py` | FMP | 미국 주식 (5순위) |
| `dual_source/sources/agentic_source.py` | Playwright + Gemini | 수급 (스크린샷) |
| `ai_researcher.py` | Gemini 2.5 Flash | AI 분석 리포트 |

---

## 8. 환경 변수

### 8.1 필수 환경 변수

| 변수명 | 용도 | 설명 |
|--------|------|------|
| `TELEGRAM_TOKEN` | 텔레그램 봇 | 봇 API 토큰 |
| `CHAT_ID` | 텔레그램 채팅 ID | 메시지 수신 채팅방 |
| `GOOGLE_API_KEY_01` | Gemini API | AI 분석용 (기본) |

### 8.2 Gemini API Fallback

| 변수명 | 용도 |
|--------|------|
| `GOOGLE_API_KEY_02` | Fallback 1 |
| `GOOGLE_API_KEY_03` | Fallback 2 |

### 8.3 한국 주식 API

| 변수명 | 용도 | 발급처 |
|--------|------|--------|
| `KIS_APP_KEY` | 한국투자증권 앱키 | apiportal.koreainvestment.com |
| `KIS_APP_SECRET` | 한국투자증권 시크릿 | apiportal.koreainvestment.com |
| `KRX_API_KEY` | KRX OpenAPI | data.krx.co.kr |
| `KRX_API_KEY_EXPIRY` | KRX API 만료일 | YYYY-MM-DD 형식 |

### 8.4 미국 주식 API (선택적)

| 변수명 | 용도 | 무료 제한 | 발급처 |
|--------|------|----------|--------|
| `TWELVE_DATA_API_KEY` | Twelve Data | 800/day | twelvedata.com |
| `FINNHUB_API_KEY` | Finnhub | 60/min | finnhub.io |
| `FMP_API_KEY` | FMP | 250/day | financialmodelingprep.com |

### 8.5 기타

| 변수명 | 용도 | 기본값 |
|--------|------|--------|
| `USE_DUAL_SOURCE` | 듀얼 소스 활성화 | `true` |
| `FRED_API_KEY` | FRED API | 매크로 데이터 |

---

## 9. 오류 처리

### 9.1 재시도 정책

| 상황 | 재시도 | 대기 시간 |
|------|--------|----------|
| DNS 실패 | 5회 | 5→10→20→30→60초 |
| 타임아웃 | 5회 | 5→10→20→30→60초 |
| Rate Limit (429) | 5회 | 10→30→60→120→180초 |
| Quota 초과 | 키 전환 | 즉시 다음 키 |

### 9.2 API 키 관리

- **Google API**: `GoogleAPIKeyManager` (최대 3개 키 순환, 세션 내 상태 유지)
- **KIS API**: `KISTokenManager` (24시간 토큰, 자동 갱신)

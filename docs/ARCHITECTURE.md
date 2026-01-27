# 종목어때.ai 시스템 아키텍처 및 기술 문서

> **문서 버전**: 1.0.0
> **작성일**: 2026-01-27
> **목적**: 타 시스템에 동일하게 적용하기 위한 상세 기술 문서

---

## 목차

1. [시스템 개요](#1-시스템-개요)
2. [전체 아키텍처](#2-전체-아키텍처)
3. [프로젝트 구조](#3-프로젝트-구조)
4. [데이터 획득 방법](#4-데이터-획득-방법)
   - 4.1 [한국 주식 데이터](#41-한국-주식-데이터)
   - 4.2 [미국 주식 데이터](#42-미국-주식-데이터)
   - 4.3 [시장 지표 데이터](#43-시장-지표-데이터)
5. [데이터 활용 방식](#5-데이터-활용-방식)
6. [AI 분석 시스템](#6-ai-분석-시스템)
7. [캐싱 전략](#7-캐싱-전략)
8. [에러 처리 및 Fallback](#8-에러-처리-및-fallback)
9. [인증 시스템](#9-인증-시스템)
10. [배포 구성](#10-배포-구성)
11. [API 엔드포인트 명세](#11-api-엔드포인트-명세)
12. [환경 변수 설정](#12-환경-변수-설정)

---

## 1. 시스템 개요

### 1.1 프로젝트 목적

AI 기반 주식 분석 플랫폼으로, 한국/미국 주식의 기술적 지표를 분석하고 Google Gemini AI를 활용하여 투자 인사이트를 제공합니다.

### 1.2 핵심 기능

| 기능 | 설명 |
|------|------|
| 주식 데이터 수집 | 다중 API 소스에서 실시간/히스토리컬 데이터 수집 |
| 기술적 지표 계산 | RSI, MA, MACD, 볼린저 밴드 등 14개 지표 |
| AI 분석 리포트 | Gemini AI를 활용한 종합 투자 분석 |
| 가격 알림 | 목표가 도달 시 알림 발송 |
| 데이터 교차 검증 | 듀얼 소스 수집 및 신뢰도 검증 |

### 1.3 기술 스택

```
Frontend:  Next.js 15 (App Router) + React 19 + Tailwind CSS v4
Backend:   Next.js API Routes + TypeScript 5.4+
Database:  InMemory Cache (TTL 기반)
AI:        Google Gemini API (다중 키 지원)
Charts:    Recharts 3.6+
Auth:      JWT (jose) + bcryptjs
Deploy:    Docker / Vercel / Render
```

---

## 2. 전체 아키텍처

### 2.1 시스템 구성도

```
┌─────────────────────────────────────────────────────────────────────┐
│                         클라이언트 (웹 브라우저)                      │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ HTTPS
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Next.js 애플리케이션 (Vercel/Render)              │
├─────────────────────────────────────────────────────────────────────┤
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────────────┐   │
│  │  프론트엔드    │  │  API Routes   │  │     미들웨어           │   │
│  │  (React 19)   │  │  (/api/*)     │  │  (JWT 인증 검증)       │   │
│  └───────────────┘  └───────┬───────┘  └───────────────────────┘   │
│                             │                                       │
│  ┌──────────────────────────┴──────────────────────────────────┐   │
│  │                      비즈니스 로직 계층 (lib/)                │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │   │
│  │  │ 데이터 수집  │  │ 지표 계산   │  │    AI 분석          │  │   │
│  │  │ (finance*)  │  │(indicators) │  │  (gemini-client)    │  │   │
│  │  └──────┬──────┘  └─────────────┘  └─────────────────────┘  │   │
│  │         │                                                    │   │
│  │  ┌──────┴──────────────────────────────────────────────┐    │   │
│  │  │              인메모리 캐시 (cache.ts)                 │    │   │
│  │  │              TTL: Quote 5분, Historical 1시간         │    │   │
│  │  └─────────────────────────────────────────────────────┘    │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
        ▼                        ▼                        ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────────┐
│  한국 주식 API │      │  미국 주식 API │      │     AI API        │
├───────────────┤      ├───────────────┤      ├───────────────────┤
│ • KRX Open API│      │ • Yahoo Finance│      │ • Google Gemini   │
│ • 한국투자증권 │      │ • FMP          │      │   (다중 키 지원)   │
│ • 공공데이터   │      │ • Finnhub      │      │ • Saveticker      │
│ • 네이버 크롤링│      │ • Twelve Data  │      │   (시황 리포트)   │
└───────────────┘      └───────────────┘      └───────────────────┘
```

### 2.2 데이터 흐름

```
사용자 입력 (종목, 지표, 기간)
         │
         ▼
┌─────────────────────────────────────┐
│   1. 입력 검증 (data-validator.ts)   │
│   - 종목 심볼 형식 검증              │
│   - 기간 파라미터 검증               │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│   2. 종목명 → 심볼 변환              │
│   - korea-stock-mapper-dynamic.ts   │
│   - 한글 종목명 지원                 │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│   3. 데이터 수집 (병렬 처리)          │
│   - 현재가 (Quote)                   │
│   - 히스토리컬 데이터                │
│   - 수급 데이터 (기관/외국인)         │
│   - 환율, VIX                       │
│   - 뉴스                            │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│   4. 기술적 지표 계산                │
│   - RSI, MA, MACD, Stochastic      │
│   - 볼린저 밴드, 변동성              │
│   - 지지/저항선                     │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│   5. AI 분석 리포트 생성             │
│   - Gemini API 호출                 │
│   - 시황 리포트 통합 (선택)          │
│   - 마크다운 형식 출력               │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│   6. 응답 구성 및 반환               │
│   - 차트 데이터                     │
│   - AI 리포트                       │
│   - 메타데이터 (수행 시간, 토큰 사용량)│
└─────────────────────────────────────┘
```

---

## 3. 프로젝트 구조

```
stock_analysys_web_private_02/
├── app/                              # Next.js App Router
│   ├── page.tsx                      # 홈 페이지 (분석 폼)
│   ├── layout.tsx                    # 루트 레이아웃
│   ├── login/page.tsx                # 로그인 페이지
│   ├── report/page.tsx               # 분석 리포트 페이지
│   ├── alerts/page.tsx               # 가격 알림 설정
│   ├── metrics/page.tsx              # 시스템 메트릭 (Admin)
│   ├── settings/page.tsx             # 설정 페이지
│   └── api/                          # API 라우트
│       ├── analyze/route.ts          # 메인 분석 엔드포인트
│       ├── auth/                     # 인증 (login, logout, status)
│       ├── search-korea-stocks/      # 한국 주식 검색
│       ├── search-us-stocks/         # 미국 주식 검색
│       ├── api-status/               # API 상태 확인
│       └── ...
│
├── lib/                              # 핵심 비즈니스 로직
│   ├── 데이터 수집 계층
│   │   ├── finance.ts                # Yahoo Finance 통합 (966줄)
│   │   ├── finance-adapter.ts        # 다중 소스 어댑터
│   │   ├── finance-fmp.ts            # FMP API
│   │   ├── finance-finnhub.ts        # Finnhub API
│   │   ├── finance-twelvedata.ts     # Twelve Data API
│   │   ├── finance-kis.ts            # 한국투자증권 API
│   │   ├── finance-publicdata.ts     # 공공데이터포털 API
│   │   ├── krx-api.ts                # KRX Open API
│   │   └── dual-source/              # 듀얼 소스 수집
│   │
│   ├── 지표 계산 계층
│   │   ├── indicators.ts             # 기술적 지표 (1,110줄)
│   │   └── indicator-descriptions.ts # 지표 설명 (1,336줄)
│   │
│   ├── AI 분석 계층
│   │   ├── gemini-client.ts          # Gemini API 클라이언트
│   │   └── saveticker/               # Saveticker 시황 리포트
│   │
│   ├── 검색 및 매핑
│   │   ├── korea-stock-mapper-dynamic.ts # 한국 주식 매핑 (714줄)
│   │   └── stock-search.ts           # 통합 검색 엔진
│   │
│   ├── 시스템
│   │   ├── cache.ts                  # 인메모리 캐시
│   │   ├── auth.ts                   # JWT 인증
│   │   ├── alert-system.ts           # 가격 알림
│   │   └── types.ts                  # TypeScript 타입 정의
│   │
│   └── constants.ts                  # 전역 상수
│
├── components/                       # React 컴포넌트
│   ├── ui/                           # Shadcn UI 컴포넌트
│   ├── charts/                       # 차트 컴포넌트 (Recharts)
│   │   ├── price-chart.tsx           # 캔들 차트
│   │   ├── rsi-chart.tsx             # RSI 차트
│   │   ├── macd-chart.tsx            # MACD 차트
│   │   └── ...
│   └── stock-autocomplete.tsx        # 종목 자동완성
│
├── scripts/                          # 스크립트
│   ├── get_comprehensive_stock_listing.py  # 한국 주식 목록 (Python)
│   └── test-kis-api.ts               # KIS API 테스트
│
├── middleware.ts                     # JWT 인증 미들웨어
├── Dockerfile                        # Docker 멀티스테이지 빌드
├── next.config.js                    # Next.js 설정
└── package.json                      # Node.js 의존성
```

---

## 4. 데이터 획득 방법

### 4.1 한국 주식 데이터

#### 4.1.1 KRX Open API (한국거래소)

**파일**: `lib/krx-api.ts`

**용도**: 유가증권/ETF 일별 매매정보

**엔드포인트**:
```
Base URL: https://data-dbg.krx.co.kr/svc/apis
- 유가증권: /sto/stk_bydd_trd
- ETF: /etp/etf_bydd_trd
```

**요청 예시**:
```typescript
const response = await axios.get(
  `https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd`,
  {
    params: {
      AUTH_KEY: process.env.KRX_API_KEY,
      basDd: '20260127',  // YYYYMMDD 형식
    },
    timeout: 10000,
  }
);
```

**응답 구조**:
```typescript
interface KRXResponse {
  OutBlock_1: Array<{
    ISU_CD: string;        // 종목코드 (예: KR7005930003)
    ISU_NM: string;        // 종목명 (예: 삼성전자)
    TDD_CLSPRC: string;    // 종가
    CMPPREVDD_PRC: string; // 전일대비
    FLUC_RT: string;       // 등락률
    TDD_OPNPRC: string;    // 시가
    TDD_HGPRC: string;     // 고가
    TDD_LWPRC: string;     // 저가
    ACC_TRDVOL: string;    // 거래량
    ACC_TRDVAL: string;    // 거래대금
    MKTCAP: string;        // 시가총액
  }>;
}
```

**제한사항**:
- 일일 10,000회 호출 제한
- API 키 유효기간 1년
- 투자자별 매매동향 미제공 → 네이버 크롤링으로 대체

---

#### 4.1.2 한국투자증권 Open API (KIS)

**파일**: `lib/finance-kis.ts`

**용도**: 실시간 시세, 일별 시세, 수급 데이터

**인증 흐름**:
```
1. 토큰 발급: POST /oauth2/tokenP
2. 토큰 캐싱 (24시간 유효)
3. API 호출 시 Bearer 토큰 사용
4. 401 오류 시 자동 재발급
```

**토큰 발급**:
```typescript
const response = await axios.post(
  'https://openapi.koreainvestment.com:9443/oauth2/tokenP',
  {
    grant_type: 'client_credentials',
    appkey: process.env.KIS_APP_KEY,
    appsecret: process.env.KIS_APP_SECRET,
  },
  {
    headers: { 'Content-Type': 'application/json' },
    timeout: 10000,
  }
);

// 토큰 캐싱
cachedToken = {
  token: response.data.access_token,
  expiresAt: Date.now() + response.data.expires_in * 1000,
};
```

**현재가 조회**:
```typescript
// 엔드포인트
GET /uapi/domestic-stock/v1/quotations/inquire-price

// 헤더
headers: {
  'authorization': `Bearer ${accessToken}`,
  'appkey': process.env.KIS_APP_KEY,
  'appsecret': process.env.KIS_APP_SECRET,
  'tr_id': 'FHKST01010100',  // 거래ID
}

// 파라미터
params: {
  FID_COND_MRKT_DIV_CODE: 'J',  // 시장구분 (J: 주식)
  FID_INPUT_ISCD: '005930',     // 종목코드 (6자리)
}
```

**응답 구조**:
```typescript
interface KISQuoteResponse {
  rt_cd: string;  // 응답코드 (0: 성공)
  msg_cd: string;
  msg1: string;
  output: {
    stck_prpr: string;      // 주식현재가
    prdy_vrss: string;      // 전일대비
    prdy_ctrt: string;      // 전일대비율
    stck_oprc: string;      // 시가
    stck_hgpr: string;      // 고가
    stck_lwpr: string;      // 저가
    acml_vol: string;       // 누적거래량
    acml_tr_pbmn: string;   // 누적거래대금
    hts_frgn_ehrt: string;  // HTS 외국인 소진율
    frgn_ntby_qty: string;  // 외국인 순매수량
    pgtr_ntby_qty: string;  // 기관 순매수량
    w52_hgpr: string;       // 52주 최고가
    w52_lwpr: string;       // 52주 최저가
    per: string;            // PER
    pbr: string;            // PBR
    eps: string;            // EPS
    bps: string;            // BPS
  };
}
```

**제한사항**:
- 초당 20회 호출 제한 (추정)
- 모의투자 vs 실전투자 URL 분리
- 해외 주식은 별도 API 사용

---

#### 4.1.3 공공데이터포털 API

**파일**: `lib/finance-publicdata.ts`

**용도**: 금융위원회 주식시세정보 (무료)

**엔드포인트**:
```
https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo
```

**요청 예시**:
```typescript
const response = await axios.get(
  'https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo',
  {
    params: {
      serviceKey: process.env.PUBLIC_DATA_API_KEY,  // 인코딩된 키
      basDt: '20260127',
      likeSrtnCd: '005930',
      resultType: 'json',
      numOfRows: 100,
    },
  }
);
```

**응답 구조**:
```typescript
interface PublicDataResponse {
  response: {
    header: {
      resultCode: string;  // '00': 성공
      resultMsg: string;
    };
    body: {
      items: {
        item: Array<{
          basDt: string;      // 기준일자 (YYYYMMDD)
          srtnCd: string;     // 단축코드
          isinCd: string;     // ISIN코드
          itmsNm: string;     // 종목명
          clpr: string;       // 종가
          vs: string;         // 대비
          fltRt: string;      // 등락률
          mkp: string;        // 시가
          hipr: string;       // 고가
          lopr: string;       // 저가
          trqu: string;       // 거래량
          trPrc: string;      // 거래대금
          mrktTotAmt: string; // 시가총액
        }>;
      };
    };
  };
}
```

**특이사항**:
- 무료 API, 관대한 Rate Limit
- 2020년 1월 이후 데이터만 제공
- **종가 데이터만 제공** (실시간 불가)
- 서비스키는 URL 인코딩된 값 사용 필수

---

#### 4.1.4 네이버 금융 크롤링 (Fallback)

**파일**: `lib/finance.ts` (lines 762-842)

**용도**: 기관/외국인 수급 데이터 (KRX API 미제공 시)

**URL 패턴**:
```
https://finance.naver.com/item/frgn.naver?code={6자리종목코드}
```

**파싱 로직**:
```typescript
async function fetchSupplyDemandNaver(symbol: string): Promise<SupplyDemandData | null> {
  const code = symbol.replace('.KS', '').replace('.KQ', '');
  const url = `https://finance.naver.com/item/frgn.naver?code=${code}`;

  const response = await axios.get(url, {
    responseType: 'arraybuffer',
    headers: { 'User-Agent': 'Mozilla/5.0...' },
  });

  // EUC-KR → UTF-8 변환
  const html = iconv.decode(Buffer.from(response.data), 'EUC-KR');

  // cheerio로 테이블 파싱
  const $ = cheerio.load(html);
  const rows = $('table.type2 tbody tr');

  // 데이터 추출
  // td[5]: 기관순매매, td[6]: 외국인순매매
  const institutional = parseNumber($(row).find('td').eq(5).text());
  const foreign = parseNumber($(row).find('td').eq(6).text());
  const individual = -(institutional + foreign);  // 개인 = -(기관+외국인)

  return { institutional, foreign, individual };
}
```

---

### 4.2 미국 주식 데이터

#### 4.2.1 Yahoo Finance (Primary)

**파일**: `lib/finance.ts`

**라이브러리**: `yahoo-finance2`

**용도**: 실시간 시세, 히스토리컬 데이터, 뉴스

**Chart API (Rate Limit 회피용)**:
```typescript
// crumb 토큰 불필요 → Rate Limit에 강함
const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeSymbol(symbol)}`;

const response = await axios.get(url, {
  params: {
    interval: '1d',
    range: '6mo',  // 1d, 1mo, 3mo, 6mo, 1y, 2y
  },
  headers: {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)...',
  },
  timeout: 15000,
});
```

**응답 구조**:
```typescript
interface YahooChartResponse {
  chart: {
    result: Array<{
      meta: {
        symbol: string;
        regularMarketPrice: number;
        chartPreviousClose: number;
        regularMarketVolume: number;
        regularMarketDayHigh: number;
        regularMarketDayLow: number;
        fiftyTwoWeekHigh: number;
        fiftyTwoWeekLow: number;
        longName: string;
        currency: string;
      };
      timestamp: number[];
      indicators: {
        quote: Array<{
          open: number[];
          high: number[];
          low: number[];
          close: number[];
          volume: number[];
        }>;
        adjclose: Array<{
          adjclose: number[];
        }>;
      };
    }>;
  };
}
```

**데이터 변환**:
```typescript
// Range 선택 로직
function getYahooRange(days: number): string {
  if (days <= 5) return '1mo';
  if (days <= 30) return '1mo';
  if (days <= 90) return '3mo';
  if (days <= 180) return '6mo';
  if (days <= 365) return '1y';
  return '2y';
}

// 히스토리컬 데이터 변환
const historicalData = timestamps.map((ts, i) => ({
  date: new Date(ts * 1000).toISOString().split('T')[0],
  open: opens[i],
  high: highs[i],
  low: lows[i],
  close: closes[i],
  adjClose: adjCloses?.[i] ?? closes[i],
  volume: volumes[i],
}));
```

---

#### 4.2.2 Financial Modeling Prep (FMP)

**파일**: `lib/finance-fmp.ts`

**용도**: 실시간 시세, 히스토리컬, 재무제표 (NASDAQ 공식 라이선스)

**Base URL**: `https://financialmodelingprep.com/stable`

**엔드포인트**:
```
- 시세: /quote?symbol={symbol}
- 배치 시세: /batch-quote?symbols={s1},{s2}
- 히스토리컬: /historical-price-eod/full?symbol={symbol}
- 프로필: /profile?symbol={symbol}
- 재무지표: /key-metrics-ttm?symbol={symbol}
```

**요청 예시**:
```typescript
const response = await axios.get(
  'https://financialmodelingprep.com/stable/quote',
  {
    params: {
      symbol: 'AAPL',
      apikey: process.env.FMP_API_KEY,
    },
    timeout: 15000,
  }
);
```

**응답 구조**:
```typescript
interface FMPQuote {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercentage: number;  // 새 API: 단수형
  dayLow: number;
  dayHigh: number;
  yearHigh: number;
  yearLow: number;
  marketCap: number;
  volume: number;
  avgVolume: number;
  exchange: string;
  open: number;
  previousClose: number;
  eps: number;
  pe: number;
}
```

**제한사항**:
- 무료 티어: 250 calls/day
- 유료 플랜: $19/month (무제한)

---

#### 4.2.3 Finnhub

**파일**: `lib/finance-finnhub.ts`

**용도**: 실시간 시세, 뉴스 (한국/미국 모두 지원)

**엔드포인트**:
```
Base URL: https://finnhub.io/api/v1
- 시세: /quote
- 캔들: /stock/candle
- 뉴스: /company-news
- 심볼 검색: /search
```

**요청 예시**:
```typescript
const response = await axios.get('https://finnhub.io/api/v1/quote', {
  params: {
    symbol: 'AAPL',
    token: process.env.FINNHUB_API_KEY,
  },
});
```

**응답 구조**:
```typescript
interface FinnhubQuote {
  c: number;   // current price
  d: number;   // change
  dp: number;  // percent change
  h: number;   // high
  l: number;   // low
  o: number;   // open
  pc: number;  // previous close
  t: number;   // timestamp
}

interface FinnhubCandle {
  c: number[];  // close prices
  h: number[];  // high prices
  l: number[];  // low prices
  o: number[];  // open prices
  t: number[];  // timestamps (Unix)
  v: number[];  // volumes
  s: string;    // status ('ok' | 'no_data')
}
```

**제한사항**:
- 무료 플랜: 60 calls/min
- 무료 플랜에서 Candle API 제한 있음 → Yahoo Fallback

---

#### 4.2.4 Twelve Data

**파일**: `lib/finance-twelvedata.ts`

**용도**: 글로벌 시장 데이터 (한국 주식 KRX 지원)

**엔드포인트**:
```
Base URL: https://api.twelvedata.com
- 시세: /quote
- 시계열: /time_series
- 환율: /exchange_rate
```

**심볼 정규화**:
```typescript
// Yahoo → Twelve Data 변환
function normalizeSymbol(symbol: string): string {
  if (symbol.endsWith('.KS')) {
    return symbol.replace('.KS', ':KRX');
  }
  if (symbol.endsWith('.KQ')) {
    return symbol.replace('.KQ', ':KRX');
  }
  return symbol;
}

// 005930.KS → 005930:KRX
```

**제한사항**:
- 무료 티어: 800 req/day, 8 req/min
- 150ms 최소 요청 간격 필요

---

### 4.3 시장 지표 데이터

#### 4.3.1 환율 (USD/KRW)

```typescript
// Yahoo Finance Chart API
const url = 'https://query1.finance.yahoo.com/v8/finance/chart/KRW=X';
const response = await axios.get(url, { params: { interval: '1d', range: '1d' } });
const rate = response.data.chart.result[0].meta.regularMarketPrice;
```

#### 4.3.2 VIX (공포 지수)

```typescript
// Yahoo Finance Chart API
const url = 'https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX';
const response = await axios.get(url, { params: { interval: '1d', range: '1d' } });
const vix = response.data.chart.result[0].meta.regularMarketPrice;
```

---

## 5. 데이터 활용 방식

### 5.1 기술적 지표 계산

**파일**: `lib/indicators.ts`

#### RSI (Relative Strength Index)
```typescript
export function calculateRSI(prices: number[], period: number = 14): number | null {
  if (prices.length < period + 1) return null;

  let gains = 0;
  let losses = 0;

  // 초기 평균 계산
  for (let i = 1; i <= period; i++) {
    const change = prices[i] - prices[i - 1];
    if (change > 0) gains += change;
    else losses -= change;
  }

  let avgGain = gains / period;
  let avgLoss = losses / period;

  // Wilder's Smoothing으로 나머지 계산
  for (let i = period + 1; i < prices.length; i++) {
    const change = prices[i] - prices[i - 1];
    avgGain = (avgGain * (period - 1) + (change > 0 ? change : 0)) / period;
    avgLoss = (avgLoss * (period - 1) + (change < 0 ? -change : 0)) / period;
  }

  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - (100 / (1 + rs));
}
```

#### 이동평균선 (MA)
```typescript
export function calculateMA(prices: number[], period: number): number | null {
  if (prices.length < period) return null;
  const sum = prices.slice(-period).reduce((a, b) => a + b, 0);
  return sum / period;
}
```

#### MACD
```typescript
export function calculateMACD(prices: number[]): MACDResult | null {
  if (prices.length < 26) return null;

  const ema12 = calculateEMA(prices, 12);
  const ema26 = calculateEMA(prices, 26);

  const macdLine = ema12 - ema26;
  const signalLine = calculateEMA([...macdValues, macdLine], 9);
  const histogram = macdLine - signalLine;

  return { macdLine, signalLine, histogram };
}
```

#### 볼린저 밴드
```typescript
export function calculateBollingerBands(
  prices: number[],
  period: number = 20,
  stdDev: number = 2
): BollingerBands | null {
  if (prices.length < period) return null;

  const recentPrices = prices.slice(-period);
  const sma = recentPrices.reduce((a, b) => a + b, 0) / period;

  const variance = recentPrices.reduce((sum, price) => {
    return sum + Math.pow(price - sma, 2);
  }, 0) / period;

  const std = Math.sqrt(variance);

  return {
    upper: sma + (stdDev * std),
    middle: sma,
    lower: sma - (stdDev * std),
    bandwidth: ((sma + stdDev * std) - (sma - stdDev * std)) / sma * 100,
  };
}
```

### 5.2 지표 목록

| 지표 | 함수 | 용도 |
|------|------|------|
| RSI | `calculateRSI()` | 과매수/과매도 판단 |
| MA (5, 20, 60, 120) | `calculateMA()` | 추세 분석 |
| 이격도 | `calculateDisparity()` | 이평선 대비 괴리 |
| MACD | `calculateMACD()` | 추세 전환 신호 |
| 스토캐스틱 | `calculateStochastic()` | 단기 모멘텀 |
| 볼린저 밴드 | `calculateBollingerBands()` | 변동성 분석 |
| 지지/저항선 | `calculateSupportResistance()` | 주요 가격대 |
| 거래량 지표 | `calculateVolumeIndicators()` | 거래량 이상 감지 |
| ETF 괴리율 | `calculateETFPremium()` | NAV 대비 괴리 |
| 변동성 | `calculateVolatility()` | 변동성 측정 |

---

## 6. AI 분석 시스템

### 6.1 Gemini API 클라이언트

**파일**: `lib/gemini-client.ts`

#### 다중 API 키 관리
```typescript
// 환경변수에서 키 로드 (최대 10개)
export function getGeminiApiKeys(): string[] {
  const keys: string[] = [];

  for (let i = 1; i <= 10; i++) {
    const keyNum = i.toString().padStart(2, '0');
    const envKey = `GEMINI_API_KEY_${keyNum}`;
    const keyValue = process.env[envKey]?.trim();

    if (keyValue) {
      keys.push(keyValue);
    }
  }

  // 레거시 키 Fallback
  if (keys.length === 0) {
    const legacyKey = process.env.GEMINI_API_KEY?.trim();
    if (legacyKey) keys.push(legacyKey);
  }

  return keys;
}
```

#### 스마트 키 상태 관리
```typescript
interface KeyState {
  currentKeyIndex: number;
  failedKeyIndices: Set<number>;
  lastSuccessKeyIndex: number;
}

// 키 선택 로직
function selectNextKey(): string {
  // 1. 마지막 성공 키 우선
  if (keyState.lastSuccessKeyIndex >= 0) {
    return keys[keyState.lastSuccessKeyIndex];
  }

  // 2. 실패한 키 건너뛰기
  for (let i = 0; i < keys.length; i++) {
    if (!keyState.failedKeyIndices.has(i)) {
      return keys[i];
    }
  }

  // 3. 모든 키 실패 시 초기화
  keyState.failedKeyIndices.clear();
  return keys[0];
}
```

### 6.2 분석 프롬프트 구조

**시스템 프롬프트**:
```typescript
const systemPrompt = `당신은 월스트리트와 여의도에서 20년 이상 활동한
**수석 투자 전략가(Chief Investment Strategist)**입니다.

[분석 원칙]
1. 데이터 기반 객관적 분석
2. 기술적 지표와 수급 데이터 종합
3. 시장 심리(VIX, Fear & Greed) 반영
4. 리스크 요인 명확히 제시
5. 투자 의견과 근거 명시

[출력 형식]
- 마크다운 형식
- 각 종목별 섹션 구분
- 핵심 요약 → 상세 분석 → 결론 순서
`;
```

**사용자 프롬프트 (데이터 제공)**:
```typescript
const userPrompt = `
## 분석 요청
- 분석 기준일: ${analysisDate}
- 향후 전망 기간: ${period}
- 과거 데이터 기간: ${historicalPeriod}

## 종목 데이터

### ${symbol}
- 현재가: ${price.toLocaleString()}원
- 변동률: ${changePercent.toFixed(2)}%
- RSI(14): ${rsi}
- 이동평균선:
  - 5일선: ${ma5.toLocaleString()}
  - 20일선: ${ma20.toLocaleString()}
  - 60일선: ${ma60.toLocaleString()}
- MACD: ${macd.macdLine.toFixed(2)} / Signal: ${macd.signalLine.toFixed(2)}
- 수급:
  - 기관: ${institutional > 0 ? '+' : ''}${institutional.toLocaleString()}
  - 외국인: ${foreign > 0 ? '+' : ''}${foreign.toLocaleString()}
- 52주 최고/최저: ${high52.toLocaleString()} / ${low52.toLocaleString()}

### 시장 지표
- 환율(USD/KRW): ${exchangeRate.toFixed(2)}
- VIX: ${vix.toFixed(2)}

### 최근 뉴스
${news.slice(0, 3).map((n, i) => `${i + 1}. ${n.title}`).join('\n')}

---
위 데이터를 기반으로 종합 분석 리포트를 작성해주세요.
`;
```

### 6.3 토큰 사용량 추적

```typescript
interface TokenUsage {
  promptTokenCount: number;
  candidatesTokenCount: number;
  totalTokenCount: number;
}

// Admin 전용 메타데이터에 포함
const response = {
  results: [...],
  _metadata: {
    tokenUsage: {
      promptTokenCount: 1500,
      candidatesTokenCount: 2000,
      totalTokenCount: 3500,
    },
  },
};
```

---

## 7. 캐싱 전략

### 7.1 인메모리 캐시 구현

**파일**: `lib/cache.ts`

```typescript
interface CacheEntry<T> {
  data: T;
  timestamp: number;
  ttl: number;
}

class InMemoryCache {
  private cache = new Map<string, CacheEntry<unknown>>();
  private stats = { hits: 0, misses: 0 };

  get<T>(key: string): T | null {
    const entry = this.cache.get(key);
    if (!entry) {
      this.stats.misses++;
      return null;
    }

    // TTL 확인
    if (Date.now() - entry.timestamp > entry.ttl) {
      this.cache.delete(key);
      this.stats.misses++;
      return null;
    }

    this.stats.hits++;
    return entry.data as T;
  }

  set<T>(key: string, data: T, ttl: number): void {
    this.cache.set(key, {
      data,
      timestamp: Date.now(),
      ttl,
    });
  }

  // 5분마다 만료된 항목 정리
  cleanup(): void {
    const now = Date.now();
    for (const [key, entry] of this.cache.entries()) {
      if (now - entry.timestamp > entry.ttl) {
        this.cache.delete(key);
      }
    }
  }
}

export const cache = new InMemoryCache();
```

### 7.2 TTL 정책

```typescript
export const CACHE_TTL = {
  QUOTE: 5 * 60 * 1000,           // 5분 - 실시간성 유지
  HISTORICAL: 60 * 60 * 1000,     // 1시간 - 과거 데이터는 불변
  EXCHANGE_RATE: 10 * 60 * 1000,  // 10분
  VIX: 10 * 60 * 1000,            // 10분
  NEWS: 30 * 60 * 1000,           // 30분
  STOCK_DATA: 5 * 60 * 1000,      // 5분
};
```

### 7.3 캐시 키 패턴

```typescript
export const CacheKey = {
  quote: (symbol: string) => `quote:${symbol}`,
  historical: (symbol: string, days: number) => `historical:${symbol}:${days}`,
  stockData: (symbol: string) => `stockData:${symbol}`,
  exchangeRate: () => `exchangeRate:USD_KRW`,
  vix: () => `vix:VIX`,
  news: (symbol: string) => `news:${symbol}`,
};
```

### 7.4 사용 예시

```typescript
async function fetchQuoteWithCache(symbol: string): Promise<Quote> {
  const cacheKey = CacheKey.quote(symbol);

  // 캐시 확인
  const cached = cache.get<Quote>(cacheKey);
  if (cached) return cached;

  // API 호출
  const quote = await fetchQuoteFromAPI(symbol);

  // 캐시 저장
  cache.set(cacheKey, quote, CACHE_TTL.QUOTE);

  return quote;
}
```

---

## 8. 에러 처리 및 Fallback

### 8.1 지수 백오프 재시도

```typescript
async function retryWithDelay<T>(
  fn: () => Promise<T>,
  maxRetries: number = 3,
  initialDelayMs: number = 3000
): Promise<T> {
  let lastError: Error | null = null;

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error as Error;

      // Rate Limit 오류인 경우에만 재시도
      if (error.message?.includes('Too Many Requests')) {
        const delayMs = initialDelayMs * Math.pow(2, attempt);  // 3s → 6s → 12s
        console.log(`Rate limit hit, waiting ${delayMs}ms...`);
        await new Promise(r => setTimeout(r, delayMs));
        continue;
      }

      throw error;  // 다른 오류는 즉시 throw
    }
  }

  throw lastError;
}
```

### 8.2 Fallback 체인

**파일**: `lib/finance-adapter.ts`

```typescript
// 미국 주식 Fallback 체인
async function fetchUSStocksWithFallback(symbols: string[]): Promise<Map<string, StockData>> {
  const sources = [
    { name: 'Yahoo Finance', fn: () => fetchYahoo(symbols) },
    { name: 'Finnhub', fn: () => fetchFinnhub(symbols), condition: () => !!FINNHUB_API_KEY },
    { name: 'FMP', fn: () => fetchFMP(symbols), condition: () => !!FMP_API_KEY },
    { name: 'Twelve Data', fn: () => fetchTwelveData(symbols), condition: () => !!TWELVE_DATA_API_KEY },
  ];

  for (const source of sources) {
    if (source.condition && !source.condition()) continue;

    try {
      const result = await source.fn();
      if (result.size > 0) {
        console.log(`✓ ${source.name} 성공`);
        return result;
      }
    } catch (error) {
      console.warn(`✗ ${source.name} 실패:`, error.message);
    }
  }

  throw new Error('모든 데이터 소스 실패');
}
```

**한국 주식 Fallback 체인**:
```
1. KIS API (한국투자증권)
   ↓ 실패 시
2. Yahoo Finance (005930.KS 형식)
   ↓ 실패 시
3. 공공데이터포털 (무료, 종가만)
   ↓ 실패 시
4. Twelve Data (005930:KRX 형식)
```

### 8.3 API 키 무효 알림

```typescript
if (response.status === 401) {
  await alertSystem.alertApiKeyInvalid(
    'KRX API',
    '401 Unauthorized - API 키가 만료되었거나 유효하지 않습니다.',
    {
      statusCode: 401,
      endpoint: '/svc/apis/sto/stk_bydd_trd',
      timestamp: Date.now(),
      note: 'KRX API 키는 1년 유효기간이 있습니다. 갱신이 필요합니다.',
    }
  );
}
```

---

## 9. 인증 시스템

### 9.1 JWT 기반 인증

**파일**: `lib/auth.ts`

```typescript
import { SignJWT, jwtVerify } from 'jose';
import bcrypt from 'bcryptjs';

const JWT_SECRET = new TextEncoder().encode(process.env.JWT_SECRET);

interface JWTPayload {
  username: string;
  role: 'admin';
  iat: number;
  exp: number;
}

// 토큰 생성
export async function createToken(username: string): Promise<string> {
  return new SignJWT({ username, role: 'admin' })
    .setProtectedHeader({ alg: 'HS256' })
    .setIssuedAt()
    .setExpirationTime('24h')
    .sign(JWT_SECRET);
}

// 토큰 검증
export async function verifyToken(token: string): Promise<JWTPayload | null> {
  try {
    const { payload } = await jwtVerify(token, JWT_SECRET);
    return payload as JWTPayload;
  } catch {
    return null;
  }
}

// 비밀번호 검증
export async function verifyPassword(password: string, hash: string): Promise<boolean> {
  return bcrypt.compare(password, hash);
}
```

### 9.2 미들웨어

**파일**: `middleware.ts`

```typescript
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { verifyToken } from './lib/auth';

// 공개 경로
const PUBLIC_PATHS = [
  '/login',
  '/api/auth/login',
  '/_next',
  '/favicon.ico',
];

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // 공개 경로는 통과
  if (PUBLIC_PATHS.some(path => pathname.startsWith(path))) {
    return NextResponse.next();
  }

  // 토큰 확인
  const token = request.cookies.get('auth-token')?.value;

  if (!token) {
    return NextResponse.redirect(new URL('/login', request.url));
  }

  const payload = await verifyToken(token);

  if (!payload) {
    return NextResponse.redirect(new URL('/login', request.url));
  }

  return NextResponse.next();
}
```

---

## 10. 배포 구성

### 10.1 Docker

**파일**: `Dockerfile`

```dockerfile
# Stage 1: Base
FROM node:20-slim AS base
RUN apt-get update && apt-get install -y python3 python3-pip

# Stage 2: Dependencies
FROM base AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

# Stage 3: Builder
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Playwright 설치 (Saveticker용)
RUN npx playwright install chromium --with-deps

RUN npm run build

# Stage 4: Runner
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production

# Standalone 출력 복사
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["node", "server.js"]
```

### 10.2 Vercel 배포

```json
// vercel.json
{
  "buildCommand": "npm run build",
  "outputDirectory": ".next",
  "framework": "nextjs",
  "regions": ["icn1"],
  "functions": {
    "app/api/**/*": {
      "maxDuration": 60
    }
  }
}
```

### 10.3 Render 배포

```yaml
# render.yaml
services:
  - type: web
    name: stock-insight
    env: node
    buildCommand: npm install && npm run build
    startCommand: npm start
    envVars:
      - key: NODE_ENV
        value: production
      - key: JWT_SECRET
        sync: false
      - key: GEMINI_API_KEY_01
        sync: false
```

---

## 11. API 엔드포인트 명세

### 11.1 인증

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/api/auth/login` | POST | 로그인 (JWT 발급) |
| `/api/auth/logout` | POST | 로그아웃 |
| `/api/auth/status` | GET | 인증 상태 확인 |

### 11.2 분석

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/api/analyze` | POST | 메인 분석 (종목, 지표, AI 리포트) |

**요청**:
```typescript
interface AnalyzeRequest {
  stocks: string[];           // ["005930.KS", "AAPL"]
  period: string;             // "1w" | "1m" | "3m" | "6m" | "1y"
  historicalPeriod: string;   // "1m" | "3m" | "6m" | "1y"
  analysisDate: string;       // "2026-01-27"
  indicators: {
    rsi: boolean;
    movingAverages: boolean;
    disparity: boolean;
    supplyDemand: boolean;
    fearGreed: boolean;
    exchangeRate: boolean;
    bollingerBands?: boolean;
    macd?: boolean;
    stochastic?: boolean;
    // ...
  };
}
```

**응답**:
```typescript
interface AnalyzeResponse {
  results: Array<{
    symbol: string;
    marketData: {
      price: number;
      change: number;
      changePercent: number;
      volume: number;
      rsi: number | null;
      movingAverages: { ma5, ma20, ma60, ma120 };
      macd?: { macdLine, signalLine, histogram };
      bollingerBands?: { upper, middle, lower };
      // ...
    };
    historicalData: Array<{ date, open, high, low, close, volume }>;
    aiReport: string;  // Markdown
  }>;
  error?: string;
  _metadata?: {
    dataCollection: number;
    aiAnalysis: number;
    total: number;
    tokenUsage?: { promptTokenCount, candidatesTokenCount, totalTokenCount };
  };
}
```

### 11.3 검색

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/api/search-korea-stocks` | GET | 한국 주식 검색 |
| `/api/search-us-stocks` | GET | 미국 주식 검색 |
| `/api/validate-stock` | GET | 종목 유효성 검증 |

### 11.4 시스템

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/api/api-status` | GET | 전체 API 상태 확인 |
| `/api/cache-stats` | GET | 캐시 통계 |
| `/api/metrics` | GET | 데이터 수집 메트릭 |

---

## 12. 환경 변수 설정

### 12.1 필수 변수

```bash
# 인증
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=$2b$10$...  # bcrypt 해시
JWT_SECRET=your-32-char-secret

# AI 분석
GEMINI_API_KEY_01=your-gemini-key
```

### 12.2 선택 변수 (데이터 소스)

```bash
# 한국 주식
KRX_API_KEY=your-krx-key
KIS_APP_KEY=your-kis-app-key
KIS_APP_SECRET=your-kis-app-secret
PUBLIC_DATA_API_KEY=your-public-data-key

# 미국 주식
FMP_API_KEY=your-fmp-key
FINNHUB_API_KEY=your-finnhub-key
TWELVE_DATA_API_KEY=your-twelvedata-key

# AI 백업 키
GEMINI_API_KEY_02=backup-key-1
GEMINI_API_KEY_03=backup-key-2

# Saveticker
SAVETICKER_EMAIL=your-email
SAVETICKER_PASSWORD=your-password
```

### 12.3 비밀번호 해시 생성

```bash
node -e "console.log(require('bcryptjs').hashSync('your-password', 10))"
```

### 12.4 JWT 시크릿 생성

```bash
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

---

## 부록: Rate Limit 대응 전략

| API | 제한 | 대응 |
|-----|------|------|
| Yahoo Finance | 불명확 | Chart API 사용 (crumb 불필요) |
| KRX | 10,000/day | 캐싱, 배치 요청 |
| KIS | 20/sec | 요청 간 50ms 딜레이 |
| Finnhub | 60/min | 1초 딜레이 |
| Twelve Data | 8/min | 150ms 최소 간격 |
| FMP | 250/day | 캐싱, 배치 요청 |

---

## 문서 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| 1.0.0 | 2026-01-27 | 초기 작성 |

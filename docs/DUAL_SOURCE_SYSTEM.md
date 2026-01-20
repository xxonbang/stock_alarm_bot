# 듀얼 소스 데이터 수집 시스템 (Dual Source Data Collection System)

> **버전**: 1.0.0
> **작성일**: 2026-01-20
> **적용 범위**: 한국/미국 주식 데이터 수집

---

## 1. 시스템 개요

### 1.1 듀얼 소스 시스템이란?

듀얼 소스 시스템은 **두 개의 독립적인 데이터 소스**에서 동일한 주식 데이터를 병렬로 수집하고, **교차 검증**을 통해 신뢰성 높은 최종 데이터를 생성하는 아키텍처입니다.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      듀얼 소스 데이터 수집 시스템                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   [Source A]                              [Source B]                    │
│   Agentic Screenshot                      전통적 API                    │
│   (Puppeteer + Vision AI)                 (REST API)                   │
│        │                                       │                        │
│        ▼                                       ▼                        │
│   ┌──────────────┐                     ┌──────────────┐                │
│   │ 네이버 금융   │ (한국)              │ 다음 금융 API │ (한국)         │
│   │ Yahoo Finance│ (미국)              │ Yahoo API    │ (미국)         │
│   └──────────────┘                     └──────────────┘                │
│        │                                       │                        │
│        └───────────────┬───────────────────────┘                        │
│                        ▼                                                │
│              ┌──────────────────┐                                       │
│              │   검증 엔진       │                                       │
│              │   (Validation    │                                       │
│              │    Engine)       │                                       │
│              └──────────────────┘                                       │
│                        │                                                │
│                        ▼                                                │
│              ┌──────────────────┐                                       │
│              │ ValidatedStockData│                                      │
│              │ (신뢰도 포함)      │                                      │
│              └──────────────────┘                                       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 핵심 이점

| 이점 | 설명 |
|------|------|
| **데이터 신뢰성 향상** | 두 소스의 교차 검증으로 오류 데이터 필터링 |
| **사이트 변경 대응** | Agentic 방식이 CSS 셀렉터 변경에 자동 적응 |
| **데이터 보완** | 한 소스에 없는 데이터를 다른 소스에서 보완 |
| **장애 내성** | 한 소스 실패 시에도 다른 소스로 데이터 제공 |
| **신뢰도 지표** | 데이터 품질을 정량적으로 측정 가능 |

---

## 2. 아키텍처 상세

### 2.1 Source A: Agentic Screenshot (Vision AI 기반)

**개념**: 웹 브라우저로 페이지를 렌더링 → 스크린샷 캡처 → Vision AI가 이미지에서 데이터 추출

```
┌─────────────────────────────────────────────────────────────┐
│                  Agentic Screenshot 방식                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  [1] Puppeteer         [2] Screenshot       [3] Vision AI   │
│      브라우저 자동화        화면 캡처            데이터 추출   │
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │ - Headless   │    │ - PNG 이미지  │    │ - Gemini API │   │
│  │ - Stealth    │ →  │ - Base64     │ →  │ - JSON 파싱  │   │
│  │ - User Agent │    │ - Full Page  │    │ - 구조화     │   │
│  └──────────────┘    └──────────────┘    └──────────────┘   │
│                                                              │
│  장점:                                                       │
│  ✅ CSS 셀렉터 하드코딩 불필요                                │
│  ✅ 웹사이트 구조 변경에 자동 적응                            │
│  ✅ JavaScript 렌더링 후 데이터 수집 가능                     │
│  ✅ 복잡한 테이블/차트에서 데이터 추출 가능                    │
│                                                              │
│  단점:                                                       │
│  ⚠️ 상대적으로 느림 (5-10초/요청)                            │
│  ⚠️ Vision AI API 비용 발생                                  │
│  ⚠️ 서버리스 환경에서 제한 (Puppeteer 미지원)                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**구현 파일**: `lib/dual-source/agentic-crawler.ts`

```typescript
// Agentic Screenshot 크롤러 핵심 흐름
class AgenticScreenshotCrawler {
  async collectKoreaStock(symbol: string) {
    // 1. Puppeteer로 네이버 금융 페이지 접속
    await page.goto(`https://finance.naver.com/item/main.naver?code=${symbol}`);

    // 2. 스크린샷 캡처
    const screenshot = await page.screenshot({ encoding: 'base64' });

    // 3. Gemini Vision AI로 데이터 추출
    const data = await this.extractDataWithVision(screenshot, prompt);

    return { data, source: 'agentic', success: true };
  }
}
```

### 2.2 Source B: 전통적 API 방식

**개념**: REST API 또는 라이브러리를 통해 구조화된 데이터 직접 수집

```
┌─────────────────────────────────────────────────────────────┐
│                   전통적 API 방식                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  [한국 주식]                    [미국 주식]                   │
│  ┌──────────────────┐         ┌──────────────────┐          │
│  │ 다음 금융 API     │         │ Yahoo Finance API│          │
│  │ (finance.daum.net)│        │ (yahoo-finance2) │          │
│  └──────────────────┘         └──────────────────┘          │
│                                                              │
│  장점:                                                       │
│  ✅ 빠른 응답 속도 (100-500ms)                               │
│  ✅ 추가 비용 없음 (무료 API)                                 │
│  ✅ 구조화된 데이터 직접 획득                                 │
│  ✅ 서버리스 환경 호환                                        │
│                                                              │
│  단점:                                                       │
│  ⚠️ API 스펙 변경 시 코드 수정 필요                          │
│  ⚠️ Rate limit 제한                                          │
│  ⚠️ 일부 데이터 미제공 (재무제표 등)                          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**구현 파일**:
- 한국 주식: `lib/dual-source/korea-stock-daum.ts`
- 미국 주식: `lib/dual-source/us-stock-yahoo.ts`

---

## 3. 데이터 모델

### 3.1 통합 주식 데이터 구조

```typescript
interface ComprehensiveStockData {
  // 기본 정보
  basicInfo: {
    symbol: string;      // 종목코드 (005930, AAPL)
    name: string;        // 종목명 (삼성전자, Apple Inc.)
    market: string;      // 시장 (KOSPI, NASDAQ)
    exchange: string;    // 거래소 (KRX, NYSE)
  };

  // 가격 데이터
  priceData: {
    currentPrice: number;    // 현재가
    previousClose: number;   // 전일종가
    change: number;          // 등락금액
    changePercent: number;   // 등락률 (%)
    open: number;            // 시가
    high: number;            // 고가
    low: number;             // 저가
    volume: number;          // 거래량
    tradingValue: number;    // 거래대금
    high52Week: number;      // 52주 최고
    low52Week: number;       // 52주 최저
  };

  // 밸류에이션 데이터
  valuationData: {
    per: number | null;           // PER
    pbr: number | null;           // PBR
    eps: number | null;           // EPS
    bps: number | null;           // BPS
    roe: number | null;           // ROE (%)
    dividendYield: number | null; // 배당수익률 (%)
    estimatedPer: number | null;  // 추정 PER
    estimatedEps: number | null;  // 추정 EPS
  };

  // 재무 데이터
  financialData: {
    revenue: number | null;          // 매출액
    operatingIncome: number | null;  // 영업이익
    netIncome: number | null;        // 당기순이익
    operatingMargin: number | null;  // 영업이익률 (%)
    netProfitMargin: number | null;  // 순이익률 (%)
    fiscalDate: string | null;       // 재무제표 기준일
  };

  // 수급 데이터
  supplyDemandData: {
    foreignOwnership: number | null;    // 외국인 보유율 (%)
    foreignNetBuy: number | null;       // 외국인 순매수
    institutionalNetBuy: number | null; // 기관 순매수
    individualNetBuy: number | null;    // 개인 순매수
  };

  // 시장 데이터
  marketData: {
    marketCap: number | null;         // 시가총액
    sharesOutstanding: number | null; // 상장주식수
    floatShares: number | null;       // 유동주식수
    beta: number | null;              // 베타
  };

  timestamp: number;                            // 수집 시간
  source: 'crawling' | 'agentic' | 'api';      // 데이터 소스
}
```

### 3.2 검증 결과 데이터 구조

```typescript
interface ValidatedStockData {
  data: ComprehensiveStockData;    // 검증 완료된 병합 데이터
  confidence: number;              // 신뢰도 (0.0 ~ 1.0)
  sources: ('crawling' | 'agentic' | 'api')[]; // 사용된 소스들
  validation: {
    status: ValidationStatus;       // 검증 상태
    matchedFields: string[];        // 일치 필드 목록
    conflictFields: string[];       // 충돌 필드 목록
    supplementedFields: string[];   // 보완 필드 목록
  };
  collectedAt: number;             // 수집 완료 시간
}

type ValidationStatus =
  | 'MATCH'    // 두 소스 완전 일치 (신뢰도: 98%)
  | 'PARTIAL'  // 부분 일치 (신뢰도: 85%)
  | 'CONFLICT' // 데이터 충돌 (신뢰도: 70%)
  | 'SINGLE'   // 단일 소스만 성공 (신뢰도: 65%)
  | 'EMPTY';   // 데이터 없음 (신뢰도: 0%)
```

---

## 4. 검증 엔진 (Validation Engine)

### 4.1 검증 프로세스

```
┌─────────────────────────────────────────────────────────────┐
│                    검증 엔진 프로세스                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Source A 데이터           Source B 데이터                   │
│       │                         │                            │
│       └────────────┬────────────┘                            │
│                    ▼                                         │
│           ┌────────────────┐                                 │
│           │  필드별 비교    │                                 │
│           └────────────────┘                                 │
│                    │                                         │
│       ┌────────────┼────────────┐                            │
│       ▼            ▼            ▼                            │
│   [일치]       [충돌]       [단일값]                          │
│   허용오차     허용오차      한쪽만                           │
│   내 동일     초과 차이     값 존재                          │
│       │            │            │                            │
│       ▼            ▼            ▼                            │
│   평균값       A 우선       존재값                           │
│   사용        (또는 평균)    사용                            │
│       │            │            │                            │
│       └────────────┼────────────┘                            │
│                    ▼                                         │
│           ┌────────────────┐                                 │
│           │  신뢰도 계산    │                                 │
│           └────────────────┘                                 │
│                    │                                         │
│                    ▼                                         │
│           ValidatedStockData                                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 허용 오차 (Tolerance) 설정

```typescript
// 필드별 허용 오차 설정 (lib/dual-source/validation-engine.ts)
const DEFAULT_TOLERANCE: Record<string, number> = {
  // 가격 데이터 - 0.5% 허용 (실시간 차이 고려)
  currentPrice: 0.005,
  previousClose: 0.005,
  change: 0.01,
  changePercent: 0.01,
  open: 0.005,
  high: 0.005,
  low: 0.005,
  volume: 0.05,        // 거래량은 5% 허용

  // 밸류에이션 - 1% 허용
  per: 0.01,
  pbr: 0.01,
  eps: 0.01,
  bps: 0.01,

  // 수급 데이터 - 10% 허용
  foreignNetBuy: 0.1,
  institutionalNetBuy: 0.1,

  // 시장 데이터 - 1% 허용
  marketCap: 0.01,
};
```

### 4.3 신뢰도 점수 체계

| 검증 상태 | 기본 신뢰도 | 조건 |
|----------|:-----------:|------|
| **MATCH** | 98% | 모든 필드가 허용 오차 내 일치 |
| **PARTIAL** | 85% | 50% 이상 필드 일치, 일부 충돌 |
| **CONFLICT** | 70% | 충돌 필드가 있지만 일부 일치 |
| **SINGLE** | 65% | 한 소스만 데이터 제공 |
| **EMPTY** | 0% | 양쪽 모두 데이터 없음 |

**신뢰도 보정 공식**:
```
adjustedConfidence = baseConfidence × (0.7 + 0.3 × matchRatio)
```
- `matchRatio` = 일치 필드 수 / (일치 필드 수 + 충돌 필드 수)

---

## 5. 사용 방법

### 5.1 기본 사용법

```typescript
import { collectStockDataDualSource } from '@/lib/dual-source';

// 한국 주식 (삼성전자)
const samsungData = await collectStockDataDualSource('005930');

// 미국 주식 (애플)
const appleData = await collectStockDataDualSource('AAPL');

// 결과 확인
console.log(`종목명: ${samsungData.data.basicInfo.name}`);
console.log(`현재가: ${samsungData.data.priceData.currentPrice}`);
console.log(`신뢰도: ${(samsungData.confidence * 100).toFixed(1)}%`);
console.log(`검증 상태: ${samsungData.validation.status}`);
```

### 5.2 배치 수집

```typescript
import { collectStocksDataBatchDualSource } from '@/lib/dual-source';

const symbols = ['005930', '000660', '035720'];
const results = await collectStocksDataBatchDualSource(symbols, {
  timeout: 60000,
  logResults: true,
});

// Map<string, ValidatedStockData> 형태로 반환
for (const [symbol, data] of results) {
  console.log(`${symbol}: ${data.confidence * 100}% 신뢰도`);
}
```

### 5.3 단일 소스 사용 (빠른 조회)

```typescript
import { collectStockDataSingleSource } from '@/lib/dual-source';

// Source A (Agentic) 우선 사용
const dataA = await collectStockDataSingleSource('005930', 'A');

// Source B (API) 우선 사용
const dataB = await collectStockDataSingleSource('005930', 'B');
```

---

## 6. 시장별 데이터 소스

### 6.1 한국 주식 (KR)

| 소스 | 방식 | 대상 사이트 | 수집 데이터 |
|------|------|-------------|-------------|
| **Source A** | Agentic Screenshot | 네이버 금융 | 현재가, PER, PBR, EPS, BPS, 외국인 보유율 |
| **Source B** | REST API | 다음 금융 | 현재가, 거래량, 시가총액, 등락률 |

### 6.2 미국 주식 (US)

| 소스 | 방식 | 대상 사이트 | 수집 데이터 |
|------|------|-------------|-------------|
| **Source A** | Agentic Screenshot | Yahoo Finance | 현재가, PE Ratio, EPS, Market Cap, Beta |
| **Source B** | yahoo-finance2 | Yahoo Finance API | 현재가, 거래량, 52주 고저, 배당수익률 |

---

## 7. 환경별 동작

### 7.1 로컬 개발 환경

```
┌────────────────────────────────────────┐
│          로컬 환경 (npm run dev)        │
├────────────────────────────────────────┤
│                                         │
│  ✅ Agentic Screenshot 사용 가능         │
│  ✅ Puppeteer 정상 동작                  │
│  ✅ 듀얼 소스 완전 지원                   │
│                                         │
│  Source A: Agentic (Vision AI)         │
│  Source B: REST API                    │
│                                         │
└────────────────────────────────────────┘
```

### 7.2 서버리스 환경 (Vercel)

```
┌────────────────────────────────────────┐
│          Vercel 서버리스 환경           │
├────────────────────────────────────────┤
│                                         │
│  ⚠️ Puppeteer 사용 불가                 │
│  ✅ API 방식으로 자동 Fallback          │
│                                         │
│  Source A: Finnhub API (Fallback)      │
│  Source B: Yahoo Finance API           │
│                                         │
│  환경 감지:                             │
│  if (process.env.VERCEL) {             │
│    // Agentic 비활성화                  │
│    // API 모드 사용                     │
│  }                                     │
│                                         │
└────────────────────────────────────────┘
```

---

## 8. 에러 처리 및 Fallback

### 8.1 Fallback 전략

```typescript
// lib/dual-source/dual-source-collector.ts

async function collectKoreaStockDualSource(symbol: string) {
  const agentic = await initAgenticCrawler();

  // Source A: Agentic 또는 전통적 크롤링 (Fallback)
  let sourceAPromise;
  if (agentic) {
    // Agentic Screenshot 사용
    sourceAPromise = agentic.collectKoreaStock(symbol);
  } else {
    // Puppeteer 불가 시 전통적 크롤링으로 Fallback
    sourceAPromise = koreaStockCrawler.collectAll(symbol);
  }

  // Source B: 다음 금융 API (항상 사용)
  const sourceBPromise = koreaStockDaumCollector.collectAll(symbol);

  // 병렬 수집
  const [sourceA, sourceB] = await Promise.all([
    sourceAPromise.catch(handleError),
    sourceBPromise.catch(handleError),
  ]);

  // 검증 및 병합
  return validateAndMerge(sourceA, sourceB);
}
```

### 8.2 에러 시나리오별 동작

| 시나리오 | Source A | Source B | 결과 |
|----------|:--------:|:--------:|------|
| 양쪽 성공 | ✅ | ✅ | 교차 검증 후 병합 |
| A만 실패 | ❌ | ✅ | B 데이터 사용 (SINGLE) |
| B만 실패 | ✅ | ❌ | A 데이터 사용 (SINGLE) |
| 양쪽 실패 | ❌ | ❌ | 에러 throw |

---

## 9. 성능 지표

### 9.1 예상 수집 시간

| 환경 | Source A | Source B | 전체 (병렬) |
|------|:--------:|:--------:|:-----------:|
| 로컬 (Agentic) | 5-10초 | 0.5-1초 | 5-10초 |
| Vercel (API) | 0.5-1초 | 0.5-1초 | 0.5-1초 |

### 9.2 API 비용 (Agentic 사용 시)

| 항목 | 비용 |
|------|------|
| Gemini Vision API | ~$0.01-0.02/요청 |
| 일 100회 수집 기준 | ~$1-2/일 |
| 월간 예상 | ~$30-60/월 |

---

## 10. 확장 가이드

### 10.1 새로운 데이터 소스 추가

```typescript
// lib/dual-source/new-source-collector.ts

import type { StockDataCollector, CollectionResult } from './types';

export class NewSourceCollector implements StockDataCollector {
  async collectAll(symbol: string): Promise<CollectionResult<ComprehensiveStockData>> {
    const startTime = Date.now();

    try {
      // 1. 데이터 수집 로직
      const data = await fetchFromNewSource(symbol);

      // 2. 표준 형식으로 변환
      const normalizedData = normalizeToComprehensiveData(data);

      return {
        data: normalizedData,
        source: 'api',
        timestamp: Date.now(),
        success: true,
        latency: Date.now() - startTime,
      };
    } catch (error) {
      return {
        data: null,
        source: 'api',
        timestamp: Date.now(),
        success: false,
        error: error.message,
        latency: Date.now() - startTime,
      };
    }
  }
}
```

### 10.2 검증 규칙 커스터마이징

```typescript
// 커스텀 허용 오차 설정
const CUSTOM_TOLERANCE = {
  ...DEFAULT_TOLERANCE,
  currentPrice: 0.001,  // 0.1%로 더 엄격하게
  volume: 0.10,         // 10%로 더 느슨하게
};
```

---

## 11. 파일 구조

```
lib/dual-source/
├── index.ts                    # 모듈 진입점 및 export
├── types.ts                    # 타입 정의
├── dual-source-collector.ts    # 메인 수집 로직
├── validation-engine.ts        # 검증 엔진
├── agentic-crawler.ts          # Agentic Screenshot 크롤러
├── korea-stock-crawler.ts      # 한국 주식 전통적 크롤러
├── korea-stock-daum.ts         # 한국 주식 다음 API
├── us-stock-yahoo.ts           # 미국 주식 Yahoo API
├── us-stock-finnhub.ts         # 미국 주식 Finnhub API
└── us-stock-crawler.ts         # 미국 주식 Puppeteer 크롤러
```

---

## 12. 참고 자료

### 12.1 관련 문서
- [Agentic Web Browsing 분석 보고서](./AGENTIC_WEB_BROWSING_ANALYSIS.md)
- [데이터 소스 비교 분석](./DATA_SOURCE_COMPARISON.md)

### 12.2 외부 리소스
- [Puppeteer Documentation](https://pptr.dev/)
- [Gemini Vision API](https://ai.google.dev/gemini-api/docs/vision)
- [yahoo-finance2 Library](https://github.com/gadicc/yahoo-finance2)

---

*문서 작성: Claude Code*
*최종 업데이트: 2026-01-20*

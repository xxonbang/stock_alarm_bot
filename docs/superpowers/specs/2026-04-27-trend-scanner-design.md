# Trend Scanner Design

> **작성일**: 2026-04-27
> **대상 기능**: 매일 KST 07:30·20:00 자동 실행되는 뉴스·커뮤니티 트렌드 스캐너
> **상태**: Spec (구현 전)

---

## 1. 목적

매일 정해진 시각에 미국·한국의 주식 관련 뉴스와 유명 커뮤니티 게시글을 자동 수집하여, 공통적으로 언급되는 종목·섹터를 추출하고, TOP3 항목에 대해 데이터(수집된 텍스트) 기반의 비판적·객관적 전망을 텔레그램으로 발송한다.

기존 시스템(`src/main.py`)은 **보유·관심 종목 중심** 리포트인 반면, 본 기능은 **유니버스 전반의 트렌드 스캔**으로 성격이 다르다. 따라서 별도 entrypoint·별도 워크플로우로 격리하여 기존 흐름에 영향을 주지 않는다.

---

## 2. 핵심 결정 (브레인스토밍 합의)

| # | 항목 | 결정 |
|---|---|---|
| 1 | 기존 08:00 모닝 리포트와의 관계 | 별도 추가 (둘 다 발송) |
| 2 | 뉴스 소스 | 기존 코드 재활용 우선(Google News RSS) + 부족 시 보강 |
| 3 | 커뮤니티 소스 | 미국: Reddit 4곳 / 한국: 디시 주식갤 |
| 4 | 종목·섹터 추출 방식 | LLM(Gemini) 일괄 추출 |
| 5 | AI 호출 구조 | 3콜 (배치 추출 1 + TOP3 종합 1 + 전망 1) |
| 6 | 휴일·주말 동작 | 매일 발송 (스킵 없음) |
| 7 | 추가 발송 시각 | 20:00 KST에도 동일 동작 |
| 8 | 메시지 분량 | 2메시지 분할 (미국 / 한국) + 전망 3~4줄 |
| 9 | 데이터 신뢰 범위 | **수집된 텍스트만** 사용. 시세·지표 동봉 금지. 추측·할루시네이션 절대 금지 |
| 10 | 근거 표기 | B+C+Y: 인덱스 표기 + 빈도 표기 + 자동 매핑 검증 |
| 11 | 모듈 구조 | 신규 파일 분리 (`src/trend_scanner.py` + `trend_collectors/`) |
| 12 | 시간 윈도우 | 최근 24시간 |
| 13 | 스케줄링 | cron-job.org → GitHub `workflow_dispatch` API |

---

## 3. 데이터 흐름

```
[cron-job.org KST 07:30 / 20:00 매일]
   ↓ POST workflow_dispatch
[GitHub Actions: trend_scan.yml]
   ↓
[python -m src.trend_scanner]
   │
   ├── Step 0. 오늘자(KST) 인지
   │   └── now_kst, since = now_kst - 24h
   │
   ├── Step 1. 4배치 수집 (각 30개, 인덱스 ID 부착)
   │   ├── us_news      [미뉴스#1..#30]
   │   ├── us_community [미커뮤#1..#30]
   │   ├── kr_news      [한뉴스#1..#30]
   │   └── kr_community [한커뮤#1..#30]
   │
   ├── Step 2. AI 콜 #1 — 4배치 일괄 추출
   │   └── 각 배치 → 종목 10 + 섹터 10 (빈도 포함, 인덱스 인용 필수)
   │
   ├── Step 3. AI 콜 #2 — TOP3 종합
   │   └── 미국 TOP3 섹터·종목, 한국 TOP3 섹터·종목 + 선정 이유
   │
   ├── Step 4. AI 콜 #3 — 12개 항목 전망 생성
   │   └── 각 항목 3~4줄, [출처#N] 인덱스 인용 강제
   │
   ├── Step 5. 검증 (Y)
   │   ├── 출력의 [출처#N] 패턴 정규식 추출
   │   ├── 실제 수집된 인덱스와 매핑 비교
   │   └── 미매핑 발견 시 → 경고 로그 + 메시지 상단 `⚠️ 인덱스 검증 실패 N건`
   │
   └── Step 6. 텔레그램 발송
       ├── 메시지 1: 🇺🇸 미국 TOP3 섹터·종목·전망
       └── 메시지 2: 🇰🇷 한국 TOP3 섹터·종목·전망
```

---

## 4. 모듈 구조

```
src/
├── trend_scanner.py            # NEW. 메인 entrypoint
├── trend_collectors/           # NEW
│   ├── __init__.py
│   ├── base.py                 # 공통 타입 (CollectedItem dataclass), 인덱스 부착 유틸
│   ├── us_news.py              # Google News RSS (영문 키워드)
│   ├── us_community.py         # Reddit JSON
│   ├── kr_news.py              # Google News RSS (한글) + 한경/매경 RSS 보강
│   └── kr_community.py         # 디시 주식갤 (베스트/실시간 인기)
├── trend_extractor.py          # NEW. AI 콜 #1, #2, #3 + 검증 로직
├── trend_formatter.py          # NEW. 텔레그램 2메시지 포맷
├── notifier.py                 # 기존 재사용
├── ai_researcher.py            # 기존 재사용 (다중 키 폴백)
└── main.py                     # 변경 없음

config/prompts/
├── trend_extract.txt           # NEW. AI 콜 #1
├── trend_top3.txt              # NEW. AI 콜 #2
└── trend_outlook.txt           # NEW. AI 콜 #3

.github/workflows/
└── trend_scan.yml              # NEW. workflow_dispatch only

docs/
└── superpowers/specs/2026-04-27-trend-scanner-design.md  # 본 문서
```

### 4.1 컴포넌트 책임

| 컴포넌트 | 책임 | 의존성 |
|---|---|---|
| `trend_scanner.main()` | 흐름 제어, 로깅, abort 판단 | 모든 하위 모듈 |
| `trend_collectors.base.CollectedItem` | `{batch, idx, title, body, url, published_at}` 데이터 클래스 | - |
| `trend_collectors.*.collect(since, limit=30)` | 시간 윈도우 내 글 수집, ID 부착 | requests/feedparser/curl_cffi |
| `trend_extractor.extract_per_batch(batches)` | AI 콜 #1: 각 배치별 종목 10 + 섹터 10 | `ai_researcher` |
| `trend_extractor.select_top3(extracted)` | AI 콜 #2: 지역별 TOP3 섹터·종목 + 이유 | `ai_researcher` |
| `trend_extractor.generate_outlook(top3, batches)` | AI 콜 #3: 12개 항목 전망 (3~4줄) | `ai_researcher` |
| `trend_extractor.verify_indices(text, batches)` | 인덱스 매핑 검증 → `{ok: bool, missing: [...]}` | re |
| `trend_formatter.format_us(...)`, `format_kr(...)` | 텔레그램 메시지 2개 생성 | - |

### 4.2 데이터 형태

```python
# trend_collectors/base.py
@dataclass
class CollectedItem:
    batch: str          # "us_news" | "us_community" | "kr_news" | "kr_community"
    idx: int            # 1..30 (배치별 일련번호)
    title: str
    body: str           # 요약 또는 본문 일부
    url: str
    published_at: datetime  # KST

# 인덱스 표기 형식 (LLM 입력·출력 공통)
# us_news       → [미뉴스#1] ~ [미뉴스#30]
# us_community  → [미커뮤#1] ~ [미커뮤#30]
# kr_news       → [한뉴스#1] ~ [한뉴스#30]
# kr_community  → [한커뮤#1] ~ [한커뮤#30]
```

```python
# AI 콜 #1 출력 (Gemini JSON 모드)
{
  "us_news":      {"stocks": [{"name": str, "freq": int, "refs": [int, ...]}, ...×10],
                   "sectors": [...×10]},
  "us_community": {...},
  "kr_news":      {...},
  "kr_community": {...}
}

# AI 콜 #2 출력
{
  "us_top3_sectors": [{"name": str, "reason": str, "refs": [...]}, ...×3],
  "us_top3_stocks":  [...×3],
  "kr_top3_sectors": [...×3],
  "kr_top3_stocks":  [...×3]
}

# AI 콜 #3 출력
{
  "us_sector_outlook": [{"name": str, "outlook": str, "refs": [...]}, ...×3],
  "us_stock_outlook":  [...×3],
  "kr_sector_outlook": [...×3],
  "kr_stock_outlook":  [...×3]
}
```

---

## 5. 수집 소스 상세

### 5.1 미국 뉴스 (목표 30개)

- **1차**: Google News RSS 검색 — 키워드 `stock market`, `Wall Street`, `S&P 500`, `Nasdaq`
- **2차 보강** (1차에서 30개 미달 시): yfinance `Ticker.news`(인기 ETF SPY/QQQ 기준), Reuters Business RSS
- 24시간 내 글만 필터, URL 중복 제거. 본문 길이 200자 이상을 우선 정렬(미달 글도 30개 채우는 데 사용)

### 5.2 미국 커뮤니티 (목표 30개)

- **소스**: Reddit JSON 엔드포인트 (인증 불필요)
  - `https://www.reddit.com/r/wallstreetbets/hot.json?limit=N`
  - `https://www.reddit.com/r/stocks/hot.json?limit=N`
  - `https://www.reddit.com/r/investing/hot.json?limit=N`
  - `https://www.reddit.com/r/StockMarket/hot.json?limit=N`
- 4개 서브에서 최신 hot 글을 시간 가중·점수 가중으로 30개 추림
- 24시간 내 글만, NSFW/스팸 플래그 제외. 본문 또는 셀프텍스트 200자 이상을 우선 정렬(미달 글도 30개 채우는 데 사용)
- User-Agent: `trade-info-sender/1.0`

### 5.3 한국 뉴스 (목표 30개)

- **1차**: Google News RSS 검색 — 키워드 `한국 증시`, `코스피`, `코스닥`
- **2차 보강**: 한경 RSS, 매경 RSS (기존 `crawler.py`에서 사용 중)
- 24시간 내 글만, 중복 제거

### 5.4 한국 커뮤니티 (목표 30개)

- **소스**: 디시 주식갤러리 (https://gall.dcinside.com/board/lists/?id=stock_new1)
- 베스트(`?exception_mode=recommend`) + 실시간 인기글 혼합
- 24시간 내. 본문 길이 100자 이상을 우선 정렬(미달 글도 30개 채우는 데 사용)
- 봇 차단 대응: curl_cffi 세션 사용 (기존 `crawler.py` 패턴)
- 차단·구조 변경 시 fallback: 빈 배치로 진행 + 메시지에 `⚠️ kr_community 수집 실패` 표기

---

## 6. AI 프롬프트 설계 (할루시네이션 가드)

### 6.1 공통 시스템 제약 (3개 프롬프트 모두 헤더에 포함)

```
당신은 한국어로 응답하는 객관적 분석자입니다. 다음 제약을 절대 위반하지 마세요:

1. 입력으로 제공된 [출처#N] 텍스트에 명시되지 않은 사실·숫자·예측은
   어떤 형태로도 출력하지 마세요.
2. 다음 추측 표현 사용 금지:
   "예상된다", "전망된다", "~할 것이다", "아마도", "~로 보인다",
   "기대된다", "유력하다", "가능성이 크다"
3. 모든 주장은 [출처#N] 형식으로 인덱스를 인용해야 합니다.
   인덱스 없는 주장은 무효이며 출력 금지.
4. 빈도는 "30개 중 N건 언급" 형식으로 표기.
5. 사용 가능한 표현: "~라고 보도됨", "~로 언급됨", "~가 다뤄짐",
   "~건의 글에서 거론됨"
6. 입력 텍스트에 명시되지 않은 종목·섹터 이름을 새로 만들어내지 마세요.
```

### 6.2 AI 콜 #1 — 배치별 추출 (`config/prompts/trend_extract.txt`)

입력: 4배치 × 30개 글 (인덱스 부착 텍스트) + 위 공통 제약
출력 형식: JSON (위 4.2 참조)
지시: 각 배치별로 종목 상위 10개·섹터 상위 10개를 빈도순으로. 각 항목에 `refs` 배열로 인덱스 명시.

### 6.3 AI 콜 #2 — TOP3 종합 (`config/prompts/trend_top3.txt`)

입력: AI 콜 #1의 4배치 추출 결과 + 공통 제약
지시:
- 미국(미뉴스 + 미커뮤), 한국(한뉴스 + 한커뮤) 묶음별 빈도 가중 합산
- TOP3 섹터·TOP3 종목 선정 (지역별)
- 각 항목 `reason`에 빈도 + 인덱스 인용 ("미뉴스 30개 중 8건, 미커뮤 30개 중 5건 [미뉴스#3,#7,#12,#15,#18,#22,#25,#29] [미커뮤#2,#9,#14,#21,#27]")

### 6.4 AI 콜 #3 — 전망 생성 (`config/prompts/trend_outlook.txt`)

입력: TOP3 결과 + 원본 4배치 텍스트(해당 인덱스 글만 발췌) + 공통 제약
지시:
- 각 12개 항목에 대해 3~4줄의 전망
- **명시 가능 내용**: 텍스트에 등장한 호재·악재·이벤트·일정만
- **금지 내용**: 가격 예측, 목표가, "상승할 것", "하락할 것" 표현
- 형식: "[종목/섹터명] — (호재/악재/관찰 사항을 인덱스 인용하며 서술). 다만 (반대 시각·리스크가 텍스트에 있다면 인덱스 인용)."
- 텍스트에 반대 시각이 없으면 "반대 시각은 수집된 텍스트에 부재"라고 명시

### 6.5 사후 검증 (검증 Y)

```python
def verify_indices(ai_output: str, batches: dict[str, list[CollectedItem]]) -> dict:
    """
    출력에서 [미뉴스#N] / [미커뮤#N] / [한뉴스#N] / [한커뮤#N] 패턴을 추출하여
    실제 수집된 인덱스와 매핑 비교한다.

    Returns:
        {"ok": bool, "missing": [(batch, idx), ...], "total_refs": int}
    """
    label_to_batch = {
        "미뉴스": "us_news", "미커뮤": "us_community",
        "한뉴스": "kr_news", "한커뮤": "kr_community",
    }
    pattern = r'\[(미뉴스|미커뮤|한뉴스|한커뮤)#(\d+)\]'
    found = re.findall(pattern, ai_output)
    cited = {(label_to_batch[lbl], int(n)) for lbl, n in found}

    actual = {(b, item.idx) for b, items in batches.items() for item in items}
    missing = sorted(cited - actual)

    return {"ok": len(missing) == 0, "missing": missing, "total_refs": len(found)}
```

- 검증 실패해도 발송은 진행 (운영 단계에서 모니터링)
- 메시지 상단에 `⚠️ 인덱스 검증 실패 N건` 표기 (성공 시 표기 없음)
- 빈도 표기(`N건 언급`)는 검증 대상 제외 (오탐 방지)

---

## 7. 텔레그램 메시지 포맷

### 7.1 메시지 1 — 미국 (목표 ~2000자)

```
🇺🇸 [미국] 트렌드 스캔 — 2026-04-27 07:30 KST
수집: 미국 뉴스 30 + 미국 커뮤니티 30 (최근 24h)
[검증 실패 시 ⚠️ 인덱스 검증 실패 N건]

━━━━━━━━━━━━━━━━━━━━━━━━━
📊 TOP3 섹터
1. {섹터명} — 미뉴스 30개 중 N건, 미커뮤 30개 중 M건 [미뉴스#a,#b...] [미커뮤#c,#d...]
   {3~4줄 전망}
2. ...
3. ...

━━━━━━━━━━━━━━━━━━━━━━━━━
🏢 TOP3 종목
1. {종목명} — 미뉴스 30개 중 N건, 미커뮤 30개 중 M건 [미뉴스#a,#b...] [미커뮤#c,#d...]
   {3~4줄 전망}
2. ...
3. ...

━━━━━━━━━━━━━━━━━━━━━━━━━
※ 본 리포트는 수집된 텍스트만을 근거로 합니다. 투자 권유가 아닙니다.
```

### 7.2 메시지 2 — 한국 (구조 동일, 🇰🇷 한국)

### 7.3 길이 초과 시
- 한 메시지가 4096자 초과하면 같은 카테고리 내에서 추가 분할 (TOP3 섹터 / TOP3 종목)
- 분할 시 헤더 동일하게 유지

---

## 8. 에러 처리

| 시나리오 | 동작 |
|---|---|
| 4배치 중 일부 수집 0개 | 해당 배치 제외하고 진행, 메시지 상단 `⚠️ {batch} 수집 실패` 표기 |
| 모든 배치 수집 0개 | abort + 텔레그램 에러 메시지 1건 |
| 30개 미달(예: Reddit 22개) | 가능한 만큼 진행, 메시지에 `(22/30)` 표기 |
| AI 콜 실패 | 기존 `ai_researcher` 다중 키 폴백 사용. 모두 실패 시 abort + 에러 메시지 |
| AI 출력 JSON 파싱 실패 | 1회 재시도. 재실패 시 abort + 에러 메시지 |
| 인덱스 검증 실패 | 발송 진행, 메시지에 ⚠️ 표기 |
| 텔레그램 발송 실패 | 1회 재시도, 그 이후 로그만 (기존 `notifier` 패턴) |

---

## 9. 스케줄 & 배포

### 9.1 GitHub Actions 워크플로우

`.github/workflows/trend_scan.yml`

```yaml
name: Trend Scanner

on:
  workflow_dispatch:

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: python -m src.trend_scanner
        env:
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          CHAT_ID: ${{ secrets.CHAT_ID }}
          GOOGLE_API_KEY_01: ${{ secrets.GOOGLE_API_KEY_01 }}
          GOOGLE_API_KEY_02: ${{ secrets.GOOGLE_API_KEY_02 }}
          GOOGLE_API_KEY_03: ${{ secrets.GOOGLE_API_KEY_03 }}
```

### 9.2 cron-job.org 수동 등록 (사용자 작업)

| 시간 (KST) | cron 식 | Timezone |
|---|---|---|
| 07:30 매일 | `30 7 * * *` | Asia/Seoul |
| 20:00 매일 | `0 20 * * *` | Asia/Seoul |

**URL** (두 작업 동일):
```
POST https://api.github.com/repos/<owner>/trade_info_sender/actions/workflows/trend_scan.yml/dispatches
```

**Headers**:
```
Authorization: Bearer <GitHub PAT (Actions: Read and write)>
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2022-11-28
```

**Body**:
```json
{"ref":"main"}
```

기존 `theme_analysis` 프로젝트의 `docs/archive/cron-job-setup-guide.md` 패턴과 동일.

---

## 10. 테스트 전략

- **TEST_MODE** (`--test` 플래그 또는 `TEST_MODE=true` 환경변수)
  - 텔레그램 발송 대신 stdout 출력
  - 검증 결과(ok/missing) 콘솔 표시
- **수집기 단위 실행**: 각 collector를 독립 실행 가능
  ```
  python -m src.trend_collectors.us_news
  python -m src.trend_collectors.us_community
  python -m src.trend_collectors.kr_news
  python -m src.trend_collectors.kr_community
  ```
- **end-to-end 수동 검증** (첫 1주일):
  - 메시지의 `[출처#N]` 인덱스 sample-check (10건 무작위)
  - 추측 표현 잔존 여부 확인 ("예상", "전망", "~할 것" 등 grep)
  - 검증 실패 ⚠️ 발생 빈도 모니터링

---

## 11. 향후 개선 후보 (스펙 외)

- 인덱스 검증 안정화 후 메시지에서 [출처#N] 제거하고 빈도 표기만 유지 (사용자 피드백)
- 추가 커뮤니티 소스 (네이버 금융 종목토론실, Twitter/X)
- 시계열 비교 (어제 TOP3 대비 변화)
- 임베딩 기반 종목·섹터 정규화 (현재는 LLM 자율 처리)

---

## 12. 비결정 사항 (구현 시 결정)

- AI 콜 #1·#2·#3에 사용할 Gemini 모델 (현재 `ai_researcher`는 모델 폴백 자동) → 기존 설정 그대로 사용
- 디시 주식갤 수집 정확한 셀렉터 → 구현 단계에서 페이지 구조 확인 후 결정
- 한국 뉴스 보강 시 한경/매경 RSS 우선순위 → 구현 단계에서 응답 안정성 측정 후 결정

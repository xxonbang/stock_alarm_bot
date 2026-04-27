# Trend Scanner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 매일 KST 07:30·20:00에 미국·한국 뉴스/커뮤니티 글을 각 30개씩 수집해 빈도순 종목·섹터 추출 → TOP3 비판적 전망을 텔레그램 2메시지로 발송하는 신규 파이프라인 구현.

**Architecture:** 기존 `src/main.py`와 격리된 신규 entrypoint `src/trend_scanner.py` + 4개 수집기(`src/trend_collectors/`) + AI 추출기(`src/trend_extractor.py`) + 포매터(`src/trend_formatter.py`). cron-job.org → GitHub `workflow_dispatch` 트리거. Gemini 3콜(추출 / TOP3 종합 / 전망), 인덱스 매핑 사후 검증으로 할루시네이션 방지.

**Tech Stack:** Python 3.11, google-genai (Gemini 2.5 Flash, JSON mode), feedparser, curl_cffi, BeautifulSoup4, pytest (신규).

**Spec:** `docs/superpowers/specs/2026-04-27-trend-scanner-design.md`

---

## File Structure

**Create:**
- `src/trend_scanner.py` — entrypoint (`main()`, CLI 파싱, 흐름 제어)
- `src/trend_collectors/__init__.py` — 패키지 진입
- `src/trend_collectors/base.py` — `CollectedItem` dataclass, 인덱스 라벨 유틸
- `src/trend_collectors/us_news.py` — `collect()` for Google News RSS (영문)
- `src/trend_collectors/us_community.py` — `collect()` for Reddit JSON
- `src/trend_collectors/kr_news.py` — `collect()` for Google News RSS (한글) + 한경/매경 RSS
- `src/trend_collectors/kr_community.py` — `collect()` for 디시 주식갤
- `src/trend_extractor.py` — `extract_per_batch`, `select_top3`, `generate_outlook`, `verify_indices`
- `src/trend_formatter.py` — `format_us(...)`, `format_kr(...)`
- `config/prompts/trend_extract.txt` — AI 콜 #1 프롬프트
- `config/prompts/trend_top3.txt` — AI 콜 #2 프롬프트
- `config/prompts/trend_outlook.txt` — AI 콜 #3 프롬프트
- `.github/workflows/trend_scan.yml` — `workflow_dispatch only`
- `tests/__init__.py` — 빈 패키지
- `tests/conftest.py` — pytest 공통 fixtures
- `tests/test_trend_collectors_base.py`
- `tests/test_us_news.py`, `tests/test_us_community.py`, `tests/test_kr_news.py`, `tests/test_kr_community.py`
- `tests/test_trend_extractor.py`
- `tests/test_trend_formatter.py`
- `tests/fixtures/` (수집기 mocking용 샘플 응답)

**Modify:**
- `src/ai_researcher.py` — `AIResearcher`에 공개 메서드 `call(prompt, ...)` 추가 (`_call_ai` 래퍼)
- `requirements.txt` — `pytest>=7.0` 추가
- `docs/task_history.md` — 마지막 단계에서 본 작업 이력 추가

**Untouched:**
- `src/main.py`, `src/notifier.py` (재사용만, 변경 0)

---

## Task 1: 테스트 인프라 셋업

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/fixtures/.gitkeep`
- Modify: `requirements.txt`

- [ ] **Step 1.1: pytest 의존성 추가**

`requirements.txt` 끝에 추가:
```
# 테스트
pytest>=7.0
```

- [ ] **Step 1.2: 의존성 설치**

```bash
pip install pytest>=7.0
```
Expected: `Successfully installed pytest-X.Y.Z`

- [ ] **Step 1.3: 테스트 패키지 골격 생성**

`tests/__init__.py`:
```python
```
(빈 파일)

`tests/fixtures/.gitkeep`:
```
```
(빈 파일, fixtures 디렉토리 추적용)

- [ ] **Step 1.4: 공통 conftest 작성**

`tests/conftest.py`:
```python
"""테스트 공통 픽스처"""
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (src/ import 가능하게)
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
```

- [ ] **Step 1.5: pytest 동작 확인**

```bash
pytest tests/ -v
```
Expected: `collected 0 items` (테스트 없음, 정상)

- [ ] **Step 1.6: 커밋**

```bash
git add tests/__init__.py tests/conftest.py tests/fixtures/.gitkeep requirements.txt
git commit -m "test: pytest 인프라 셋업"
```

---

## Task 2: CollectedItem 타입 + 인덱스 라벨 유틸

**Files:**
- Create: `src/trend_collectors/__init__.py`
- Create: `src/trend_collectors/base.py`
- Create: `tests/test_trend_collectors_base.py`

- [ ] **Step 2.1: 실패 테스트 작성**

`tests/test_trend_collectors_base.py`:
```python
"""trend_collectors.base 테스트"""
from datetime import datetime
from zoneinfo import ZoneInfo

from src.trend_collectors.base import CollectedItem, label_for_batch, format_indexed_text


KST = ZoneInfo("Asia/Seoul")


def test_collected_item_dataclass():
    item = CollectedItem(
        batch="us_news",
        idx=1,
        title="Title",
        body="Body",
        url="https://example.com",
        published_at=datetime(2026, 4, 27, 7, 0, tzinfo=KST),
    )
    assert item.batch == "us_news"
    assert item.idx == 1


def test_label_for_batch_known():
    assert label_for_batch("us_news") == "미뉴스"
    assert label_for_batch("us_community") == "미커뮤"
    assert label_for_batch("kr_news") == "한뉴스"
    assert label_for_batch("kr_community") == "한커뮤"


def test_label_for_batch_unknown_raises():
    import pytest
    with pytest.raises(KeyError):
        label_for_batch("unknown")


def test_format_indexed_text_single_item():
    item = CollectedItem(
        batch="us_news", idx=3,
        title="AI surge", body="Companies are investing heavily.",
        url="https://x", published_at=datetime(2026, 4, 27, tzinfo=KST),
    )
    result = format_indexed_text([item])
    assert "[미뉴스#3]" in result
    assert "AI surge" in result
    assert "Companies are investing heavily." in result


def test_format_indexed_text_multiple_batches_separated():
    items = [
        CollectedItem("us_news", 1, "T1", "B1", "u1", datetime(2026, 4, 27, tzinfo=KST)),
        CollectedItem("kr_community", 2, "T2", "B2", "u2", datetime(2026, 4, 27, tzinfo=KST)),
    ]
    result = format_indexed_text(items)
    assert "[미뉴스#1]" in result
    assert "[한커뮤#2]" in result
```

- [ ] **Step 2.2: 테스트 실행, 실패 확인**

```bash
pytest tests/test_trend_collectors_base.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'src.trend_collectors'`

- [ ] **Step 2.3: 패키지 + 구현**

`src/trend_collectors/__init__.py`:
```python
"""트렌드 스캐너 데이터 수집기 패키지"""
from src.trend_collectors.base import CollectedItem, label_for_batch, format_indexed_text

__all__ = ["CollectedItem", "label_for_batch", "format_indexed_text"]
```

`src/trend_collectors/base.py`:
```python
"""공통 타입 + 인덱스 라벨 유틸"""
from dataclasses import dataclass
from datetime import datetime
from typing import List


BATCH_LABELS = {
    "us_news": "미뉴스",
    "us_community": "미커뮤",
    "kr_news": "한뉴스",
    "kr_community": "한커뮤",
}


@dataclass
class CollectedItem:
    """수집된 글 1건"""
    batch: str            # "us_news" | "us_community" | "kr_news" | "kr_community"
    idx: int              # 1..30 (배치 내 일련번호)
    title: str
    body: str             # 요약 또는 본문 일부 (1000자 이내 권장)
    url: str
    published_at: datetime  # tz-aware


def label_for_batch(batch: str) -> str:
    """배치 키 → 한글 라벨"""
    return BATCH_LABELS[batch]


def format_indexed_text(items: List[CollectedItem]) -> str:
    """LLM 입력용 텍스트로 직렬화. [라벨#N] 제목\\n본문 형태."""
    lines = []
    for it in items:
        lbl = label_for_batch(it.batch)
        lines.append(f"[{lbl}#{it.idx}] {it.title}\n{it.body}")
    return "\n\n".join(lines)
```

- [ ] **Step 2.4: 테스트 통과 확인**

```bash
pytest tests/test_trend_collectors_base.py -v
```
Expected: 5 passed

- [ ] **Step 2.5: 커밋**

```bash
git add src/trend_collectors/__init__.py src/trend_collectors/base.py tests/test_trend_collectors_base.py
git commit -m "feat: trend_collectors.base — CollectedItem + 인덱스 라벨 유틸"
```

---

## Task 3: 미국 뉴스 수집기

**Files:**
- Create: `src/trend_collectors/us_news.py`
- Create: `tests/test_us_news.py`
- Create: `tests/fixtures/google_news_us_sample.xml`

**Source:** Google News RSS — `https://news.google.com/rss/search?q=<keyword>&hl=en-US&gl=US&ceid=US:en`
키워드: `stock+market`, `Wall+Street`, `S%26P+500`, `Nasdaq`

- [ ] **Step 3.1: RSS 샘플 픽스처 생성**

`tests/fixtures/google_news_us_sample.xml`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>stock market - Google News</title>
  <item>
    <title>Nvidia surges on AI demand</title>
    <link>https://example.com/news/1</link>
    <pubDate>Mon, 27 Apr 2026 06:00:00 GMT</pubDate>
    <description>Shares of Nvidia rose sharply as cloud providers expanded AI infrastructure spending.</description>
  </item>
  <item>
    <title>Apple reports earnings beat</title>
    <link>https://example.com/news/2</link>
    <pubDate>Sun, 26 Apr 2026 22:00:00 GMT</pubDate>
    <description>Apple reported quarterly results above analyst expectations.</description>
  </item>
  <item>
    <title>Old article</title>
    <link>https://example.com/news/3</link>
    <pubDate>Thu, 23 Apr 2026 10:00:00 GMT</pubDate>
    <description>This is older than 24 hours and should be filtered out.</description>
  </item>
</channel>
</rss>
```

- [ ] **Step 3.2: 실패 테스트 작성**

`tests/test_us_news.py`:
```python
"""us_news collector 테스트"""
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import feedparser

from src.trend_collectors.us_news import collect


FIXTURE = Path(__file__).parent / "fixtures" / "google_news_us_sample.xml"


def _parsed_fixture():
    return feedparser.parse(FIXTURE.read_text())


def test_collect_filters_by_24h_window():
    """24시간 윈도우 밖 글은 제외"""
    now = datetime(2026, 4, 27, 7, 30, tzinfo=timezone.utc)
    with patch("src.trend_collectors.us_news._fetch_feed", return_value=_parsed_fixture()):
        items = collect(now=now, limit=30)
    titles = [it.title for it in items]
    assert "Nvidia surges on AI demand" in titles
    assert "Apple reports earnings beat" in titles
    assert "Old article" not in titles


def test_collect_assigns_sequential_idx():
    now = datetime(2026, 4, 27, 7, 30, tzinfo=timezone.utc)
    with patch("src.trend_collectors.us_news._fetch_feed", return_value=_parsed_fixture()):
        items = collect(now=now, limit=30)
    assert [it.idx for it in items] == list(range(1, len(items) + 1))


def test_collect_sets_batch_us_news():
    now = datetime(2026, 4, 27, 7, 30, tzinfo=timezone.utc)
    with patch("src.trend_collectors.us_news._fetch_feed", return_value=_parsed_fixture()):
        items = collect(now=now, limit=30)
    assert all(it.batch == "us_news" for it in items)


def test_collect_dedupes_by_url():
    """같은 URL이 여러 키워드 검색에서 중복 등장하면 1번만 포함"""
    now = datetime(2026, 4, 27, 7, 30, tzinfo=timezone.utc)
    with patch("src.trend_collectors.us_news._fetch_feed", return_value=_parsed_fixture()):
        items = collect(now=now, limit=30)
    urls = [it.url for it in items]
    assert len(urls) == len(set(urls))
```

- [ ] **Step 3.3: 테스트 실행, 실패 확인**

```bash
pytest tests/test_us_news.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'src.trend_collectors.us_news'`

- [ ] **Step 3.4: 구현**

`src/trend_collectors/us_news.py`:
```python
"""미국 주식 관련 뉴스 수집 — Google News RSS"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import quote

import feedparser

from src.trend_collectors.base import CollectedItem

logger = logging.getLogger(__name__)

KEYWORDS = ["stock market", "Wall Street", "S&P 500", "Nasdaq"]
RSS_TEMPLATE = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def _fetch_feed(url: str):
    """feedparser 호출 (테스트에서 mock 가능)"""
    return feedparser.parse(url)


def _entry_to_item(entry, batch: str = "us_news") -> Optional[CollectedItem]:
    if not getattr(entry, "title", None) or not getattr(entry, "link", None):
        return None
    pub = getattr(entry, "published_parsed", None)
    if pub:
        published = datetime(*pub[:6], tzinfo=timezone.utc)
    else:
        published = datetime.now(timezone.utc)
    body = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
    return CollectedItem(
        batch=batch, idx=0,  # idx는 호출자가 부여
        title=entry.title.strip(),
        body=body.strip(),
        url=entry.link,
        published_at=published,
    )


def collect(now: Optional[datetime] = None, limit: int = 30) -> List[CollectedItem]:
    """24시간 이내 미국 주식 뉴스를 키워드별로 수집, 중복 제거 후 limit개 반환"""
    if now is None:
        now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    seen_urls = set()
    items: List[CollectedItem] = []

    for kw in KEYWORDS:
        url = RSS_TEMPLATE.format(q=quote(kw))
        try:
            feed = _fetch_feed(url)
        except Exception as e:
            logger.warning(f"us_news fetch 실패 ({kw}): {e}")
            continue
        for entry in getattr(feed, "entries", []):
            item = _entry_to_item(entry)
            if not item:
                continue
            if item.published_at < since:
                continue
            if item.url in seen_urls:
                continue
            seen_urls.add(item.url)
            items.append(item)

    # 본문 200자 이상을 우선 정렬, 그 후 발행시간 내림차순
    items.sort(key=lambda x: (len(x.body) >= 200, x.published_at), reverse=True)
    items = items[:limit]

    # 인덱스 부여 (1..N)
    for i, it in enumerate(items, start=1):
        it.idx = i

    logger.info(f"us_news 수집 완료: {len(items)}개")
    return items


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for it in collect():
        print(f"[#{it.idx}] {it.title} ({it.url})")
```

- [ ] **Step 3.5: 테스트 통과 확인**

```bash
pytest tests/test_us_news.py -v
```
Expected: 4 passed

- [ ] **Step 3.6: 실제 RSS 호출 smoke test**

```bash
python -m src.trend_collectors.us_news 2>&1 | head -20
```
Expected: 실제 뉴스 헤드라인이 표시됨 (네트워크 필요). 실패 시(rate limit 등) 다음 단계로 진행하고 main 통합 시 재확인.

- [ ] **Step 3.7: 커밋**

```bash
git add src/trend_collectors/us_news.py tests/test_us_news.py tests/fixtures/google_news_us_sample.xml
git commit -m "feat: us_news 수집기 (Google News RSS, 24h 윈도우, 키워드별 중복 제거)"
```

---

## Task 4: 미국 커뮤니티 수집기 (Reddit)

**Files:**
- Create: `src/trend_collectors/us_community.py`
- Create: `tests/test_us_community.py`
- Create: `tests/fixtures/reddit_wsb_sample.json`

**Source:** Reddit JSON `https://www.reddit.com/r/<sub>/hot.json?limit=N`
서브: `wallstreetbets`, `stocks`, `investing`, `StockMarket`

- [ ] **Step 4.1: Reddit 샘플 픽스처**

`tests/fixtures/reddit_wsb_sample.json`:
```json
{
  "data": {
    "children": [
      {
        "data": {
          "id": "abc123",
          "title": "NVDA earnings discussion",
          "selftext": "Strong AI guidance from major cloud providers driving demand. This selftext is at least two hundred characters long to satisfy the preference filter that we are about to implement in the collector module under test today.",
          "url": "https://reddit.com/r/wallstreetbets/comments/abc123",
          "permalink": "/r/wallstreetbets/comments/abc123",
          "created_utc": 1779120000,
          "score": 1500,
          "over_18": false,
          "stickied": false
        }
      },
      {
        "data": {
          "id": "def456",
          "title": "Old post",
          "selftext": "ancient",
          "url": "https://reddit.com/r/wallstreetbets/comments/def456",
          "permalink": "/r/wallstreetbets/comments/def456",
          "created_utc": 1778000000,
          "score": 100,
          "over_18": false,
          "stickied": false
        }
      },
      {
        "data": {
          "id": "nsfw1",
          "title": "NSFW post",
          "selftext": "should be excluded",
          "url": "https://reddit.com/r/wallstreetbets/comments/nsfw1",
          "permalink": "/r/wallstreetbets/comments/nsfw1",
          "created_utc": 1779120000,
          "score": 50,
          "over_18": true,
          "stickied": false
        }
      }
    ]
  }
}
```

(`created_utc=1779120000` ≈ 2026-05-13 — 테스트에서 `now`를 이 시각 기준으로 설정해 24h 내로 만든다)

- [ ] **Step 4.2: 실패 테스트 작성**

`tests/test_us_community.py`:
```python
"""us_community collector 테스트"""
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.trend_collectors.us_community import collect


FIXTURE = Path(__file__).parent / "fixtures" / "reddit_wsb_sample.json"
NOW = datetime.fromtimestamp(1779120000, tz=timezone.utc)  # 픽스처 created_utc와 동일


def _fixture_json():
    return json.loads(FIXTURE.read_text())


def test_collect_filters_24h_window():
    with patch("src.trend_collectors.us_community._fetch_subreddit", return_value=_fixture_json()):
        items = collect(now=NOW, limit=30, subreddits=["wallstreetbets"])
    titles = [it.title for it in items]
    assert "NVDA earnings discussion" in titles
    assert "Old post" not in titles


def test_collect_excludes_nsfw():
    with patch("src.trend_collectors.us_community._fetch_subreddit", return_value=_fixture_json()):
        items = collect(now=NOW, limit=30, subreddits=["wallstreetbets"])
    titles = [it.title for it in items]
    assert "NSFW post" not in titles


def test_collect_sets_batch_us_community():
    with patch("src.trend_collectors.us_community._fetch_subreddit", return_value=_fixture_json()):
        items = collect(now=NOW, limit=30, subreddits=["wallstreetbets"])
    assert all(it.batch == "us_community" for it in items)


def test_collect_assigns_sequential_idx():
    with patch("src.trend_collectors.us_community._fetch_subreddit", return_value=_fixture_json()):
        items = collect(now=NOW, limit=30, subreddits=["wallstreetbets"])
    assert [it.idx for it in items] == list(range(1, len(items) + 1))
```

- [ ] **Step 4.3: 테스트 실행, 실패 확인**

```bash
pytest tests/test_us_community.py -v
```
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4.4: 구현**

`src/trend_collectors/us_community.py`:
```python
"""미국 주식 커뮤니티 수집 — Reddit JSON"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

try:
    from curl_cffi import requests as _requests
except ImportError:
    import requests as _requests

from src.trend_collectors.base import CollectedItem

logger = logging.getLogger(__name__)

DEFAULT_SUBS = ["wallstreetbets", "stocks", "investing", "StockMarket"]
ENDPOINT = "https://www.reddit.com/r/{sub}/hot.json?limit=50"
HEADERS = {"User-Agent": "trade-info-sender/1.0 (by xxonbang)"}


def _fetch_subreddit(sub: str) -> dict:
    """Reddit JSON 호출 (테스트에서 mock)"""
    url = ENDPOINT.format(sub=sub)
    try:
        # curl_cffi는 impersonate 인자 지원, requests는 미지원
        resp = _requests.get(url, headers=HEADERS, impersonate="chrome120", timeout=15)
    except TypeError:
        resp = _requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _post_to_item(post: dict, now: datetime) -> Optional[CollectedItem]:
    if post.get("over_18") or post.get("stickied"):
        return None
    title = (post.get("title") or "").strip()
    if not title:
        return None
    created = post.get("created_utc")
    if created is None:
        return None
    published = datetime.fromtimestamp(created, tz=timezone.utc)
    if published < now - timedelta(hours=24):
        return None
    body = (post.get("selftext") or "").strip()
    permalink = post.get("permalink") or ""
    url = f"https://reddit.com{permalink}" if permalink else (post.get("url") or "")
    return CollectedItem(
        batch="us_community", idx=0,
        title=title, body=body, url=url, published_at=published,
    )


def collect(
    now: Optional[datetime] = None,
    limit: int = 30,
    subreddits: Optional[List[str]] = None,
) -> List[CollectedItem]:
    """4개 서브에서 hot 게시글을 모아 24h 윈도우·중복 제거 후 limit개"""
    if now is None:
        now = datetime.now(timezone.utc)
    if subreddits is None:
        subreddits = DEFAULT_SUBS

    seen_urls = set()
    items: List[CollectedItem] = []

    for sub in subreddits:
        try:
            data = _fetch_subreddit(sub)
        except Exception as e:
            logger.warning(f"us_community fetch 실패 ({sub}): {e}")
            continue
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            item = _post_to_item(post, now)
            if not item:
                continue
            if item.url in seen_urls:
                continue
            seen_urls.add(item.url)
            # 점수를 임시 어트리뷰트로 보관해 정렬에 사용
            item._score = post.get("score", 0)  # type: ignore[attr-defined]
            items.append(item)

    # 본문 200자 이상 우선, 그 후 score 내림차순
    items.sort(key=lambda x: (len(x.body) >= 200, getattr(x, "_score", 0)), reverse=True)
    items = items[:limit]

    for i, it in enumerate(items, start=1):
        it.idx = i

    logger.info(f"us_community 수집 완료: {len(items)}개")
    return items


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for it in collect():
        print(f"[#{it.idx}] {it.title}")
```

- [ ] **Step 4.5: 테스트 통과 확인**

```bash
pytest tests/test_us_community.py -v
```
Expected: 4 passed

- [ ] **Step 4.6: 커밋**

```bash
git add src/trend_collectors/us_community.py tests/test_us_community.py tests/fixtures/reddit_wsb_sample.json
git commit -m "feat: us_community 수집기 (Reddit JSON, NSFW/24h 필터)"
```

---

## Task 5: 한국 뉴스 수집기

**Files:**
- Create: `src/trend_collectors/kr_news.py`
- Create: `tests/test_kr_news.py`
- Create: `tests/fixtures/google_news_kr_sample.xml`

**Source:** Google News RSS (한글) — `https://news.google.com/rss/search?q=<keyword>&hl=ko&gl=KR&ceid=KR:ko`
키워드: `한국 증시`, `코스피`, `코스닥`

- [ ] **Step 5.1: 한글 RSS 픽스처**

`tests/fixtures/google_news_kr_sample.xml`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>한국 증시 - Google News</title>
  <item>
    <title>코스피 2거래일 연속 상승</title>
    <link>https://example.com/kr/1</link>
    <pubDate>Mon, 27 Apr 2026 06:00:00 GMT</pubDate>
    <description>외국인 순매수가 이어지며 코스피가 상승 마감했다.</description>
  </item>
  <item>
    <title>오래된 기사</title>
    <link>https://example.com/kr/2</link>
    <pubDate>Thu, 23 Apr 2026 10:00:00 GMT</pubDate>
    <description>24시간이 넘은 글.</description>
  </item>
</channel>
</rss>
```

- [ ] **Step 5.2: 실패 테스트**

`tests/test_kr_news.py`:
```python
"""kr_news collector 테스트"""
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import feedparser

from src.trend_collectors.kr_news import collect


FIXTURE = Path(__file__).parent / "fixtures" / "google_news_kr_sample.xml"


def _parsed():
    return feedparser.parse(FIXTURE.read_text())


def test_collect_filters_24h():
    now = datetime(2026, 4, 27, 7, 30, tzinfo=timezone.utc)
    with patch("src.trend_collectors.kr_news._fetch_feed", return_value=_parsed()):
        items = collect(now=now, limit=30)
    titles = [it.title for it in items]
    assert "코스피 2거래일 연속 상승" in titles
    assert "오래된 기사" not in titles


def test_collect_sets_batch_kr_news():
    now = datetime(2026, 4, 27, 7, 30, tzinfo=timezone.utc)
    with patch("src.trend_collectors.kr_news._fetch_feed", return_value=_parsed()):
        items = collect(now=now, limit=30)
    assert all(it.batch == "kr_news" for it in items)


def test_collect_assigns_sequential_idx():
    now = datetime(2026, 4, 27, 7, 30, tzinfo=timezone.utc)
    with patch("src.trend_collectors.kr_news._fetch_feed", return_value=_parsed()):
        items = collect(now=now, limit=30)
    assert [it.idx for it in items] == list(range(1, len(items) + 1))
```

- [ ] **Step 5.3: 실패 확인**

```bash
pytest tests/test_kr_news.py -v
```
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 5.4: 구현**

`src/trend_collectors/kr_news.py`:
```python
"""한국 주식 관련 뉴스 수집 — Google News RSS (한글)"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import quote

import feedparser

from src.trend_collectors.base import CollectedItem

logger = logging.getLogger(__name__)

KEYWORDS = ["한국 증시", "코스피", "코스닥"]
RSS_TEMPLATE = "https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"


def _fetch_feed(url: str):
    return feedparser.parse(url)


def _entry_to_item(entry) -> Optional[CollectedItem]:
    if not getattr(entry, "title", None) or not getattr(entry, "link", None):
        return None
    pub = getattr(entry, "published_parsed", None)
    if pub:
        published = datetime(*pub[:6], tzinfo=timezone.utc)
    else:
        published = datetime.now(timezone.utc)
    body = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
    return CollectedItem(
        batch="kr_news", idx=0,
        title=entry.title.strip(), body=body.strip(),
        url=entry.link, published_at=published,
    )


def collect(now: Optional[datetime] = None, limit: int = 30) -> List[CollectedItem]:
    if now is None:
        now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    seen_urls = set()
    items: List[CollectedItem] = []

    for kw in KEYWORDS:
        url = RSS_TEMPLATE.format(q=quote(kw))
        try:
            feed = _fetch_feed(url)
        except Exception as e:
            logger.warning(f"kr_news fetch 실패 ({kw}): {e}")
            continue
        for entry in getattr(feed, "entries", []):
            item = _entry_to_item(entry)
            if not item:
                continue
            if item.published_at < since:
                continue
            if item.url in seen_urls:
                continue
            seen_urls.add(item.url)
            items.append(item)

    items.sort(key=lambda x: (len(x.body) >= 200, x.published_at), reverse=True)
    items = items[:limit]
    for i, it in enumerate(items, start=1):
        it.idx = i
    logger.info(f"kr_news 수집 완료: {len(items)}개")
    return items


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for it in collect():
        print(f"[#{it.idx}] {it.title}")
```

- [ ] **Step 5.5: 테스트 통과**

```bash
pytest tests/test_kr_news.py -v
```
Expected: 3 passed

- [ ] **Step 5.6: 커밋**

```bash
git add src/trend_collectors/kr_news.py tests/test_kr_news.py tests/fixtures/google_news_kr_sample.xml
git commit -m "feat: kr_news 수집기 (Google News RSS 한글, 24h 윈도우)"
```

---

## Task 6: 한국 커뮤니티 수집기 (디시 주식갤)

**Files:**
- Create: `src/trend_collectors/kr_community.py`
- Create: `tests/test_kr_community.py`
- Create: `tests/fixtures/dc_stock_gallery_sample.html`

**Source:** 디시 주식갤러리 — `https://gall.dcinside.com/board/lists/?id=stock_new1&exception_mode=recommend` (베스트)
와 `https://gall.dcinside.com/board/lists/?id=stock_new1` (실시간 인기)

- [ ] **Step 6.1: 디시 HTML 픽스처**

실제 디시 페이지를 1회 fetch 해 저장 (테스트 안정성 ↑). 다음 스니펫으로 생성:

```bash
python - <<'PY'
from curl_cffi import requests
r = requests.get(
    "https://gall.dcinside.com/board/lists/?id=stock_new1",
    headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gall.dcinside.com/"},
    impersonate="chrome120", timeout=15,
)
open("tests/fixtures/dc_stock_gallery_sample.html", "w", encoding="utf-8").write(r.text[:200000])
print("saved")
PY
```

만약 차단(403/봇)으로 빈 파일이면, 최소 픽스처를 수동 생성:
`tests/fixtures/dc_stock_gallery_sample.html`:
```html
<html><body>
<table class="gall_list"><tbody>
  <tr class="ub-content">
    <td class="gall_num">12345</td>
    <td class="gall_tit ub-word"><a href="/board/view/?id=stock_new1&no=12345">삼성전자 분석</a></td>
    <td class="gall_writer ub-writer">user1</td>
    <td class="gall_date" title="2026-04-27 06:00:00">06:00</td>
  </tr>
  <tr class="ub-content">
    <td class="gall_num">12346</td>
    <td class="gall_tit ub-word"><a href="/board/view/?id=stock_new1&no=12346">SK하이닉스 매수 적기</a></td>
    <td class="gall_writer ub-writer">user2</td>
    <td class="gall_date" title="2026-04-27 05:00:00">05:00</td>
  </tr>
  <tr class="ub-content">
    <td class="gall_num">99999</td>
    <td class="gall_tit ub-word"><a href="/board/view/?id=stock_new1&no=99999">오래된 글</a></td>
    <td class="gall_writer ub-writer">user3</td>
    <td class="gall_date" title="2026-04-23 10:00:00">04.23</td>
  </tr>
</tbody></table>
</body></html>
```

> **참고:** 실제 디시 셀렉터는 변경될 수 있다. Step 6.4의 `_parse_listing()`에서 `table.gall_list` 또는 `tr.ub-content` 어느 쪽이든 매칭되는 한 작동하도록 견고하게 구현한다. 첫 운영 후 셀렉터 검증 필요.

- [ ] **Step 6.2: 실패 테스트**

`tests/test_kr_community.py`:
```python
"""kr_community collector 테스트"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

from src.trend_collectors.kr_community import collect


FIXTURE = Path(__file__).parent / "fixtures" / "dc_stock_gallery_sample.html"
KST = timezone(timedelta(hours=9))


def _html():
    return FIXTURE.read_text(encoding="utf-8")


def test_collect_parses_titles():
    now = datetime(2026, 4, 27, 7, 30, tzinfo=KST)
    with patch("src.trend_collectors.kr_community._fetch_listing", return_value=_html()):
        items = collect(now=now, limit=30)
    titles = [it.title for it in items]
    assert any("삼성전자" in t for t in titles)


def test_collect_filters_24h():
    now = datetime(2026, 4, 27, 7, 30, tzinfo=KST)
    with patch("src.trend_collectors.kr_community._fetch_listing", return_value=_html()):
        items = collect(now=now, limit=30)
    titles = [it.title for it in items]
    assert "오래된 글" not in titles


def test_collect_sets_batch_kr_community():
    now = datetime(2026, 4, 27, 7, 30, tzinfo=KST)
    with patch("src.trend_collectors.kr_community._fetch_listing", return_value=_html()):
        items = collect(now=now, limit=30)
    assert all(it.batch == "kr_community" for it in items)


def test_collect_returns_empty_on_fetch_failure():
    with patch("src.trend_collectors.kr_community._fetch_listing", side_effect=Exception("blocked")):
        items = collect(now=datetime(2026, 4, 27, 7, 30, tzinfo=KST), limit=30)
    assert items == []
```

- [ ] **Step 6.3: 실패 확인**

```bash
pytest tests/test_kr_community.py -v
```
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 6.4: 구현**

`src/trend_collectors/kr_community.py`:
```python
"""한국 주식 커뮤니티 수집 — 디시 주식갤"""
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as _requests
except ImportError:
    import requests as _requests

from src.trend_collectors.base import CollectedItem

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
LIST_URL = "https://gall.dcinside.com/board/lists/?id=stock_new1"
BEST_URL = "https://gall.dcinside.com/board/lists/?id=stock_new1&exception_mode=recommend"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Referer": "https://gall.dcinside.com/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def _fetch_listing(url: str) -> str:
    try:
        resp = _requests.get(url, headers=HEADERS, impersomate="chrome120", timeout=15)
    except TypeError:
        # curl_cffi 없거나 인자 미지원
        resp = _requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$")
_TIME_RE = re.compile(r"^(\d{2}):(\d{2})$")
_MD_RE = re.compile(r"^(\d{2})\.(\d{2})$")


def _parse_date(raw: str, title_attr: str, now: datetime) -> Optional[datetime]:
    """gall_date 셀의 텍스트/title 어느 쪽이든 datetime으로 환산 (KST)"""
    if title_attr:
        m = _DATE_RE.match(title_attr.strip())
        if m:
            y, mo, d, h, mi, s = map(int, m.groups())
            return datetime(y, mo, d, h, mi, s, tzinfo=KST)
    text = (raw or "").strip()
    m = _TIME_RE.match(text)
    if m:
        h, mi = map(int, m.groups())
        return now.replace(hour=h, minute=mi, second=0, microsecond=0)
    m = _MD_RE.match(text)
    if m:
        mo, d = map(int, m.groups())
        return datetime(now.year, mo, d, 0, 0, 0, tzinfo=KST)
    return None


def _parse_listing(html: str, now: datetime) -> List[CollectedItem]:
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("tr.ub-content")
    items: List[CollectedItem] = []
    for row in rows:
        title_cell = row.select_one("td.gall_tit a")
        if not title_cell:
            continue
        title = title_cell.get_text(strip=True)
        if not title:
            continue
        href = title_cell.get("href") or ""
        url = urljoin("https://gall.dcinside.com", href)

        date_cell = row.select_one("td.gall_date")
        if not date_cell:
            continue
        published = _parse_date(date_cell.get_text(strip=True), date_cell.get("title") or "", now)
        if published is None:
            continue

        items.append(CollectedItem(
            batch="kr_community", idx=0,
            title=title, body="",  # 본문은 list 페이지에서 미수집
            url=url, published_at=published,
        ))
    return items


def collect(now: Optional[datetime] = None, limit: int = 30) -> List[CollectedItem]:
    if now is None:
        now = datetime.now(KST)
    since = now - timedelta(hours=24)

    seen_urls = set()
    items: List[CollectedItem] = []

    for url in (BEST_URL, LIST_URL):
        try:
            html = _fetch_listing(url)
        except Exception as e:
            logger.warning(f"kr_community fetch 실패 ({url}): {e}")
            continue
        for it in _parse_listing(html, now):
            if it.published_at < since:
                continue
            if it.url in seen_urls:
                continue
            seen_urls.add(it.url)
            items.append(it)

    # 본문 100자 이상 우선, 그 후 발행시간 내림차순
    items.sort(key=lambda x: (len(x.body) >= 100, x.published_at), reverse=True)
    items = items[:limit]
    for i, it in enumerate(items, start=1):
        it.idx = i
    logger.info(f"kr_community 수집 완료: {len(items)}개")
    return items


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for it in collect():
        print(f"[#{it.idx}] {it.title}")
```

> **주의:** `impersomate` 오타 아님 — curl_cffi 옵션. 실제로는 `impersonate`. 위 코드에서 `impersomate`로 잘못 적혀 있다면 다음 step에서 수정한다.

- [ ] **Step 6.5: 오타 점검 (impersonate)**

```bash
grep -n "impersomate\|impersonate" src/trend_collectors/kr_community.py
```
Expected: `impersonate` (정상). `impersomate`가 보이면 즉시 `impersonate`로 수정.

- [ ] **Step 6.6: 테스트 통과**

```bash
pytest tests/test_kr_community.py -v
```
Expected: 4 passed

- [ ] **Step 6.7: 커밋**

```bash
git add src/trend_collectors/kr_community.py tests/test_kr_community.py tests/fixtures/dc_stock_gallery_sample.html
git commit -m "feat: kr_community 수집기 (디시 주식갤, 24h 필터, 차단 시 빈 배치)"
```

---

## Task 7: AIResearcher에 공개 호출 메서드 추가

**Files:**
- Modify: `src/ai_researcher.py`

기존 `_call_ai()`는 비공개 메서드라 외부에서 사용하기 적절치 않다. 얇은 공개 래퍼를 추가한다.

- [ ] **Step 7.1: 기존 ai_researcher.py에서 `_call_ai` 시그니처 확인**

```bash
grep -n "def _call_ai" src/ai_researcher.py
```
Expected: `def _call_ai(self, prompt, max_retries=5, temperature=0.4, max_output_tokens=4000, system_instruction=None)`

- [ ] **Step 7.2: 공개 메서드 추가**

`src/ai_researcher.py`의 `class AIResearcher` 안, `generate_briefing` 메서드 정의 직전에 다음을 추가:

```python
    def call(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
        max_output_tokens: int = 6000,
        max_retries: int = 5,
    ) -> Tuple[str, Dict]:
        """
        외부 모듈이 직접 호출하는 공개 진입점.
        기존 다중 키 폴백/재시도 로직(`_call_ai`)을 그대로 사용한다.

        Args:
            prompt: 사용자 프롬프트
            system_instruction: 시스템 인스트럭션 (할루시네이션 가드 등)
            temperature: 응답 다양성 (트렌드 스캐너는 0.2 권장 — 객관성)
            max_output_tokens: 최대 출력 토큰
            max_retries: 키 폴백 포함 최대 재시도

        Returns:
            (response_text, usage_info)
        """
        return self._call_ai(
            prompt=prompt,
            max_retries=max_retries,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            system_instruction=system_instruction,
        )
```

- [ ] **Step 7.3: 메서드 호출 가능 여부 smoke test**

```bash
python -c "from src.ai_researcher import create_researcher; r = create_researcher(); print(type(r.call).__name__)"
```
Expected: `method` (예외 없이 출력)

> 실제 API 호출은 다음 task의 추출기 통합 단계에서 mock으로 검증한다.

- [ ] **Step 7.4: 커밋**

```bash
git add src/ai_researcher.py
git commit -m "feat: AIResearcher.call 공개 메서드 추가 (트렌드 스캐너용)"
```

---

## Task 8: AI 프롬프트 3종 작성

**Files:**
- Create: `config/prompts/trend_extract.txt`
- Create: `config/prompts/trend_top3.txt`
- Create: `config/prompts/trend_outlook.txt`

- [ ] **Step 8.1: 공통 시스템 제약 작성용 헬퍼 결정**

각 프롬프트 파일은 **시스템 제약(공통)** + **태스크별 지시 + 출력 스키마**로 구성. 공통 제약은 각 파일에 직접 인라인(중복)한다 — 파일 1개 단위로 self-contained 유지.

- [ ] **Step 8.2: trend_extract.txt 작성**

`config/prompts/trend_extract.txt`:
```
[시스템 제약 - 절대 위반 금지]

당신은 한국어로 응답하는 객관적 분석자입니다. 다음 제약을 절대 위반하지 마세요:

1. 입력으로 제공된 [출처#N] 텍스트에 명시되지 않은 사실·숫자·예측은
   어떤 형태로도 출력하지 마세요.
2. 다음 추측 표현 사용 금지:
   "예상된다", "전망된다", "~할 것이다", "아마도", "~로 보인다",
   "기대된다", "유력하다", "가능성이 크다"
3. 모든 항목에 refs(인덱스 배열)를 채워야 합니다. 빈 refs는 무효.
4. 입력 텍스트에 명시되지 않은 종목·섹터 이름을 새로 만들어내지 마세요.
5. 동일 종목의 별칭(예: "엔비디아"/"NVDA"/"Nvidia")은 하나로 통합하되,
   대표 표기로는 입력 텍스트에 가장 자주 등장한 표기를 사용합니다.

[작업]

아래 4배치(미국 뉴스 / 미국 커뮤니티 / 한국 뉴스 / 한국 커뮤니티)
각 30건의 글에서, 배치별로 가장 자주 언급된 종목 10개와 섹터 10개를
빈도순으로 추출하세요.

[출력 형식 — 반드시 유효 JSON만 출력]

{
  "us_news":      {"stocks": [{"name": "...", "freq": 0, "refs": []}, ...×10],
                   "sectors": [{"name": "...", "freq": 0, "refs": []}, ...×10]},
  "us_community": {"stocks": [...×10], "sectors": [...×10]},
  "kr_news":      {"stocks": [...×10], "sectors": [...×10]},
  "kr_community": {"stocks": [...×10], "sectors": [...×10]}
}

각 항목:
- name: 종목명 또는 섹터명 (입력 텍스트의 표기 사용)
- freq: 해당 배치 30개 중 언급된 글 수
- refs: 언급된 글의 인덱스 배열 (예: [3, 7, 12])

JSON 외 다른 텍스트(설명, 마크다운, 코드블록 표시) 금지.

[입력 데이터]

{COLLECTED_TEXT}
```

- [ ] **Step 8.3: trend_top3.txt 작성**

`config/prompts/trend_top3.txt`:
```
[시스템 제약 - 절대 위반 금지]

당신은 한국어로 응답하는 객관적 분석자입니다. 다음 제약을 절대 위반하지 마세요:

1. 입력으로 제공된 추출 결과에 등장하지 않은 종목·섹터를 새로 만들지 마세요.
2. 추측 표현 사용 금지:
   "예상된다", "전망된다", "~할 것이다", "아마도", "~로 보인다"
3. 각 항목 reason은 빈도수와 [출처#N] 인덱스 인용으로만 구성합니다.
4. 영역(미국/한국)을 혼동하지 마세요. 미국 TOP3는 미뉴스 + 미커뮤만,
   한국 TOP3는 한뉴스 + 한커뮤만 가중 합산합니다.

[작업]

아래 4배치 추출 결과를 받아, 영역별 TOP3를 선정하세요:
- 미국 TOP3 섹터: 미뉴스+미커뮤 빈도 합산 상위 3개
- 미국 TOP3 종목: 동일 기준
- 한국 TOP3 섹터: 한뉴스+한커뮤 빈도 합산 상위 3개
- 한국 TOP3 종목: 동일 기준

[출력 형식 — 반드시 유효 JSON만 출력]

{
  "us_top3_sectors": [
    {"name": "...", "reason": "미뉴스 30개 중 N건, 미커뮤 30개 중 M건 [미뉴스#a,#b,...] [미커뮤#c,#d,...]",
     "us_news_refs": [a, b, ...], "us_community_refs": [c, d, ...]},
    ...×3
  ],
  "us_top3_stocks":  [...×3],
  "kr_top3_sectors": [
    {"name": "...", "reason": "한뉴스 30개 중 N건, 한커뮤 30개 중 M건 [한뉴스#a,...] [한커뮤#b,...]",
     "kr_news_refs": [...], "kr_community_refs": [...]},
    ...×3
  ],
  "kr_top3_stocks":  [...×3]
}

JSON 외 텍스트 금지.

[입력 데이터 — 4배치 추출 결과]

{EXTRACTION_RESULT}
```

- [ ] **Step 8.4: trend_outlook.txt 작성**

`config/prompts/trend_outlook.txt`:
```
[시스템 제약 - 절대 위반 금지]

당신은 한국어로 응답하는 객관적 분석자입니다. 다음 제약을 절대 위반하지 마세요:

1. 아래 [출처#N] 텍스트에 명시되지 않은 사실·숫자·예측은 출력 금지.
2. 추측·전망 표현 사용 금지:
   "예상된다", "전망된다", "~할 것이다", "아마도", "~로 보인다",
   "기대된다", "유력하다", "가능성이 크다", "상승할", "하락할",
   "오를", "내릴"
3. 가격 예측·목표가·등락 방향 단정 금지.
4. 사용 가능한 표현: "~라고 보도됨", "~로 언급됨", "~가 다뤄짐",
   "~건의 글에서 거론됨", "반대 시각으로 ~가 언급됨"
5. 모든 outlook 문장은 [출처#N] 형식 인덱스를 1개 이상 인용해야 합니다.
6. 각 항목당 3~4줄 길이.
7. 호재·관찰 사항을 먼저 인용한 뒤, 반대 시각·리스크가 텍스트에 있다면
   인용하여 균형을 맞추세요. 반대 시각이 텍스트에 없다면 마지막 줄에
   "반대 시각은 수집된 텍스트에 부재"라고 명시합니다.

[작업]

영역별 TOP3 종목·섹터(총 12개 항목)에 대해 outlook(전망 코멘트)을
3~4줄로 작성하세요. 작성 근거는 오직 아래 [출처#N] 텍스트에 한정합니다.

[출력 형식 — 반드시 유효 JSON만 출력]

{
  "us_sector_outlook": [
    {"name": "...", "outlook": "3~4줄 한국어 코멘트, [미뉴스#a] [미커뮤#b] 인용 포함",
     "refs": ["미뉴스#a", "미커뮤#b", ...]},
    ...×3
  ],
  "us_stock_outlook":  [...×3],
  "kr_sector_outlook": [...×3],
  "kr_stock_outlook":  [...×3]
}

JSON 외 텍스트 금지.

[입력 데이터 — TOP3 결과]

{TOP3_RESULT}

[입력 데이터 — 인용 가능한 글 (TOP3 reason의 refs에 등장한 글만)]

{REFERENCED_TEXTS}
```

- [ ] **Step 8.5: 파일 존재 확인**

```bash
ls -la config/prompts/trend_*.txt
```
Expected: 3 files

- [ ] **Step 8.6: 커밋**

```bash
git add config/prompts/trend_extract.txt config/prompts/trend_top3.txt config/prompts/trend_outlook.txt
git commit -m "feat: 트렌드 스캐너 프롬프트 3종 (추출/TOP3/전망, 할루시네이션 가드)"
```

---

## Task 9: trend_extractor — extract_per_batch + select_top3 + generate_outlook + verify_indices

**Files:**
- Create: `src/trend_extractor.py`
- Create: `tests/test_trend_extractor.py`

이 task는 4개의 함수를 포함하므로 sub-step이 길다. 각 함수마다 TDD 사이클을 한 번씩 돈다.

- [ ] **Step 9.1: verify_indices 실패 테스트**

`tests/test_trend_extractor.py` (이 task 동안 점진적으로 추가):
```python
"""trend_extractor 테스트"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.trend_collectors.base import CollectedItem
from src.trend_extractor import verify_indices


KST = timezone.utc  # 테스트에서는 timezone 무관


def _make_batches():
    return {
        "us_news": [
            CollectedItem("us_news", i, f"T{i}", f"B{i}", f"u{i}", datetime(2026, 4, 27, tzinfo=KST))
            for i in range(1, 6)  # idx 1..5
        ],
        "us_community": [
            CollectedItem("us_community", i, f"CT{i}", f"CB{i}", f"cu{i}", datetime(2026, 4, 27, tzinfo=KST))
            for i in range(1, 4)  # idx 1..3
        ],
        "kr_news": [],
        "kr_community": [],
    }


def test_verify_indices_all_valid():
    text = "Nvidia가 강세 [미뉴스#3] [미커뮤#2]"
    result = verify_indices(text, _make_batches())
    assert result["ok"] is True
    assert result["missing"] == []
    assert result["total_refs"] == 2


def test_verify_indices_detects_missing():
    text = "잘못된 인덱스 [미뉴스#99] [미커뮤#1]"
    result = verify_indices(text, _make_batches())
    assert result["ok"] is False
    assert ("us_news", 99) in result["missing"]
    assert ("us_community", 1) not in result["missing"]


def test_verify_indices_no_refs():
    text = "인덱스 없음"
    result = verify_indices(text, _make_batches())
    assert result["ok"] is True
    assert result["total_refs"] == 0


def test_verify_indices_handles_korean_labels_only():
    """한국 배치도 동일하게 처리"""
    batches = _make_batches()
    batches["kr_news"] = [
        CollectedItem("kr_news", i, f"T{i}", f"B{i}", f"u{i}", datetime(2026, 4, 27, tzinfo=KST))
        for i in range(1, 4)
    ]
    text = "[한뉴스#2]"
    result = verify_indices(text, batches)
    assert result["ok"] is True
```

- [ ] **Step 9.2: 실패 확인**

```bash
pytest tests/test_trend_extractor.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'src.trend_extractor'`

- [ ] **Step 9.3: trend_extractor.py 골격 + verify_indices 구현**

`src/trend_extractor.py`:
```python
"""트렌드 스캐너 AI 추출 + 검증 모듈"""
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Tuple

from src.trend_collectors.base import CollectedItem, format_indexed_text

logger = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).parent.parent / "config" / "prompts"

LABEL_TO_BATCH = {
    "미뉴스": "us_news",
    "미커뮤": "us_community",
    "한뉴스": "kr_news",
    "한커뮤": "kr_community",
}

INDEX_PATTERN = re.compile(r"\[(미뉴스|미커뮤|한뉴스|한커뮤)#(\d+)\]")


def verify_indices(text: str, batches: Dict[str, List[CollectedItem]]) -> Dict:
    """
    출력 text에 등장한 [라벨#N] 인덱스를 실제 수집 데이터와 매핑 검증.

    Returns:
        {"ok": bool, "missing": [(batch, idx), ...], "total_refs": int}
    """
    found = INDEX_PATTERN.findall(text)
    cited = {(LABEL_TO_BATCH[lbl], int(n)) for lbl, n in found}

    actual = {(b, item.idx) for b, items in batches.items() for item in items}
    missing = sorted(cited - actual)

    return {"ok": len(missing) == 0, "missing": missing, "total_refs": len(found)}
```

- [ ] **Step 9.4: verify_indices 테스트 통과**

```bash
pytest tests/test_trend_extractor.py -v
```
Expected: 4 passed

- [ ] **Step 9.5: extract_per_batch 실패 테스트 추가**

`tests/test_trend_extractor.py`에 추가:
```python
from src.trend_extractor import extract_per_batch


def test_extract_per_batch_passes_indexed_text_to_ai():
    batches = _make_batches()
    fake_response = json.dumps({
        "us_news":      {"stocks": [], "sectors": []},
        "us_community": {"stocks": [], "sectors": []},
        "kr_news":      {"stocks": [], "sectors": []},
        "kr_community": {"stocks": [], "sectors": []},
    })
    fake_researcher = MagicMock()
    fake_researcher.call.return_value = (fake_response, {"total_tokens": 100})

    result = extract_per_batch(batches, researcher=fake_researcher)

    # researcher.call이 호출되었고, 프롬프트에 [미뉴스#1], [미커뮤#1] 인덱스 포함
    fake_researcher.call.assert_called_once()
    prompt_arg = fake_researcher.call.call_args.kwargs.get("prompt") or fake_researcher.call.call_args.args[0]
    assert "[미뉴스#1]" in prompt_arg
    assert "[미커뮤#1]" in prompt_arg

    assert "us_news" in result
    assert "stocks" in result["us_news"]


def test_extract_per_batch_parses_json_with_codeblock_wrapper():
    """LLM이 ```json ... ``` 으로 감쌀 경우도 파싱"""
    batches = _make_batches()
    wrapped = "```json\n" + json.dumps({
        "us_news":      {"stocks": [{"name": "Nvidia", "freq": 5, "refs": [1,2,3,4,5]}], "sectors": []},
        "us_community": {"stocks": [], "sectors": []},
        "kr_news":      {"stocks": [], "sectors": []},
        "kr_community": {"stocks": [], "sectors": []},
    }) + "\n```"
    fake_researcher = MagicMock()
    fake_researcher.call.return_value = (wrapped, {"total_tokens": 100})

    result = extract_per_batch(batches, researcher=fake_researcher)

    assert result["us_news"]["stocks"][0]["name"] == "Nvidia"


def test_extract_per_batch_retries_on_invalid_json():
    """첫 응답이 JSON 파싱 실패면 1회 재시도"""
    batches = _make_batches()
    valid = json.dumps({
        "us_news":      {"stocks": [], "sectors": []},
        "us_community": {"stocks": [], "sectors": []},
        "kr_news":      {"stocks": [], "sectors": []},
        "kr_community": {"stocks": [], "sectors": []},
    })
    fake_researcher = MagicMock()
    fake_researcher.call.side_effect = [
        ("not a json", {"total_tokens": 50}),
        (valid, {"total_tokens": 100}),
    ]

    result = extract_per_batch(batches, researcher=fake_researcher)

    assert fake_researcher.call.call_count == 2
    assert "us_news" in result
```

- [ ] **Step 9.6: 실패 확인**

```bash
pytest tests/test_trend_extractor.py -v
```
Expected: 3 new tests FAIL — `ImportError: cannot import name 'extract_per_batch'`

- [ ] **Step 9.7: extract_per_batch 구현**

`src/trend_extractor.py`에 추가:
```python
def _load_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def _strip_codeblock(text: str) -> str:
    """LLM이 ```json ... ``` 으로 감싼 경우 안쪽 JSON만 반환"""
    s = text.strip()
    if s.startswith("```"):
        # 첫 줄(```json 등) 제거
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


def _parse_json_with_retry(
    researcher,
    prompt: str,
    max_retries: int = 2,
    temperature: float = 0.2,
) -> Tuple[Dict, Dict]:
    """LLM 응답을 JSON 파싱. 실패 시 재시도."""
    last_err = None
    last_usage = {}
    for attempt in range(max_retries):
        try:
            text, usage = researcher.call(
                prompt=prompt,
                temperature=temperature,
                max_output_tokens=8000,
            )
            last_usage = usage
            cleaned = _strip_codeblock(text)
            return json.loads(cleaned), usage
        except (json.JSONDecodeError, ValueError) as e:
            last_err = e
            logger.warning(f"AI JSON 파싱 실패 (시도 {attempt + 1}): {e}")
    raise RuntimeError(f"AI JSON 파싱 {max_retries}회 실패: {last_err}")


def extract_per_batch(
    batches: Dict[str, List[CollectedItem]],
    researcher,
) -> Dict:
    """
    AI 콜 #1 — 4배치 일괄 추출.
    각 배치에서 종목 10 + 섹터 10을 빈도순으로 추출.
    """
    template = _load_prompt("trend_extract.txt")

    # 모든 배치를 인덱스 부착해 직렬화
    all_items: List[CollectedItem] = []
    for b in ("us_news", "us_community", "kr_news", "kr_community"):
        all_items.extend(batches.get(b, []))
    collected_text = format_indexed_text(all_items)

    prompt = template.replace("{COLLECTED_TEXT}", collected_text)

    result, _usage = _parse_json_with_retry(researcher, prompt)
    return result
```

- [ ] **Step 9.8: extract_per_batch 테스트 통과**

```bash
pytest tests/test_trend_extractor.py -v
```
Expected: 7 passed

- [ ] **Step 9.9: select_top3 테스트 추가**

```python
from src.trend_extractor import select_top3


def test_select_top3_passes_extraction_to_ai():
    extraction = {"us_news": {"stocks": [], "sectors": []}, "us_community": {"stocks": [], "sectors": []},
                  "kr_news": {"stocks": [], "sectors": []}, "kr_community": {"stocks": [], "sectors": []}}
    fake_response = json.dumps({
        "us_top3_sectors": [], "us_top3_stocks": [],
        "kr_top3_sectors": [], "kr_top3_stocks": [],
    })
    fake_researcher = MagicMock()
    fake_researcher.call.return_value = (fake_response, {"total_tokens": 100})

    result = select_top3(extraction, researcher=fake_researcher)

    assert "us_top3_sectors" in result
    assert "kr_top3_stocks" in result
    fake_researcher.call.assert_called_once()
    prompt = fake_researcher.call.call_args.kwargs.get("prompt") or fake_researcher.call.call_args.args[0]
    assert "us_news" in prompt  # extraction JSON이 프롬프트에 들어감
```

- [ ] **Step 9.10: 실패 확인**

```bash
pytest tests/test_trend_extractor.py -v
```
Expected: 1 new FAIL

- [ ] **Step 9.11: select_top3 구현**

`src/trend_extractor.py`에 추가:
```python
def select_top3(extraction: Dict, researcher) -> Dict:
    """
    AI 콜 #2 — 영역별 TOP3 섹터·종목 + 선정 이유.
    """
    template = _load_prompt("trend_top3.txt")
    prompt = template.replace("{EXTRACTION_RESULT}", json.dumps(extraction, ensure_ascii=False, indent=2))
    result, _usage = _parse_json_with_retry(researcher, prompt)
    return result
```

- [ ] **Step 9.12: 통과 확인**

```bash
pytest tests/test_trend_extractor.py -v
```
Expected: 8 passed

- [ ] **Step 9.13: generate_outlook 테스트 추가**

```python
from src.trend_extractor import generate_outlook


def test_generate_outlook_includes_only_referenced_texts():
    """TOP3 reason에 인용된 인덱스에 해당하는 글만 프롬프트에 포함"""
    batches = _make_batches()
    top3 = {
        "us_top3_sectors": [
            {"name": "AI", "reason": "...", "us_news_refs": [3], "us_community_refs": [2]},
        ],
        "us_top3_stocks": [],
        "kr_top3_sectors": [],
        "kr_top3_stocks": [],
    }
    fake_response = json.dumps({
        "us_sector_outlook": [], "us_stock_outlook": [],
        "kr_sector_outlook": [], "kr_stock_outlook": [],
    })
    fake_researcher = MagicMock()
    fake_researcher.call.return_value = (fake_response, {"total_tokens": 100})

    result = generate_outlook(top3, batches, researcher=fake_researcher)

    prompt = fake_researcher.call.call_args.kwargs.get("prompt") or fake_researcher.call.call_args.args[0]
    # 인용된 us_news#3, us_community#2 글이 프롬프트에 포함
    assert "[미뉴스#3]" in prompt
    assert "[미커뮤#2]" in prompt
    # 인용되지 않은 글은 미포함 (idx 1, 4, 5는 us_news에서 인용 안 됨)
    assert "[미뉴스#1]" not in prompt
    assert "us_sector_outlook" in result
```

- [ ] **Step 9.14: 실패 확인**

```bash
pytest tests/test_trend_extractor.py -v
```
Expected: 1 new FAIL

- [ ] **Step 9.15: generate_outlook 구현**

`src/trend_extractor.py`에 추가:
```python
def _collect_referenced_indices(top3: Dict) -> Dict[str, set]:
    """TOP3 결과의 모든 *_refs 필드에서 인용된 인덱스를 batch별로 모음"""
    refs: Dict[str, set] = {b: set() for b in ("us_news", "us_community", "kr_news", "kr_community")}
    field_to_batch = [
        ("us_news_refs", "us_news"),
        ("us_community_refs", "us_community"),
        ("kr_news_refs", "kr_news"),
        ("kr_community_refs", "kr_community"),
    ]
    for key in ("us_top3_sectors", "us_top3_stocks", "kr_top3_sectors", "kr_top3_stocks"):
        for entry in top3.get(key, []):
            for field, batch in field_to_batch:
                for idx in entry.get(field, []) or []:
                    refs[batch].add(int(idx))
    return refs


def generate_outlook(
    top3: Dict,
    batches: Dict[str, List[CollectedItem]],
    researcher,
) -> Dict:
    """
    AI 콜 #3 — 12개 항목 전망. TOP3 reason에 인용된 글만 프롬프트에 포함.
    """
    template = _load_prompt("trend_outlook.txt")

    # 인용된 글만 필터
    referenced = _collect_referenced_indices(top3)
    referenced_items: List[CollectedItem] = []
    for batch, idx_set in referenced.items():
        for it in batches.get(batch, []):
            if it.idx in idx_set:
                referenced_items.append(it)

    referenced_text = format_indexed_text(referenced_items)

    prompt = (
        template
        .replace("{TOP3_RESULT}", json.dumps(top3, ensure_ascii=False, indent=2))
        .replace("{REFERENCED_TEXTS}", referenced_text)
    )

    result, _usage = _parse_json_with_retry(researcher, prompt)
    return result
```

- [ ] **Step 9.16: 전체 trend_extractor 테스트 통과**

```bash
pytest tests/test_trend_extractor.py -v
```
Expected: 9 passed

- [ ] **Step 9.17: 커밋**

```bash
git add src/trend_extractor.py tests/test_trend_extractor.py
git commit -m "feat: trend_extractor — 추출/TOP3/전망/검증 (3 AI 콜 + 인덱스 매핑 검증)"
```

---

## Task 10: trend_formatter — 텔레그램 2메시지 포맷

**Files:**
- Create: `src/trend_formatter.py`
- Create: `tests/test_trend_formatter.py`

- [ ] **Step 10.1: 실패 테스트 작성**

`tests/test_trend_formatter.py`:
```python
"""trend_formatter 테스트"""
from datetime import datetime, timezone, timedelta

from src.trend_formatter import format_us, format_kr


KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 4, 27, 7, 30, tzinfo=KST)


def _sample_top3():
    return {
        "us_top3_sectors": [
            {"name": "AI 인프라", "reason": "미뉴스 30개 중 8건, 미커뮤 30개 중 5건 [미뉴스#3,#7,#12,#15,#18,#22,#25,#29] [미커뮤#2,#9,#14,#21,#27]"},
            {"name": "반도체", "reason": "미뉴스 30개 중 6건 [미뉴스#1,#4,#8,#11,#16,#20]"},
            {"name": "클라우드", "reason": "미뉴스 30개 중 5건 [미뉴스#5,#9,#13,#17,#23]"},
        ],
        "us_top3_stocks": [
            {"name": "Nvidia", "reason": "미뉴스 30개 중 7건 [미뉴스#3,#7,#12,#15,#18,#22,#25]"},
            {"name": "Microsoft", "reason": "미커뮤 30개 중 4건 [미커뮤#2,#9,#14,#21]"},
            {"name": "Apple", "reason": "미뉴스 30개 중 3건 [미뉴스#4,#11,#19]"},
        ],
        "kr_top3_sectors": [
            {"name": "반도체", "reason": "한뉴스 30개 중 9건 [한뉴스#1,#3,#5,#7,#10,#12,#15,#18,#22]"},
            {"name": "2차전지", "reason": "한뉴스 30개 중 5건 [한뉴스#2,#8,#13,#17,#24]"},
            {"name": "AI", "reason": "한커뮤 30개 중 4건 [한커뮤#4,#9,#16,#23]"},
        ],
        "kr_top3_stocks": [
            {"name": "삼성전자", "reason": "한뉴스 30개 중 8건 [한뉴스#1,#3,#5,#7,#10,#12,#15,#18]"},
            {"name": "SK하이닉스", "reason": "한뉴스 30개 중 5건 [한뉴스#2,#8,#13,#17,#22]"},
            {"name": "LG에너지솔루션", "reason": "한뉴스 30개 중 3건 [한뉴스#4,#11,#19]"},
        ],
    }


def _sample_outlook():
    return {
        "us_sector_outlook": [
            {"name": "AI 인프라", "outlook": "AI 인프라 수요 가속이 [미뉴스#3] [미커뮤#2]에서 다뤄짐. 다만 밸류에이션 부담 우려가 [미뉴스#7]에서 언급됨. 데이터센터 전력 비용 이슈가 [미커뮤#9]에 등장."},
            {"name": "반도체", "outlook": "AI 칩 수요가 [미뉴스#1] [미뉴스#4]에서 거론됨. 사이클 우려가 [미뉴스#8]에 언급. 반대 시각은 수집된 텍스트에 부재"},
            {"name": "클라우드", "outlook": "AWS·Azure 매출 성장이 [미뉴스#5]에서 보도됨. 다만 비용 효율 압박이 [미뉴스#9]에 언급됨. 반대 시각은 수집된 텍스트에 부재"},
        ],
        "us_stock_outlook": [
            {"name": "Nvidia", "outlook": "AI GPU 수요가 [미뉴스#3]에서 다뤄짐. 경쟁사 대안이 [미뉴스#22]에 언급됨. 반대 시각은 수집된 텍스트에 부재"},
            {"name": "Microsoft", "outlook": "Copilot 매출이 [미커뮤#2]에서 거론됨. 비용 부담이 [미커뮤#9]에 언급. 반대 시각은 수집된 텍스트에 부재"},
            {"name": "Apple", "outlook": "iPhone 판매가 [미뉴스#4]에서 다뤄짐. 중국 시장 우려가 [미뉴스#11]에 언급됨. 반대 시각은 수집된 텍스트에 부재"},
        ],
        "kr_sector_outlook": [
            {"name": "반도체", "outlook": "HBM 수요가 [한뉴스#1] [한뉴스#3]에서 다뤄짐. 가격 협상 이슈가 [한뉴스#7]에 언급됨. 반대 시각은 수집된 텍스트에 부재"},
            {"name": "2차전지", "outlook": "전기차 수요 둔화가 [한뉴스#2] [한뉴스#8]에서 거론됨. 다만 ESS 수요는 [한뉴스#13]에 언급. 반대 시각이 [한뉴스#17]에 등장"},
            {"name": "AI", "outlook": "K-AI 정책이 [한커뮤#4]에서 다뤄짐. 수익성 우려가 [한커뮤#9]에 언급됨. 반대 시각은 수집된 텍스트에 부재"},
        ],
        "kr_stock_outlook": [
            {"name": "삼성전자", "outlook": "HBM 양산이 [한뉴스#1]에서 거론됨. 메모리 가격 하락 우려가 [한뉴스#7]에 언급됨. 반대 시각은 수집된 텍스트에 부재"},
            {"name": "SK하이닉스", "outlook": "Nvidia 공급이 [한뉴스#2]에서 보도됨. 수율 이슈가 [한뉴스#8]에 언급됨. 반대 시각은 수집된 텍스트에 부재"},
            {"name": "LG에너지솔루션", "outlook": "북미 수주가 [한뉴스#4]에서 다뤄짐. 마진 압박이 [한뉴스#11]에 언급됨. 반대 시각은 수집된 텍스트에 부재"},
        ],
    }


def test_format_us_contains_top3_sectors_and_stocks():
    msg = format_us(NOW, _sample_top3(), _sample_outlook(), counts={"us_news": 30, "us_community": 30}, verify_result={"ok": True, "missing": [], "total_refs": 50})
    assert "🇺🇸" in msg
    assert "AI 인프라" in msg
    assert "Nvidia" in msg
    assert "30개 중 8건" in msg


def test_format_us_includes_indices():
    msg = format_us(NOW, _sample_top3(), _sample_outlook(), counts={"us_news": 30, "us_community": 30}, verify_result={"ok": True, "missing": [], "total_refs": 50})
    assert "[미뉴스#3" in msg


def test_format_us_warns_on_verify_fail():
    msg = format_us(NOW, _sample_top3(), _sample_outlook(), counts={"us_news": 30, "us_community": 30}, verify_result={"ok": False, "missing": [("us_news", 99)], "total_refs": 50})
    assert "⚠️" in msg
    assert "검증 실패" in msg


def test_format_us_warns_on_partial_collection():
    """30개 미달 시 표기"""
    msg = format_us(NOW, _sample_top3(), _sample_outlook(), counts={"us_news": 22, "us_community": 30}, verify_result={"ok": True, "missing": [], "total_refs": 50})
    assert "22" in msg


def test_format_kr_contains_top3():
    msg = format_kr(NOW, _sample_top3(), _sample_outlook(), counts={"kr_news": 30, "kr_community": 30}, verify_result={"ok": True, "missing": [], "total_refs": 50})
    assert "🇰🇷" in msg
    assert "삼성전자" in msg
    assert "반도체" in msg


def test_format_messages_under_4096_chars_for_typical_input():
    msg_us = format_us(NOW, _sample_top3(), _sample_outlook(), counts={"us_news": 30, "us_community": 30}, verify_result={"ok": True, "missing": [], "total_refs": 50})
    msg_kr = format_kr(NOW, _sample_top3(), _sample_outlook(), counts={"kr_news": 30, "kr_community": 30}, verify_result={"ok": True, "missing": [], "total_refs": 50})
    assert len(msg_us) < 4096
    assert len(msg_kr) < 4096
```

- [ ] **Step 10.2: 실패 확인**

```bash
pytest tests/test_trend_formatter.py -v
```
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 10.3: 구현**

`src/trend_formatter.py`:
```python
"""트렌드 스캐너 텔레그램 메시지 포매터"""
from datetime import datetime
from typing import Dict


SEP = "━━━━━━━━━━━━━━━━━━━━━━━━━"
DISCLAIMER = "※ 본 리포트는 수집된 텍스트만을 근거로 합니다. 투자 권유가 아닙니다."


def _verify_warning(verify_result: Dict) -> str:
    if verify_result.get("ok", True):
        return ""
    n = len(verify_result.get("missing", []))
    return f"⚠️ 인덱스 검증 실패 {n}건\n"


def _format_section(title_emoji: str, title: str, top3_list, outlook_list) -> str:
    """공통 — TOP3 항목 3개 + 각 항목의 outlook을 결합"""
    lines = [f"{title_emoji} {title}"]
    outlook_by_name = {o["name"]: o["outlook"] for o in outlook_list}
    for i, entry in enumerate(top3_list, start=1):
        name = entry["name"]
        reason = entry["reason"]
        outlook = outlook_by_name.get(name, "(전망 누락)")
        lines.append(f"{i}. {name} — {reason}")
        lines.append(f"   {outlook}")
    return "\n".join(lines)


def format_us(
    now: datetime,
    top3: Dict,
    outlook: Dict,
    counts: Dict[str, int],
    verify_result: Dict,
) -> str:
    """미국 메시지 (~2000자)"""
    timestamp = now.strftime("%Y-%m-%d %H:%M KST")
    header = (
        f"🇺🇸 [미국] 트렌드 스캔 — {timestamp}\n"
        f"수집: 미국 뉴스 {counts.get('us_news', 0)} + 미국 커뮤니티 {counts.get('us_community', 0)} (최근 24h)\n"
    )
    warning = _verify_warning(verify_result)

    sectors = _format_section("📊", "TOP3 섹터", top3.get("us_top3_sectors", []), outlook.get("us_sector_outlook", []))
    stocks = _format_section("🏢", "TOP3 종목", top3.get("us_top3_stocks", []), outlook.get("us_stock_outlook", []))

    body = "\n".join([header + warning, SEP, sectors, "", SEP, stocks, "", SEP, DISCLAIMER])
    return body


def format_kr(
    now: datetime,
    top3: Dict,
    outlook: Dict,
    counts: Dict[str, int],
    verify_result: Dict,
) -> str:
    """한국 메시지 (~2000자)"""
    timestamp = now.strftime("%Y-%m-%d %H:%M KST")
    header = (
        f"🇰🇷 [한국] 트렌드 스캔 — {timestamp}\n"
        f"수집: 한국 뉴스 {counts.get('kr_news', 0)} + 한국 커뮤니티 {counts.get('kr_community', 0)} (최근 24h)\n"
    )
    warning = _verify_warning(verify_result)

    sectors = _format_section("📊", "TOP3 섹터", top3.get("kr_top3_sectors", []), outlook.get("kr_sector_outlook", []))
    stocks = _format_section("🏢", "TOP3 종목", top3.get("kr_top3_stocks", []), outlook.get("kr_stock_outlook", []))

    body = "\n".join([header + warning, SEP, sectors, "", SEP, stocks, "", SEP, DISCLAIMER])
    return body
```

- [ ] **Step 10.4: 통과 확인**

```bash
pytest tests/test_trend_formatter.py -v
```
Expected: 6 passed

- [ ] **Step 10.5: 커밋**

```bash
git add src/trend_formatter.py tests/test_trend_formatter.py
git commit -m "feat: trend_formatter — 텔레그램 미국·한국 2메시지 포맷"
```

---

## Task 11: trend_scanner — 메인 entrypoint 통합

**Files:**
- Create: `src/trend_scanner.py`

이 task는 통합이라 기존 단위 테스트를 활용하고 main 자체는 manual smoke test로 검증한다.

- [ ] **Step 11.1: 구현**

`src/trend_scanner.py`:
```python
"""
트렌드 스캐너 — 매일 KST 07:30·20:00 실행

미국·한국 뉴스/커뮤니티 글을 각 30개씩 수집해 빈도순 종목·섹터 추출 →
TOP3 비판적 전망을 텔레그램 2메시지로 발송한다.

Usage:
    python -m src.trend_scanner          # 정상 실행
    python -m src.trend_scanner --test   # 텔레그램 발송 대신 콘솔 출력
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 프로젝트 루트 추가
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.trend_collectors import us_news, us_community, kr_news, kr_community
from src.trend_extractor import extract_per_batch, select_top3, generate_outlook, verify_indices
from src.trend_formatter import format_us, format_kr
from src.ai_researcher import create_researcher
from src.notifier import create_notifier

KST = timezone(timedelta(hours=9))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def _collect_all(now_utc: datetime, now_kst: datetime) -> dict:
    """4배치 병렬 수집 — 일부 실패는 빈 배치로 처리"""
    batches = {}

    logger.info("[수집 1/4] 미국 뉴스...")
    try:
        batches["us_news"] = us_news.collect(now=now_utc, limit=30)
    except Exception as e:
        logger.warning(f"us_news 수집 실패: {e}")
        batches["us_news"] = []

    logger.info("[수집 2/4] 미국 커뮤니티...")
    try:
        batches["us_community"] = us_community.collect(now=now_utc, limit=30)
    except Exception as e:
        logger.warning(f"us_community 수집 실패: {e}")
        batches["us_community"] = []

    logger.info("[수집 3/4] 한국 뉴스...")
    try:
        batches["kr_news"] = kr_news.collect(now=now_utc, limit=30)
    except Exception as e:
        logger.warning(f"kr_news 수집 실패: {e}")
        batches["kr_news"] = []

    logger.info("[수집 4/4] 한국 커뮤니티...")
    try:
        batches["kr_community"] = kr_community.collect(now=now_kst, limit=30)
    except Exception as e:
        logger.warning(f"kr_community 수집 실패: {e}")
        batches["kr_community"] = []

    return batches


def _counts(batches: dict) -> dict:
    return {b: len(items) for b, items in batches.items()}


def main(test_mode: bool = False) -> int:
    logger.info("=" * 50)
    logger.info("트렌드 스캐너 시작")
    if test_mode:
        logger.info("🧪 TEST MODE — 텔레그램 발송 대신 콘솔 출력")

    now_utc = datetime.now(timezone.utc)
    now_kst = now_utc.astimezone(KST)
    logger.info(f"기준 시각: {now_kst.strftime('%Y-%m-%d %H:%M KST')}")

    # 1. 수집
    batches = _collect_all(now_utc, now_kst)
    counts = _counts(batches)
    logger.info(f"수집 결과: {counts}")

    if all(c == 0 for c in counts.values()):
        logger.error("모든 배치 수집 실패 — abort")
        return 1

    # 2. AI 콜 #1 — 추출
    researcher = create_researcher()
    logger.info("[AI 1/3] 4배치 추출...")
    extraction = extract_per_batch(batches, researcher=researcher)

    # 3. AI 콜 #2 — TOP3
    logger.info("[AI 2/3] TOP3 종합...")
    top3 = select_top3(extraction, researcher=researcher)

    # 4. AI 콜 #3 — 전망
    logger.info("[AI 3/3] 전망 생성...")
    outlook = generate_outlook(top3, batches, researcher=researcher)

    # 5. 검증
    full_text = str(top3) + str(outlook)
    verify_result = verify_indices(full_text, batches)
    if verify_result["ok"]:
        logger.info(f"✅ 인덱스 검증 통과 ({verify_result['total_refs']}개 인용)")
    else:
        logger.warning(f"⚠️ 인덱스 검증 실패 {len(verify_result['missing'])}건: {verify_result['missing'][:10]}")

    # 6. 포맷
    msg_us = format_us(now_kst, top3, outlook, counts, verify_result)
    msg_kr = format_kr(now_kst, top3, outlook, counts, verify_result)

    # 7. 발송
    if test_mode:
        print("\n=== 미국 메시지 ===\n" + msg_us)
        print("\n=== 한국 메시지 ===\n" + msg_kr)
        print(f"\n=== 검증 결과 ===\n{verify_result}")
        return 0

    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("CHAT_ID")
    if not token or not chat_id:
        logger.error("TELEGRAM_TOKEN 또는 CHAT_ID 미설정")
        return 1

    notifier = create_notifier(token, chat_id)
    sent_us = notifier.send_message(msg_us)
    sent_kr = notifier.send_message(msg_kr)
    logger.info(f"발송 결과: 미국={sent_us}, 한국={sent_kr}")
    return 0 if (sent_us and sent_kr) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="트렌드 스캐너")
    parser.add_argument("--test", action="store_true", help="콘솔 출력 모드")
    args = parser.parse_args()
    sys.exit(main(test_mode=args.test))
```

- [ ] **Step 11.2: 컴파일·import 검증**

```bash
python -c "import src.trend_scanner; print('ok')"
```
Expected: `ok`

- [ ] **Step 11.3: --test 모드 smoke test (네트워크 + Gemini API 사용)**

> **주의:** 이 단계는 실제 Gemini API 호출이 발생한다. `.env`의 `GOOGLE_API_KEY_01`이 유효해야 한다.

```bash
python -m src.trend_scanner --test 2>&1 | tee /tmp/trend_scanner_test.log
```
Expected:
- 수집 4회 INFO 로그
- AI 호출 3회 INFO 로그
- 콘솔에 "=== 미국 메시지 ===" / "=== 한국 메시지 ===" 출력
- 메시지에 [미뉴스#N] / [미커뮤#N] / [한뉴스#N] / [한커뮤#N] 인덱스 등장
- 검증 결과 `ok: True` 또는 `missing` 리스트

수동 sanity check:
- [ ] 추측 표현(`예상된다`, `~할 것이다`, `상승할`, `하락할`) grep으로 0건인가?

  ```bash
  grep -E "예상된다|전망된다|상승할|하락할|아마도|기대된다" /tmp/trend_scanner_test.log
  ```
  Expected: no output

- [ ] 메시지 길이가 4096자 미만인가? 출력 확인.

- [ ] **Step 11.4: 커밋**

```bash
git add src/trend_scanner.py
git commit -m "feat: trend_scanner — 메인 entrypoint (수집 + 3 AI 콜 + 검증 + 발송)"
```

---

## Task 12: GitHub Actions 워크플로우 + cron-job.org 가이드

**Files:**
- Create: `.github/workflows/trend_scan.yml`
- Modify: `docs/superpowers/specs/2026-04-27-trend-scanner-design.md` (cron-job 가이드는 이미 9.2 섹션에 포함됨)

- [ ] **Step 12.1: 워크플로우 작성**

`.github/workflows/trend_scan.yml`:
```yaml
name: Trend Scanner

on:
  workflow_dispatch:

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v3

      - name: Set up Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run Trend Scanner
        env:
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          CHAT_ID: ${{ secrets.CHAT_ID }}
          GOOGLE_API_KEY_01: ${{ secrets.GOOGLE_API_KEY_01 }}
          GOOGLE_API_KEY_02: ${{ secrets.GOOGLE_API_KEY_02 }}
          GOOGLE_API_KEY_03: ${{ secrets.GOOGLE_API_KEY_03 }}
        run: |
          python -m src.trend_scanner
```

- [ ] **Step 12.2: 워크플로우 yaml 문법 검증**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/trend_scan.yml')); print('ok')"
```
Expected: `ok`

- [ ] **Step 12.3: 커밋**

```bash
git add .github/workflows/trend_scan.yml
git commit -m "ci: trend_scan 워크플로우 (workflow_dispatch only, cron-job.org 트리거)"
```

- [ ] **Step 12.4: cron-job.org 등록 (사용자 수동 작업, 안내만)**

이 단계는 코드 변경이 없다. 사용자에게 안내만 표시한다:

```
cron-job.org 웹 UI에서 다음 2개 작업을 등록하세요:

1. Trend Scanner — Morning (07:30 KST 매일)
   URL:     POST https://api.github.com/repos/<owner>/trade_info_sender/actions/workflows/trend_scan.yml/dispatches
   Cron:    30 7 * * *
   Timezone: Asia/Seoul
   Headers:
     Authorization: Bearer <기존 PAT 또는 신규 발급>
     Accept: application/vnd.github+json
     X-GitHub-Api-Version: 2022-11-28
   Body: {"ref":"main"}

2. Trend Scanner — Evening (20:00 KST 매일)
   동일 설정, Cron만: 0 20 * * *
```

PAT은 기존 theme_analysis용 PAT 재사용 또는 신규 발급(`Repository access: trade_info_sender`, `Actions: Read and write`).

---

## Task 13: 전체 테스트 + task_history 기록

**Files:**
- Modify: `docs/task_history.md`

- [ ] **Step 13.1: 전체 단위 테스트 실행**

```bash
pytest tests/ -v
```
Expected: 모든 테스트 통과 (Task 2~10 누계, 약 30+ tests)

- [ ] **Step 13.2: task_history 추가**

`docs/task_history.md` 상단(맨 위 `# Task History` 헤더 바로 아래)에 다음 블록 추가. 같은 날짜 내 최신 항목이 상단:

```markdown
## 2026-04-27

### [기능] 트렌드 스캐너 — 매일 07:30·20:00 자동 발송 (2026-04-27 HH:MM KST)
- 변경 파일:
  - 신규: `src/trend_scanner.py`, `src/trend_collectors/` (base + 4개 수집기), `src/trend_extractor.py`, `src/trend_formatter.py`
  - 신규: `config/prompts/trend_extract.txt`, `trend_top3.txt`, `trend_outlook.txt`
  - 신규: `.github/workflows/trend_scan.yml`
  - 신규: `tests/` (pytest 인프라 + 단위 테스트 30+)
  - 수정: `src/ai_researcher.py` (`AIResearcher.call` 공개 메서드 추가)
  - 수정: `requirements.txt` (pytest 추가)
- 내용: 미국·한국 뉴스 30 + 커뮤니티 30 (총 120건) 수집 → Gemini 3콜(추출/TOP3/전망) → 텔레그램 2메시지 발송. 할루시네이션 가드 3중(인덱싱/프롬프트 제약/사후 매핑 검증). cron-job.org → GitHub workflow_dispatch 트리거. 매일 발송(휴일 포함).
- 스펙: `docs/superpowers/specs/2026-04-27-trend-scanner-design.md`
- 계획: `docs/superpowers/plans/2026-04-27-trend-scanner.md`
```

`HH:MM`은 실제 작업 완료 시각(KST).

- [ ] **Step 13.3: 커밋**

```bash
git add docs/task_history.md
git commit -m "docs: task_history — 트렌드 스캐너 신규 기능 이력 추가"
```

---

## Self-Review (계획 작성자가 직접 점검)

**1. Spec coverage 확인:**
- ✅ 결정 #1 (별도 신규 파이프라인) → Task 11, 12
- ✅ 결정 #2 (Google News RSS 우선) → Task 3, 5
- ✅ 결정 #3 (Reddit 4곳 + 디시 주식갤) → Task 4, 6
- ✅ 결정 #4·#5 (LLM 추출 3콜) → Task 9
- ✅ 결정 #6 (휴일 포함 매일) → Task 12 (cron 식 `* * *`, 요일 제한 없음)
- ✅ 결정 #7 (07:30 + 20:00) → Task 12
- ✅ 결정 #8 (2메시지 + 3~4줄) → Task 8 (프롬프트), Task 10 (포맷)
- ✅ 결정 #9 (텍스트만, 추측 금지) → Task 8 (프롬프트 시스템 제약)
- ✅ 결정 #10 (B+C+Y) → Task 8 (프롬프트), Task 9 (verify_indices), Task 10 (포맷에 검증 결과 표기)
- ✅ 결정 #11 (신규 파일 분리) → Task 2~6, 9~11
- ✅ 결정 #12 (24h 윈도우) → Task 3~6
- ✅ 결정 #13 (cron-job.org) → Task 12

**2. Placeholder scan:**
- ✅ "TBD" / "TODO" 없음
- ✅ 모든 코드 step에 실제 코드 포함
- ✅ 모든 명령어와 expected output 명시

**3. Type 일관성:**
- `CollectedItem(batch, idx, title, body, url, published_at)` — Task 2에서 정의, Task 3~6, 9, 11에서 일관 사용
- `verify_indices` 반환 `{"ok", "missing", "total_refs"}` — Task 9 정의, Task 10·11에서 일관 사용
- `format_us(now, top3, outlook, counts, verify_result)` — Task 10 정의, Task 11에서 동일 시그니처 호출
- `extract_per_batch / select_top3 / generate_outlook` — Task 9 정의, Task 11에서 일관 사용
- `AIResearcher.call(prompt, ..., temperature, max_output_tokens)` — Task 7 정의, Task 9의 `_parse_json_with_retry`에서 호출

**모든 항목 검증 완료.**

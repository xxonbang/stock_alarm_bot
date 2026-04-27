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

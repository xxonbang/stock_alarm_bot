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
    if not pub:
        return None
    published = datetime(*pub[:6], tzinfo=timezone.utc)
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

    six_hours_ago = now - timedelta(hours=6)
    items.sort(
        key=lambda x: (x.published_at >= six_hours_ago, len(x.body) >= 200, x.published_at),
        reverse=True,
    )
    items = items[:limit]
    for i, it in enumerate(items, start=1):
        it.idx = i
    logger.info(f"kr_news 수집 완료: {len(items)}개")
    return items


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for it in collect():
        print(f"[#{it.idx}] {it.title}")

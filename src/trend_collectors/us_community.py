"""미국 주식 커뮤니티 수집 — Reddit JSON"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

try:
    from curl_cffi import requests as _requests
    _IMPERSONATE_KWARGS = {"impersonate": "chrome120"}
except ImportError:
    import requests as _requests
    _IMPERSONATE_KWARGS = {}

from src.trend_collectors.base import CollectedItem

logger = logging.getLogger(__name__)

DEFAULT_SUBS = ["wallstreetbets", "stocks", "investing", "StockMarket"]
ENDPOINT = "https://www.reddit.com/r/{sub}/hot.json?limit=50"
HEADERS = {"User-Agent": "trade-info-sender/1.0 (by xxonbang)"}


def _fetch_subreddit(sub: str) -> dict:
    """Reddit JSON 호출 (테스트에서 mock)"""
    url = ENDPOINT.format(sub=sub)
    resp = _requests.get(url, headers=HEADERS, timeout=15, **_IMPERSONATE_KWARGS)
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
    scores: dict[str, int] = {}
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
            scores[item.url] = post.get("score", 0)
            items.append(item)

    # 본문 200자 이상 우선, 그 후 score 내림차순
    items.sort(key=lambda x: (len(x.body) >= 200, scores.get(x.url, 0)), reverse=True)
    items = items[:limit]

    for i, it in enumerate(items, start=1):
        it.idx = i

    logger.info(f"us_community 수집 완료: {len(items)}개")
    return items


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for it in collect():
        print(f"[#{it.idx}] {it.title}")

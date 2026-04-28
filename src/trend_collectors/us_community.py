"""미국 주식 커뮤니티 수집 — Hacker News (Algolia) + StockTwits trending

Reddit JSON은 GitHub Actions IP에서 403 차단되어 신뢰도 낮음.
HN Algolia + StockTwits 공개 API는 무인증·안정적·GH Actions 친화적.
"""
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

HN_ENDPOINT = "https://hn.algolia.com/api/v1/search?query={q}&tags=story&hitsPerPage=30"
HN_KEYWORDS = ["stock market", "wall street", "S&P 500", "nasdaq", "earnings"]

STOCKTWITS_TRENDING = "https://api.stocktwits.com/api/2/streams/trending.json?limit=30"

HEADERS = {"User-Agent": "trade-info-sender/1.0"}


def _fetch_hn(keyword: str) -> dict:
    """Hacker News Algolia API 호출 (테스트에서 mock)"""
    url = HN_ENDPOINT.format(q=keyword.replace(" ", "+").replace("&", "%26"))
    resp = _requests.get(url, headers=HEADERS, timeout=15, **_IMPERSONATE_KWARGS)
    resp.raise_for_status()
    return resp.json()


def _fetch_stocktwits() -> dict:
    """StockTwits trending stream (테스트에서 mock)"""
    resp = _requests.get(STOCKTWITS_TRENDING, headers=HEADERS, timeout=15, **_IMPERSONATE_KWARGS)
    resp.raise_for_status()
    return resp.json()


def _hn_hit_to_item(hit: dict, now: datetime) -> Optional[CollectedItem]:
    title = (hit.get("title") or "").strip()
    if not title:
        return None
    created = hit.get("created_at_i")
    if created is None:
        return None
    published = datetime.fromtimestamp(created, tz=timezone.utc)
    if published < now - timedelta(hours=24):
        return None
    body = (hit.get("story_text") or "").strip()
    obj_id = hit.get("objectID")
    url = hit.get("url") or (f"https://news.ycombinator.com/item?id={obj_id}" if obj_id else "")
    if not url:
        return None
    return CollectedItem(
        batch="us_community", idx=0,
        title=title, body=body, url=url, published_at=published,
    )


def _stocktwits_msg_to_item(msg: dict, now: datetime) -> Optional[CollectedItem]:
    body = (msg.get("body") or "").strip()
    if not body:
        return None
    msg_id = msg.get("id")
    created_at = msg.get("created_at")
    if not created_at:
        return None
    try:
        published = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if published < now - timedelta(hours=24):
        return None
    user = msg.get("user", {}) or {}
    username = user.get("username", "stocktwits")
    symbols = [s.get("symbol", "") for s in (msg.get("symbols") or []) if s.get("symbol")]
    title = f"[{', '.join(symbols)}] {body[:80]}" if symbols else body[:120]
    url = f"https://stocktwits.com/{username}/message/{msg_id}" if msg_id else ""
    if not url:
        return None
    return CollectedItem(
        batch="us_community", idx=0,
        title=title.strip(), body=body, url=url, published_at=published,
    )


def collect(now: Optional[datetime] = None, limit: int = 30) -> List[CollectedItem]:
    """HN + StockTwits 통합. 24h 윈도우, URL 중복 제거, limit개 반환."""
    if now is None:
        now = datetime.now(timezone.utc)

    seen_urls = set()
    items: List[CollectedItem] = []
    scores: dict = {}

    # 1. Hacker News (5 keywords)
    for kw in HN_KEYWORDS:
        try:
            data = _fetch_hn(kw)
        except Exception as e:
            logger.warning(f"HN fetch 실패 ({kw}): {e}")
            continue
        for hit in data.get("hits", []):
            it = _hn_hit_to_item(hit, now)
            if not it:
                continue
            if it.url in seen_urls:
                continue
            seen_urls.add(it.url)
            scores[it.url] = hit.get("points", 0) or 0
            items.append(it)

    # 2. StockTwits trending
    try:
        data = _fetch_stocktwits()
        for msg in data.get("messages", []):
            it = _stocktwits_msg_to_item(msg, now)
            if not it:
                continue
            if it.url in seen_urls:
                continue
            seen_urls.add(it.url)
            scores[it.url] = (msg.get("conversation", {}) or {}).get("replies", 0) or 0
            items.append(it)
    except Exception as e:
        logger.warning(f"StockTwits fetch 실패: {e}")

    # 본문 200자 이상 우선, 그 후 score 내림차순
    items.sort(key=lambda x: (len(x.body) >= 200, scores.get(x.url, 0)), reverse=True)
    items = items[:limit]
    for i, it in enumerate(items, start=1):
        it.idx = i
    logger.info(f"us_community 수집 완료: {len(items)}개 (HN+StockTwits)")
    return items


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for it in collect():
        print(f"[#{it.idx}] {it.title}")

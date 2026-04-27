"""한국 주식 커뮤니티 수집 — 디시 주식갤"""
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as _requests
    _IMPERSONATE_KWARGS = {"impersonate": "chrome120"}
except ImportError:
    import requests as _requests
    _IMPERSONATE_KWARGS = {}

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
    resp = _requests.get(url, headers=HEADERS, timeout=15, **_IMPERSONATE_KWARGS)
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

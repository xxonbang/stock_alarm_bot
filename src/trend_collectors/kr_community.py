"""한국 주식 커뮤니티 수집 — 에펨코리아 주식 + 38커뮤니케이션 장내 토론방 + 클리앙 새로운소식

기존 디시 주식갤은 차단됨. 위 3개 사이트는 정적 HTML, 무인증, 차단 적음.
"""
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
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

FMKOREA_URL = "https://www.fmkorea.com/index.php?mid=stock"
SAM8_URL = "https://www.38.co.kr/html/board/?code=380058"
CLIEN_URL = "https://www.clien.net/service/board/news"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.google.com/",
}


def _fetch(url: str) -> str:
    resp = _requests.get(url, headers=HEADERS, timeout=15, **_IMPERSONATE_KWARGS)
    resp.raise_for_status()
    return resp.text


_HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
_YY_MD_RE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{2})$")
_YYYY_MD_HMS_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})$")
_YYYY_MD_HM_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})$")
_HHMMSS_RE = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2})$")


def _parse_relative_time(text: str, now: datetime) -> Optional[datetime]:
    """다양한 시간 포맷 파싱 → KST datetime"""
    text = (text or "").strip()
    if not text:
        return None
    # YYYY-MM-DD HH:MM:SS
    m = _YYYY_MD_HMS_RE.match(text)
    if m:
        y, mo, d, h, mi, s = map(int, m.groups())
        return datetime(y, mo, d, h, mi, s, tzinfo=KST)
    # YYYY-MM-DD HH:MM
    m = _YYYY_MD_HM_RE.match(text)
    if m:
        y, mo, d, h, mi = map(int, m.groups())
        return datetime(y, mo, d, h, mi, 0, tzinfo=KST)
    # HH:MM:SS (오늘)
    m = _HHMMSS_RE.match(text)
    if m:
        h, mi, s = map(int, m.groups())
        return now.replace(hour=h, minute=mi, second=s, microsecond=0)
    # HH:MM (오늘)
    m = _HHMM_RE.match(text)
    if m:
        h, mi = map(int, m.groups())
        return now.replace(hour=h, minute=mi, second=0, microsecond=0)
    # YY.MM.DD (옛 글)
    m = _YY_MD_RE.match(text)
    if m:
        yy, mo, d = map(int, m.groups())
        y = 2000 + yy if yy < 70 else 1900 + yy
        return datetime(y, mo, d, 0, 0, 0, tzinfo=KST)
    return None


def _collect_fmkorea(html: str, now: datetime) -> List[CollectedItem]:
    """에펨코리아 주식 게시판 파싱"""
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table tbody tr:not(.notice)")
    items: List[CollectedItem] = []
    for row in rows:
        # 글 링크: href가 '/숫자' 형태 (카테고리/팝업 제외)
        title_a = None
        for a in row.select("a"):
            href = a.get("href") or ""
            if re.fullmatch(r"/\d+", href):
                title_a = a
                break
        if not title_a:
            continue
        title = title_a.get_text(strip=True)
        if not title or len(title) < 3:
            continue
        url = urljoin("https://www.fmkorea.com", title_a.get("href"))
        time_cell = row.select_one("td.time, .time")
        published = _parse_relative_time(time_cell.get_text(strip=True) if time_cell else "", now)
        if published is None:
            continue
        items.append(CollectedItem(
            batch="kr_community", idx=0,
            title=title, body="",
            url=url, published_at=published,
        ))
    return items


def _collect_sam8(html: str, now: datetime) -> List[CollectedItem]:
    """38커뮤니케이션 장내 토론방 파싱"""
    soup = BeautifulSoup(html, "html.parser")
    items: List[CollectedItem] = []
    seen_in_page = set()
    for a in soup.select("a"):
        href = a.get("href") or ""
        # 글 URL 패턴: ?o=v&code=380058&no=...
        if "o=v" not in href or "code=380058" not in href or "no=" not in href:
            continue
        title = a.get_text(strip=True)
        if not title or len(title) < 3 or title in seen_in_page:
            continue
        seen_in_page.add(title)
        url = urljoin("https://www.38.co.kr/html/board/", href)
        # 38커뮤는 시간 정보가 행에 분리되어 있어 행 단위로 찾아야 함
        row = a.find_parent("tr")
        time_text = ""
        if row:
            for cell in row.select("td"):
                t = cell.get_text(strip=True)
                if _HHMM_RE.match(t) or _YY_MD_RE.match(t):
                    time_text = t
                    break
        published = _parse_relative_time(time_text, now)
        if published is None:
            continue
        items.append(CollectedItem(
            batch="kr_community", idx=0,
            title=title, body="",
            url=url, published_at=published,
        ))
    return items


def _collect_clien(html: str, now: datetime) -> List[CollectedItem]:
    """클리앙 새로운소식 파싱"""
    soup = BeautifulSoup(html, "html.parser")
    items: List[CollectedItem] = []
    for it in soup.select("div.list_item.symph_row"):
        subject = it.select_one("span.subject_fixed")
        link = it.select_one("a.list_subject")
        if not (subject and link):
            continue
        title = (subject.get("title") or subject.get_text(strip=True)).strip()
        if not title or len(title) < 3:
            continue
        href = link.get("href") or ""
        url = urljoin("https://www.clien.net", href)
        # 정확한 시각: span.timestamp 안의 'YYYY-MM-DD HH:MM:SS'
        ts_elem = it.select_one("span.timestamp")
        time_text = ts_elem.get_text(strip=True) if ts_elem else ""
        published = _parse_relative_time(time_text, now)
        if published is None:
            continue
        items.append(CollectedItem(
            batch="kr_community", idx=0,
            title=title, body="",
            url=url, published_at=published,
        ))
    return items


_SOURCES: List[Tuple[str, str, callable]] = [
    ("fmkorea", FMKOREA_URL, _collect_fmkorea),
    ("38커뮤", SAM8_URL, _collect_sam8),
    ("clien", CLIEN_URL, _collect_clien),
]


def collect(now: Optional[datetime] = None, limit: int = 30) -> List[CollectedItem]:
    """3개 소스 통합. 24h 윈도우, URL 중복 제거, limit개 반환."""
    if now is None:
        now = datetime.now(KST)
    since = now - timedelta(hours=24)

    seen_urls = set()
    items: List[CollectedItem] = []

    for source_name, url, parser in _SOURCES:
        try:
            html = _fetch(url)
        except Exception as e:
            logger.warning(f"kr_community fetch 실패 ({source_name}): {e}")
            continue
        try:
            parsed = parser(html, now)
        except Exception as e:
            logger.warning(f"kr_community 파싱 실패 ({source_name}): {e}")
            continue
        for it in parsed:
            if it.published_at < since:
                continue
            if it.url in seen_urls:
                continue
            seen_urls.add(it.url)
            items.append(it)
        logger.info(f"  {source_name}: {len([x for x in parsed if x.published_at >= since])}개 (24h 내)")

    # 발행시간 내림차순 정렬
    items.sort(key=lambda x: x.published_at, reverse=True)
    items = items[:limit]
    for i, it in enumerate(items, start=1):
        it.idx = i
    logger.info(f"kr_community 수집 완료: {len(items)}개 (에펨+38+클리앙)")
    return items


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for it in collect():
        print(f"[#{it.idx}] {it.title}")

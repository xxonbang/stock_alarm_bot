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


def test_collect_dedupes_url_across_pages():
    """베스트와 실시간 두 페이지에서 같은 글 등장 시 1번만"""
    html_a = """<html><body><table><tbody>
    <tr class="ub-content">
      <td class="gall_tit ub-word"><a href="/board/view/?id=stock_new1&no=11111">공통 글</a></td>
      <td class="gall_date" title="2026-04-27 06:00:00">06:00</td>
    </tr>
    </tbody></table></body></html>"""
    html_b = """<html><body><table><tbody>
    <tr class="ub-content">
      <td class="gall_tit ub-word"><a href="/board/view/?id=stock_new1&no=11111">공통 글</a></td>
      <td class="gall_date" title="2026-04-27 05:30:00">05:30</td>
    </tr>
    <tr class="ub-content">
      <td class="gall_tit ub-word"><a href="/board/view/?id=stock_new1&no=22222">B에만</a></td>
      <td class="gall_date" title="2026-04-27 05:00:00">05:00</td>
    </tr>
    </tbody></table></body></html>"""

    now = datetime(2026, 4, 27, 7, 30, tzinfo=KST)
    with patch("src.trend_collectors.kr_community._fetch_listing",
               side_effect=[html_a, html_b]):
        items = collect(now=now, limit=30)
    titles = [it.title for it in items]
    assert titles.count("공통 글") == 1
    assert "B에만" in titles

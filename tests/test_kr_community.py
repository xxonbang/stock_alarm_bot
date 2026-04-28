"""kr_community collector 테스트 (에펨코리아 + 38커뮤 + 클리앙)"""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from src.trend_collectors.kr_community import (
    collect,
    _collect_fmkorea,
    _collect_sam8,
    _collect_clien,
)


KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 4, 28, 22, 0, tzinfo=KST)


FMKOREA_HTML = """
<table><tbody>
  <tr class="notice"><td><a href="/index.php?mid=stock&category=1">공지</a></td><td class="time">25.01.01</td></tr>
  <tr><td><a href="/index.php?mid=stock&category=2997204381">해외주식</a></td>
      <td><a href="/9763040708">마소 넷플에 1억씩 박아두고</a></td>
      <td class="time">21:44</td></tr>
  <tr><td><a href="/index.php?mid=stock&category=2997203870">국내주식</a></td>
      <td><a href="/9763040775">마지막 골파기라고 믿는다</a></td>
      <td class="time">20:30</td></tr>
  <tr><td><a href="/9999999999">오래된 글</a></td>
      <td class="time">26.04.01</td></tr>
</tbody></table>
"""

SAM8_HTML = """
<table><tbody>
  <tr><td><a href="?o=v&code=380058&no=103394&page=1">[애드바이오텍]애드바이오의 질주</a></td>
      <td>21:30</td></tr>
  <tr><td><a href="?o=v&code=380058&no=103389&page=1">[삼진식품]4만원까지 보고 팔자</a></td>
      <td>20:00</td></tr>
  <tr><td><a href="?o=v&code=380058&no=103388&page=1">오래된 글</a></td>
      <td>26.04.01</td></tr>
</tbody></table>
"""

CLIEN_HTML = """
<div class="list_item symph_row">
  <div class="list_title">
    <a class="list_subject" href="/service/board/news/19183832">
      <span class="subject_fixed" title="[루머] 삼성 갤럭시Z 폴더블">[루머] 삼성 갤럭시Z 폴더블</span>
    </a>
  </div>
  <div class="list_time"><span class="time"><span class="timestamp">2026-04-28 19:31:26</span></span></div>
</div>
<div class="list_item symph_row">
  <div class="list_title">
    <a class="list_subject" href="/service/board/news/19183830">
      <span class="subject_fixed" title="머스크 X 금융 비즈니스">머스크 X 금융 비즈니스</span>
    </a>
  </div>
  <div class="list_time"><span class="time"><span class="timestamp">2026-04-28 19:22:48</span></span></div>
</div>
<div class="list_item symph_row">
  <div class="list_title">
    <a class="list_subject" href="/service/board/news/old">
      <span class="subject_fixed" title="옛글">옛글</span>
    </a>
  </div>
  <div class="list_time"><span class="time"><span class="timestamp">2026-04-25 10:00:00</span></span></div>
</div>
"""


def test_fmkorea_parses_real_posts_skips_notices_and_categories():
    items = _collect_fmkorea(FMKOREA_HTML, NOW)
    titles = [it.title for it in items]
    assert "마소 넷플에 1억씩 박아두고" in titles
    assert "마지막 골파기라고 믿는다" in titles
    assert "공지" not in titles
    assert "해외주식" not in titles
    assert "국내주식" not in titles


def test_sam8_parses_post_links():
    items = _collect_sam8(SAM8_HTML, NOW)
    titles = [it.title for it in items]
    assert "[애드바이오텍]애드바이오의 질주" in titles
    assert "[삼진식품]4만원까지 보고 팔자" in titles


def test_clien_parses_subject_and_timestamp():
    items = _collect_clien(CLIEN_HTML, NOW)
    titles = [it.title for it in items]
    assert "[루머] 삼성 갤럭시Z 폴더블" in titles
    assert "머스크 X 금융 비즈니스" in titles


def test_collect_filters_24h_across_sources():
    """3개 소스 모두 24h 밖 글 제외"""
    with patch("src.trend_collectors.kr_community._fetch") as mock_fetch:
        mock_fetch.side_effect = [FMKOREA_HTML, SAM8_HTML, CLIEN_HTML]
        items = collect(now=NOW, limit=30)
    titles = [it.title for it in items]
    assert "마소 넷플에 1억씩 박아두고" in titles
    assert "[애드바이오텍]애드바이오의 질주" in titles
    assert "[루머] 삼성 갤럭시Z 폴더블" in titles
    assert "오래된 글" not in titles
    assert "옛글" not in titles


def test_collect_sets_batch_kr_community():
    with patch("src.trend_collectors.kr_community._fetch") as mock_fetch:
        mock_fetch.side_effect = [FMKOREA_HTML, SAM8_HTML, CLIEN_HTML]
        items = collect(now=NOW, limit=30)
    assert all(it.batch == "kr_community" for it in items)


def test_collect_assigns_sequential_idx():
    with patch("src.trend_collectors.kr_community._fetch") as mock_fetch:
        mock_fetch.side_effect = [FMKOREA_HTML, SAM8_HTML, CLIEN_HTML]
        items = collect(now=NOW, limit=30)
    assert [it.idx for it in items] == list(range(1, len(items) + 1))


def test_collect_one_source_failure_does_not_abort_others():
    """fmkorea 실패해도 나머지 진행"""
    with patch("src.trend_collectors.kr_community._fetch") as mock_fetch:
        mock_fetch.side_effect = [Exception("fmkorea blocked"), SAM8_HTML, CLIEN_HTML]
        items = collect(now=NOW, limit=30)
    titles = [it.title for it in items]
    assert "[애드바이오텍]애드바이오의 질주" in titles
    assert "[루머] 삼성 갤럭시Z 폴더블" in titles


def test_collect_all_sources_failure_returns_empty():
    """모두 실패 시 빈 리스트"""
    with patch("src.trend_collectors.kr_community._fetch",
               side_effect=Exception("all blocked")):
        items = collect(now=NOW, limit=30)
    assert items == []


def test_parse_time_formats():
    """시간 포맷 다양성 확인"""
    from src.trend_collectors.kr_community import _parse_relative_time
    now = datetime(2026, 4, 28, 22, 0, tzinfo=KST)
    assert _parse_relative_time("21:30", now).hour == 21
    assert _parse_relative_time("2026-04-28 19:31:26", now).day == 28
    assert _parse_relative_time("26.04.01", now).month == 4
    assert _parse_relative_time("garbage", now) is None

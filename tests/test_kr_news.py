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


def test_collect_drops_undated_entries():
    """published_parsed 없는 entry는 24h 필터를 우회하지 않고 드롭"""
    feed_no_date = feedparser.parse("""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>날짜 없는 글</title>
    <link>https://example.com/no-date</link>
    <description>pubDate 없음</description>
  </item>
  <item>
    <title>정상 글</title>
    <link>https://example.com/normal</link>
    <pubDate>Mon, 27 Apr 2026 06:00:00 GMT</pubDate>
    <description>정상.</description>
  </item>
</channel></rss>""")
    now = datetime(2026, 4, 27, 7, 30, tzinfo=timezone.utc)
    with patch("src.trend_collectors.kr_news._fetch_feed", return_value=feed_no_date):
        items = collect(now=now, limit=30)
    titles = [it.title for it in items]
    assert "날짜 없는 글" not in titles
    assert "정상 글" in titles


def test_collect_dedupes_by_url():
    """다른 키워드에서 같은 URL 등장 시 1번만 포함"""
    feed_a = feedparser.parse("""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>공통 헤드라인</title>
    <link>https://example.com/shared</link>
    <pubDate>Mon, 27 Apr 2026 06:00:00 GMT</pubDate>
    <description>공통.</description>
  </item>
  <item>
    <title>A에만</title>
    <link>https://example.com/a-only</link>
    <pubDate>Mon, 27 Apr 2026 06:00:00 GMT</pubDate>
    <description>A.</description>
  </item>
</channel></rss>""")
    feed_b = feedparser.parse("""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>공통 헤드라인</title>
    <link>https://example.com/shared</link>
    <pubDate>Mon, 27 Apr 2026 06:00:00 GMT</pubDate>
    <description>공통.</description>
  </item>
  <item>
    <title>B에만</title>
    <link>https://example.com/b-only</link>
    <pubDate>Mon, 27 Apr 2026 06:00:00 GMT</pubDate>
    <description>B.</description>
  </item>
</channel></rss>""")
    feed_c = feedparser.parse("""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel></channel></rss>""")

    now = datetime(2026, 4, 27, 7, 30, tzinfo=timezone.utc)
    # KEYWORDS has 3 entries; cycle 3 distinct feeds
    with patch(
        "src.trend_collectors.kr_news._fetch_feed",
        side_effect=[feed_a, feed_b, feed_c],
    ):
        items = collect(now=now, limit=30)
    urls = [it.url for it in items]
    assert urls.count("https://example.com/shared") == 1
    assert "https://example.com/a-only" in urls
    assert "https://example.com/b-only" in urls

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

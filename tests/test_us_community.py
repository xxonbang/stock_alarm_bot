"""us_community collector 테스트 (HN + StockTwits)"""
from datetime import datetime, timezone
from unittest.mock import patch

from src.trend_collectors.us_community import collect


NOW_TS = 1779120000  # 2026-05-13T15:00:00Z (테스트 anchor)
NOW = datetime.fromtimestamp(NOW_TS, tz=timezone.utc)


def _hn_fixture():
    """Hacker News Algolia 응답 형태"""
    return {
        "hits": [
            {
                "objectID": "111",
                "title": "Nvidia AI demand surges",
                "url": "https://example.com/nvidia",
                "story_text": "Strong AI guidance from major cloud providers driving demand. " * 4,
                "created_at_i": NOW_TS - 3600,
                "points": 320,
                "author": "user1",
            },
            {
                "objectID": "222",
                "title": "Old story",
                "url": "https://example.com/old",
                "story_text": "ancient",
                "created_at_i": NOW_TS - 25 * 3600,  # 윈도우 밖
                "points": 50,
            },
            {
                "objectID": "333",
                "title": "No URL story",
                "url": None,
                "story_text": "",
                "created_at_i": NOW_TS - 1000,
                "points": 100,
            },
            {
                "objectID": "",
                "title": "Empty objectID and no url",
                "url": "",
                "story_text": "",
                "created_at_i": NOW_TS - 1000,
                "points": 50,
            },
        ]
    }


def _stocktwits_fixture():
    """StockTwits trending 응답 형태"""
    return {
        "messages": [
            {
                "id": 901,
                "body": "TSLA breaking out on volume",
                "created_at": "2026-05-18T15:30:00Z",
                "user": {"username": "trader1"},
                "symbols": [{"symbol": "TSLA"}],
                "conversation": {"replies": 12},
            },
            {
                "id": 902,
                "body": "AAPL earnings tomorrow, watch volatility",
                "created_at": "2026-05-18T15:00:00Z",
                "user": {"username": "trader2"},
                "symbols": [{"symbol": "AAPL"}],
                "conversation": {"replies": 8},
            },
            {
                "id": 903,
                "body": "old message",
                "created_at": "2026-05-17T10:00:00Z",  # 25h+ 전
                "user": {"username": "trader3"},
                "symbols": [],
            },
        ]
    }


def test_collect_filters_24h_hn():
    with patch("src.trend_collectors.us_community._fetch_hn", return_value=_hn_fixture()), \
         patch("src.trend_collectors.us_community._fetch_stocktwits", return_value={"messages": []}):
        items = collect(now=NOW, limit=30)
    titles = [it.title for it in items]
    assert "Nvidia AI demand surges" in titles
    assert "Old story" not in titles


def test_collect_filters_24h_stocktwits():
    with patch("src.trend_collectors.us_community._fetch_hn", return_value={"hits": []}), \
         patch("src.trend_collectors.us_community._fetch_stocktwits", return_value=_stocktwits_fixture()):
        items = collect(now=NOW, limit=30)
    bodies = [it.body for it in items]
    assert any("TSLA" in b for b in bodies)
    assert "old message" not in [it.body for it in items]


def test_collect_skips_hn_hits_without_url():
    with patch("src.trend_collectors.us_community._fetch_hn", return_value=_hn_fixture()), \
         patch("src.trend_collectors.us_community._fetch_stocktwits", return_value={"messages": []}):
        items = collect(now=NOW, limit=30)
    titles = [it.title for it in items]
    # objectID 있고 url null이면 fallback URL 생성
    assert "No URL story" in titles
    # 둘 다 없으면 제외
    assert "Empty objectID and no url" not in titles


def test_collect_sets_batch_us_community():
    with patch("src.trend_collectors.us_community._fetch_hn", return_value=_hn_fixture()), \
         patch("src.trend_collectors.us_community._fetch_stocktwits", return_value=_stocktwits_fixture()):
        items = collect(now=NOW, limit=30)
    assert all(it.batch == "us_community" for it in items)


def test_collect_assigns_sequential_idx():
    with patch("src.trend_collectors.us_community._fetch_hn", return_value=_hn_fixture()), \
         patch("src.trend_collectors.us_community._fetch_stocktwits", return_value=_stocktwits_fixture()):
        items = collect(now=NOW, limit=30)
    assert [it.idx for it in items] == list(range(1, len(items) + 1))


def test_collect_returns_empty_on_both_failures():
    """양쪽 모두 실패해도 abort하지 않고 빈 배치 반환"""
    with patch("src.trend_collectors.us_community._fetch_hn",
               side_effect=Exception("HN blocked")), \
         patch("src.trend_collectors.us_community._fetch_stocktwits",
               side_effect=Exception("ST blocked")):
        items = collect(now=NOW, limit=30)
    assert items == []


def test_collect_one_source_failure_does_not_abort():
    """한 소스 실패해도 다른 소스 결과 반환"""
    with patch("src.trend_collectors.us_community._fetch_hn",
               side_effect=Exception("HN failed")), \
         patch("src.trend_collectors.us_community._fetch_stocktwits",
               return_value=_stocktwits_fixture()):
        items = collect(now=NOW, limit=30)
    assert len(items) > 0
    assert all(it.batch == "us_community" for it in items)


def test_collect_body_length_priority_sort():
    """본문 200자 이상이 짧은 글보다 우선"""
    long_body = "x" * 250
    hn_fix = {
        "hits": [
            {"objectID": "a", "title": "Short", "url": "https://example.com/s",
             "story_text": "tiny", "created_at_i": NOW_TS - 100, "points": 9999},
            {"objectID": "b", "title": "Long", "url": "https://example.com/l",
             "story_text": long_body, "created_at_i": NOW_TS - 200, "points": 1},
        ]
    }
    with patch("src.trend_collectors.us_community._fetch_hn", return_value=hn_fix), \
         patch("src.trend_collectors.us_community._fetch_stocktwits", return_value={"messages": []}):
        items = collect(now=NOW, limit=30)
    assert items[0].title == "Long"
    assert items[1].title == "Short"

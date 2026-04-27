"""us_community collector 테스트"""
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.trend_collectors.us_community import collect


FIXTURE = Path(__file__).parent / "fixtures" / "reddit_wsb_sample.json"
NOW = datetime.fromtimestamp(1779120000, tz=timezone.utc)  # 픽스처 created_utc와 동일


def _fixture_json():
    return json.loads(FIXTURE.read_text())


def test_collect_filters_24h_window():
    with patch("src.trend_collectors.us_community._fetch_subreddit", return_value=_fixture_json()):
        items = collect(now=NOW, limit=30, subreddits=["wallstreetbets"])
    titles = [it.title for it in items]
    assert "NVDA earnings discussion" in titles
    assert "Old post" not in titles


def test_collect_excludes_nsfw():
    with patch("src.trend_collectors.us_community._fetch_subreddit", return_value=_fixture_json()):
        items = collect(now=NOW, limit=30, subreddits=["wallstreetbets"])
    titles = [it.title for it in items]
    assert "NSFW post" not in titles


def test_collect_sets_batch_us_community():
    with patch("src.trend_collectors.us_community._fetch_subreddit", return_value=_fixture_json()):
        items = collect(now=NOW, limit=30, subreddits=["wallstreetbets"])
    assert all(it.batch == "us_community" for it in items)


def test_collect_assigns_sequential_idx():
    with patch("src.trend_collectors.us_community._fetch_subreddit", return_value=_fixture_json()):
        items = collect(now=NOW, limit=30, subreddits=["wallstreetbets"])
    assert [it.idx for it in items] == list(range(1, len(items) + 1))

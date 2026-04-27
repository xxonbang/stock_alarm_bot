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


def test_collect_filters_stickied():
    """stickied 게시물 제외"""
    fixture = {
        "data": {
            "children": [
                {"data": {"id": "stk1", "title": "Pinned mod post",
                          "selftext": "moderator notice", "url": "https://reddit.com/x",
                          "permalink": "/r/x/comments/stk1",
                          "created_utc": 1779120000, "score": 999,
                          "over_18": False, "stickied": True}},
                {"data": {"id": "ok1", "title": "Normal post",
                          "selftext": "real content", "url": "https://reddit.com/y",
                          "permalink": "/r/y/comments/ok1",
                          "created_utc": 1779120000, "score": 100,
                          "over_18": False, "stickied": False}},
            ]
        }
    }
    with patch("src.trend_collectors.us_community._fetch_subreddit", return_value=fixture):
        items = collect(now=NOW, limit=30, subreddits=["wallstreetbets"])
    titles = [it.title for it in items]
    assert "Pinned mod post" not in titles
    assert "Normal post" in titles


def test_collect_filters_missing_created_utc():
    """created_utc 없는 게시물 제외"""
    fixture = {
        "data": {
            "children": [
                {"data": {"id": "nodate", "title": "No date",
                          "selftext": "x", "url": "https://reddit.com/nodate",
                          "permalink": "/r/x/comments/nodate",
                          "score": 50, "over_18": False, "stickied": False}},
                {"data": {"id": "ok", "title": "Has date",
                          "selftext": "y", "url": "https://reddit.com/ok",
                          "permalink": "/r/x/comments/ok",
                          "created_utc": 1779120000,
                          "score": 60, "over_18": False, "stickied": False}},
            ]
        }
    }
    with patch("src.trend_collectors.us_community._fetch_subreddit", return_value=fixture):
        items = collect(now=NOW, limit=30, subreddits=["wallstreetbets"])
    titles = [it.title for it in items]
    assert "No date" not in titles
    assert "Has date" in titles


def test_collect_dedupes_url_across_subs():
    """다른 서브에서 같은 URL 등장 시 1번만 포함"""
    shared = {"id": "s", "title": "Shared",
              "selftext": "x", "url": "https://reddit.com/shared",
              "permalink": "/r/x/comments/s",
              "created_utc": 1779120000, "score": 100,
              "over_18": False, "stickied": False}
    only_a = {"id": "a", "title": "A only",
              "selftext": "x", "url": "https://reddit.com/a",
              "permalink": "/r/a/comments/a",
              "created_utc": 1779120000, "score": 50,
              "over_18": False, "stickied": False}
    only_b = {"id": "b", "title": "B only",
              "selftext": "x", "url": "https://reddit.com/b",
              "permalink": "/r/b/comments/b",
              "created_utc": 1779120000, "score": 50,
              "over_18": False, "stickied": False}
    feed_a = {"data": {"children": [{"data": shared}, {"data": only_a}]}}
    feed_b = {"data": {"children": [{"data": shared}, {"data": only_b}]}}

    with patch("src.trend_collectors.us_community._fetch_subreddit",
               side_effect=[feed_a, feed_b]):
        items = collect(now=NOW, limit=30, subreddits=["x", "y"])
    urls = [it.url for it in items]
    assert urls.count("https://reddit.com/r/x/comments/s") == 1
    assert "https://reddit.com/r/a/comments/a" in urls
    assert "https://reddit.com/r/b/comments/b" in urls


def test_collect_body_length_sort_tiebreak():
    """본문 200자 이상이 짧은 글보다 우선"""
    long_body = "x" * 250
    fixture = {
        "data": {
            "children": [
                {"data": {"id": "short", "title": "Short body high score",
                          "selftext": "tiny", "url": "https://reddit.com/short",
                          "permalink": "/r/x/comments/short",
                          "created_utc": 1779120000, "score": 9999,
                          "over_18": False, "stickied": False}},
                {"data": {"id": "long", "title": "Long body low score",
                          "selftext": long_body, "url": "https://reddit.com/long",
                          "permalink": "/r/x/comments/long",
                          "created_utc": 1779120000, "score": 1,
                          "over_18": False, "stickied": False}},
            ]
        }
    }
    with patch("src.trend_collectors.us_community._fetch_subreddit", return_value=fixture):
        items = collect(now=NOW, limit=30, subreddits=["wallstreetbets"])
    # long body 우선
    assert items[0].title == "Long body low score"
    assert items[1].title == "Short body high score"


def test_collect_one_sub_failure_does_not_abort_others():
    """한 서브에서 fetch 예외 발생해도 다른 서브 계속 진행"""
    ok_post = {"id": "ok", "title": "OK Post",
               "selftext": "content", "url": "https://reddit.com/ok",
               "permalink": "/r/x/comments/ok",
               "created_utc": 1779120000, "score": 50,
               "over_18": False, "stickied": False}
    feed_ok = {"data": {"children": [{"data": ok_post}]}}

    with patch("src.trend_collectors.us_community._fetch_subreddit",
               side_effect=[Exception("blocked"), feed_ok]):
        items = collect(now=NOW, limit=30, subreddits=["bad", "good"])
    titles = [it.title for it in items]
    assert "OK Post" in titles

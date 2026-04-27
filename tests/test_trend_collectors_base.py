"""trend_collectors.base 테스트"""
from datetime import datetime
from zoneinfo import ZoneInfo

from src.trend_collectors.base import CollectedItem, label_for_batch, format_indexed_text


KST = ZoneInfo("Asia/Seoul")


def test_collected_item_dataclass():
    item = CollectedItem(
        batch="us_news",
        idx=1,
        title="Title",
        body="Body",
        url="https://example.com",
        published_at=datetime(2026, 4, 27, 7, 0, tzinfo=KST),
    )
    assert item.batch == "us_news"
    assert item.idx == 1


def test_label_for_batch_known():
    assert label_for_batch("us_news") == "미뉴스"
    assert label_for_batch("us_community") == "미커뮤"
    assert label_for_batch("kr_news") == "한뉴스"
    assert label_for_batch("kr_community") == "한커뮤"


def test_label_for_batch_unknown_raises():
    import pytest
    with pytest.raises(KeyError):
        label_for_batch("unknown")


def test_format_indexed_text_single_item():
    item = CollectedItem(
        batch="us_news", idx=3,
        title="AI surge", body="Companies are investing heavily.",
        url="https://x", published_at=datetime(2026, 4, 27, tzinfo=KST),
    )
    result = format_indexed_text([item])
    assert "[미뉴스#3]" in result
    assert "AI surge" in result
    assert "Companies are investing heavily." in result


def test_format_indexed_text_multiple_batches_separated():
    items = [
        CollectedItem("us_news", 1, "T1", "B1", "u1", datetime(2026, 4, 27, tzinfo=KST)),
        CollectedItem("kr_community", 2, "T2", "B2", "u2", datetime(2026, 4, 27, tzinfo=KST)),
    ]
    result = format_indexed_text(items)
    assert "[미뉴스#1]" in result
    assert "[한커뮤#2]" in result

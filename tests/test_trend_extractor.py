"""trend_extractor 테스트"""
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.trend_collectors.base import CollectedItem
from src.trend_extractor import verify_indices


KST = timezone.utc  # 테스트에서는 timezone 무관


def _make_batches():
    return {
        "us_news": [
            CollectedItem("us_news", i, f"T{i}", f"B{i}", f"u{i}", datetime(2026, 4, 27, tzinfo=KST))
            for i in range(1, 6)  # idx 1..5
        ],
        "us_community": [
            CollectedItem("us_community", i, f"CT{i}", f"CB{i}", f"cu{i}", datetime(2026, 4, 27, tzinfo=KST))
            for i in range(1, 4)  # idx 1..3
        ],
        "kr_news": [],
        "kr_community": [],
    }


def test_verify_indices_all_valid():
    text = "Nvidia가 강세 [미뉴스#3] [미커뮤#2]"
    result = verify_indices(text, _make_batches())
    assert result["ok"] is True
    assert result["missing"] == []
    assert result["total_refs"] == 2


def test_verify_indices_detects_missing():
    text = "잘못된 인덱스 [미뉴스#99] [미커뮤#1]"
    result = verify_indices(text, _make_batches())
    assert result["ok"] is False
    assert ("us_news", 99) in result["missing"]
    assert ("us_community", 1) not in result["missing"]


def test_verify_indices_no_refs():
    text = "인덱스 없음"
    result = verify_indices(text, _make_batches())
    assert result["ok"] is True
    assert result["total_refs"] == 0


def test_verify_indices_handles_korean_labels_only():
    """한국 배치도 동일하게 처리"""
    batches = _make_batches()
    batches["kr_news"] = [
        CollectedItem("kr_news", i, f"T{i}", f"B{i}", f"u{i}", datetime(2026, 4, 27, tzinfo=KST))
        for i in range(1, 4)
    ]
    text = "[한뉴스#2]"
    result = verify_indices(text, batches)
    assert result["ok"] is True


from src.trend_extractor import extract_per_batch


def test_extract_per_batch_passes_indexed_text_to_ai():
    batches = _make_batches()
    fake_response = json.dumps({
        "us_news":      {"stocks": [], "sectors": []},
        "us_community": {"stocks": [], "sectors": []},
        "kr_news":      {"stocks": [], "sectors": []},
        "kr_community": {"stocks": [], "sectors": []},
    })
    fake_researcher = MagicMock()
    fake_researcher.call.return_value = (fake_response, {"total_tokens": 100})

    result = extract_per_batch(batches, researcher=fake_researcher)

    # researcher.call이 호출되었고, 프롬프트에 [미뉴스#1], [미커뮤#1] 인덱스 포함
    fake_researcher.call.assert_called_once()
    prompt_arg = fake_researcher.call.call_args.kwargs.get("prompt") or fake_researcher.call.call_args.args[0]
    assert "[미뉴스#1]" in prompt_arg
    assert "[미커뮤#1]" in prompt_arg

    assert "us_news" in result
    assert "stocks" in result["us_news"]


def test_extract_per_batch_parses_json_with_codeblock_wrapper():
    """LLM이 ```json ... ``` 으로 감쌀 경우도 파싱"""
    batches = _make_batches()
    wrapped = "```json\n" + json.dumps({
        "us_news":      {"stocks": [{"name": "Nvidia", "freq": 5, "refs": [1,2,3,4,5]}], "sectors": []},
        "us_community": {"stocks": [], "sectors": []},
        "kr_news":      {"stocks": [], "sectors": []},
        "kr_community": {"stocks": [], "sectors": []},
    }) + "\n```"
    fake_researcher = MagicMock()
    fake_researcher.call.return_value = (wrapped, {"total_tokens": 100})

    result = extract_per_batch(batches, researcher=fake_researcher)

    assert result["us_news"]["stocks"][0]["name"] == "Nvidia"


def test_extract_per_batch_retries_on_invalid_json():
    """첫 응답이 JSON 파싱 실패면 1회 재시도"""
    batches = _make_batches()
    valid = json.dumps({
        "us_news":      {"stocks": [], "sectors": []},
        "us_community": {"stocks": [], "sectors": []},
        "kr_news":      {"stocks": [], "sectors": []},
        "kr_community": {"stocks": [], "sectors": []},
    })
    fake_researcher = MagicMock()
    fake_researcher.call.side_effect = [
        ("not a json", {"total_tokens": 50}),
        (valid, {"total_tokens": 100}),
    ]

    result = extract_per_batch(batches, researcher=fake_researcher)

    assert fake_researcher.call.call_count == 2
    assert "us_news" in result


from src.trend_extractor import select_top3


def test_select_top3_passes_extraction_to_ai():
    extraction = {"us_news": {"stocks": [], "sectors": []}, "us_community": {"stocks": [], "sectors": []},
                  "kr_news": {"stocks": [], "sectors": []}, "kr_community": {"stocks": [], "sectors": []}}
    fake_response = json.dumps({
        "us_top3_sectors": [], "us_top3_stocks": [],
        "kr_top3_sectors": [], "kr_top3_stocks": [],
    })
    fake_researcher = MagicMock()
    fake_researcher.call.return_value = (fake_response, {"total_tokens": 100})

    result = select_top3(extraction, researcher=fake_researcher)

    assert "us_top3_sectors" in result
    assert "kr_top3_stocks" in result
    fake_researcher.call.assert_called_once()
    prompt = fake_researcher.call.call_args.kwargs.get("prompt") or fake_researcher.call.call_args.args[0]
    assert "us_news" in prompt  # extraction JSON이 프롬프트에 들어감


from src.trend_extractor import generate_outlook


def test_generate_outlook_includes_only_referenced_texts():
    """TOP3 reason에 인용된 인덱스에 해당하는 글만 프롬프트에 포함"""
    batches = _make_batches()
    top3 = {
        "us_top3_sectors": [
            {"name": "AI", "reason": "...", "us_news_refs": [3], "us_community_refs": [2]},
        ],
        "us_top3_stocks": [],
        "kr_top3_sectors": [],
        "kr_top3_stocks": [],
    }
    fake_response = json.dumps({
        "us_sector_outlook": [], "us_stock_outlook": [],
        "kr_sector_outlook": [], "kr_stock_outlook": [],
    })
    fake_researcher = MagicMock()
    fake_researcher.call.return_value = (fake_response, {"total_tokens": 100})

    result = generate_outlook(top3, batches, researcher=fake_researcher)

    prompt = fake_researcher.call.call_args.kwargs.get("prompt") or fake_researcher.call.call_args.args[0]
    # 인용된 us_news#3, us_community#2 글이 프롬프트에 포함
    assert "[미뉴스#3]" in prompt
    assert "[미커뮤#2]" in prompt
    # 인용되지 않은 글은 미포함 (idx 1, 4, 5는 us_news에서 인용 안 됨)
    assert "[미뉴스#1]" not in prompt
    assert "us_sector_outlook" in result

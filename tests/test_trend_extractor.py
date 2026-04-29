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


def test_generate_outlook_passes_top3_to_ai_with_search_enabled():
    """generate_outlook은 TOP3를 프롬프트에 넣고 Google Search grounding을 활성화"""
    top3 = {
        "us_top3_sectors": [{"name": "AI 인프라", "reason": "..."}],
        "us_top3_stocks": [],
        "kr_top3_sectors": [],
        "kr_top3_stocks": [],
    }
    fake_response = json.dumps({
        "us_sector_outlook": [{"name": "AI 인프라", "outlook": "전망"}],
        "us_stock_outlook": [],
        "kr_sector_outlook": [], "kr_stock_outlook": [],
    })
    fake_researcher = MagicMock()
    fake_researcher.call.return_value = (fake_response, {"total_tokens": 100})

    result = generate_outlook(top3, researcher=fake_researcher)

    # researcher.call에 enable_search=True 전달
    fake_researcher.call.assert_called_once()
    kwargs = fake_researcher.call.call_args.kwargs
    assert kwargs.get("enable_search") is True
    # 프롬프트에 TOP3 내용 포함
    prompt = kwargs.get("prompt") or fake_researcher.call.call_args.args[0]
    assert "AI 인프라" in prompt
    assert "us_sector_outlook" in result


def test_generate_outlook_raises_when_top3_is_empty():
    """TOP3가 모두 비어있으면 RuntimeError"""
    import pytest
    top3_empty = {
        "us_top3_sectors": [],
        "us_top3_stocks": [],
        "kr_top3_sectors": [],
        "kr_top3_stocks": [],
    }
    fake_researcher = MagicMock()
    with pytest.raises(RuntimeError, match="TOP3 결과가 비어있어"):
        generate_outlook(top3_empty, researcher=fake_researcher)
    fake_researcher.call.assert_not_called()


def test_verify_indices_bundled_brackets_all_valid():
    text = "[미뉴스#3,#5,#1] [미커뮤#2,#3]"
    result = verify_indices(text, _make_batches())
    assert result["ok"] is True
    assert result["total_refs"] == 5  # 3+5+1+2+3 = 5 unique indices


def test_verify_indices_bundled_with_missing():
    text = "[미뉴스#3,#7,#99] [미커뮤#2]"  # us_news idx 7 doesn't exist (range 1..5)
    result = verify_indices(text, _make_batches())
    assert result["ok"] is False
    assert ("us_news", 7) in result["missing"]
    assert ("us_news", 99) in result["missing"]
    assert ("us_news", 3) not in result["missing"]


def test_verify_indices_mixed_single_and_bundled():
    text = "단일 [미뉴스#3] 그리고 묶음 [미커뮤#1,#2,#3]"
    result = verify_indices(text, _make_batches())
    assert result["ok"] is True
    assert result["total_refs"] == 4


def test_parse_json_retry_appends_clarification_suffix():
    """재시도 시 프롬프트에 clarification suffix 추가"""
    batches = _make_batches()
    valid = json.dumps({
        "us_news":      {"stocks": [], "sectors": []},
        "us_community": {"stocks": [], "sectors": []},
        "kr_news":      {"stocks": [], "sectors": []},
        "kr_community": {"stocks": [], "sectors": []},
    })
    fake_researcher = MagicMock()
    fake_researcher.call.side_effect = [
        ("not json", {"total_tokens": 50}),
        (valid, {"total_tokens": 100}),
    ]

    extract_per_batch(batches, researcher=fake_researcher)

    # 두 번째 호출의 프롬프트에 clarification suffix 포함
    second_call_prompt = fake_researcher.call.call_args_list[1].kwargs["prompt"]
    assert "JSON 파싱에 실패" in second_call_prompt
    assert "유효한 JSON" in second_call_prompt
    # 첫 번째 호출에는 없음
    first_call_prompt = fake_researcher.call.call_args_list[0].kwargs["prompt"]
    assert "JSON 파싱에 실패" not in first_call_prompt


def test_parse_json_raises_aiupstream_on_quota_sentinel():
    """`_call_ai`가 'API 할당량 초과(429 Error)' sentinel을 반환하면 즉시 AIUpstreamError"""
    import pytest
    from src.trend_extractor import AIUpstreamError, extract_per_batch

    batches = _make_batches()
    fake_researcher = MagicMock()
    fake_researcher.call.return_value = ("API 할당량 초과(429 Error)", {})

    with pytest.raises(AIUpstreamError, match="API 할당량 초과"):
        extract_per_batch(batches, researcher=fake_researcher)

    # 재시도 없이 1회만 호출 (3회 재시도해서 quota 더 소진하지 않음)
    assert fake_researcher.call.call_count == 1


def test_parse_json_raises_aiupstream_on_generic_error_sentinel():
    """`_call_ai`가 '오류: ...' sentinel을 반환하면 즉시 AIUpstreamError"""
    import pytest
    from src.trend_extractor import AIUpstreamError, extract_per_batch

    batches = _make_batches()
    fake_researcher = MagicMock()
    fake_researcher.call.return_value = ("오류: 503 UNAVAILABLE 5회 재시도 모두 실패", {})

    with pytest.raises(AIUpstreamError, match="오류:"):
        extract_per_batch(batches, researcher=fake_researcher)

    assert fake_researcher.call.call_count == 1


def test_filter_indices_from_top3_removes_kr_indices():
    """코스피/코스닥/KOSPI 등은 종목 자리에서 제거됨"""
    from src.trend_extractor import _filter_indices_from_top3
    top3 = {
        "us_top3_sectors": [],
        "us_top3_stocks": [],
        "kr_top3_sectors": [],
        "kr_top3_stocks": [
            {"name": "삼성전자", "reason": "한뉴스 30개 중 1건"},
            {"name": "코스닥", "reason": "한뉴스 30개 중 9건"},  # 인덱스 — 제거되어야
            {"name": "코스피", "reason": "한뉴스 30개 중 9건"},  # 인덱스 — 제거되어야
        ],
    }
    result = _filter_indices_from_top3(top3)
    names = [e["name"] for e in result["kr_top3_stocks"]]
    assert "삼성전자" in names
    assert "코스닥" not in names
    assert "코스피" not in names


def test_filter_indices_from_top3_removes_us_indices():
    """S&P 500, Nasdaq, Dow 등 미국 인덱스 제거"""
    from src.trend_extractor import _filter_indices_from_top3
    top3 = {
        "us_top3_sectors": [],
        "us_top3_stocks": [
            {"name": "Nvidia", "reason": "..."},
            {"name": "S&P 500", "reason": "..."},  # 제거
            {"name": "Nasdaq", "reason": "..."},   # 제거
            {"name": "Dow Jones", "reason": "..."}, # 제거
            {"name": "QQQ", "reason": "..."},      # ETF — 제거
        ],
        "kr_top3_sectors": [],
        "kr_top3_stocks": [],
    }
    result = _filter_indices_from_top3(top3)
    names = [e["name"] for e in result["us_top3_stocks"]]
    assert names == ["Nvidia"]


def test_filter_indices_from_extraction_per_batch():
    """배치별 stocks·sectors에서도 인덱스 제거"""
    from src.trend_extractor import _filter_indices_from_extraction
    extraction = {
        "kr_news": {
            "stocks": [
                {"name": "삼성전자", "freq": 5, "refs": [1]},
                {"name": "코스피", "freq": 9, "refs": [2]},
            ],
            "sectors": [
                {"name": "반도체", "freq": 8, "refs": [1]},
                {"name": "KOSPI200", "freq": 5, "refs": [2]},  # sectors에 잘못 들어감 — 제거
            ],
        },
        "us_news": {
            "stocks": [{"name": "Nvidia", "freq": 5, "refs": [1]}],
            "sectors": [],
        },
        "us_community": {"stocks": [], "sectors": []},
        "kr_community": {"stocks": [], "sectors": []},
    }
    result = _filter_indices_from_extraction(extraction)
    kr_stock_names = [e["name"] for e in result["kr_news"]["stocks"]]
    kr_sector_names = [e["name"] for e in result["kr_news"]["sectors"]]
    assert "삼성전자" in kr_stock_names
    assert "코스피" not in kr_stock_names
    assert "반도체" in kr_sector_names
    assert "KOSPI200" not in kr_sector_names


def test_is_index_or_market_various_forms():
    """다양한 표기 인식 확인"""
    from src.trend_extractor import _is_index_or_market
    # 인덱스로 인식 (제거 대상)
    assert _is_index_or_market("코스피")
    assert _is_index_or_market("KOSDAQ")
    assert _is_index_or_market("Nasdaq")
    assert _is_index_or_market("S&P 500")
    assert _is_index_or_market("nasdaq composite")
    assert _is_index_or_market("VIX")
    assert _is_index_or_market("QQQ")
    assert _is_index_or_market("Wall Street")
    # 종목으로 인식 (유지)
    assert not _is_index_or_market("삼성전자")
    assert not _is_index_or_market("Nvidia")
    assert not _is_index_or_market("Apple")
    assert not _is_index_or_market("반도체")  # 섹터지만 인덱스 아님
    assert not _is_index_or_market("")


def test_enforce_min_freq_top3_filters_low_signal():
    """저빈도 항목(stocks < 10, sectors < 15)은 TOP3에서 제거"""
    from src.trend_extractor import _enforce_min_freq_top3
    top3 = {
        "us_top3_sectors": [
            {"name": "AI", "us_news_refs": list(range(20)), "us_community_refs": []},  # 20 → 유지
            {"name": "Energy", "us_news_refs": [1, 2], "us_community_refs": [3]},  # 3 → 제거
        ],
        "us_top3_stocks": [
            {"name": "Nvidia", "us_news_refs": list(range(15)), "us_community_refs": []},  # 15 → 유지
            {"name": "Critical Metals", "us_news_refs": [1], "us_community_refs": []},  # 1 → 제거
        ],
        "kr_top3_sectors": [
            {"name": "반도체", "kr_news_refs": list(range(20)), "kr_community_refs": []},  # 유지
            {"name": "AI 반도체", "kr_news_refs": [1], "kr_community_refs": []},  # 1 → 제거
        ],
        "kr_top3_stocks": [
            {"name": "삼성전자", "kr_news_refs": list(range(12)), "kr_community_refs": []},  # 12 → 유지
            {"name": "셀트리온", "kr_news_refs": [1, 2], "kr_community_refs": []},  # 2 → 제거
        ],
    }
    result = _enforce_min_freq_top3(top3)
    us_sector_names = [e["name"] for e in result["us_top3_sectors"]]
    us_stock_names = [e["name"] for e in result["us_top3_stocks"]]
    kr_sector_names = [e["name"] for e in result["kr_top3_sectors"]]
    kr_stock_names = [e["name"] for e in result["kr_top3_stocks"]]
    assert us_sector_names == ["AI"]
    assert us_stock_names == ["Nvidia"]
    assert kr_sector_names == ["반도체"]
    assert kr_stock_names == ["삼성전자"]

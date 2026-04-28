"""trend_formatter 테스트"""
from datetime import datetime, timezone, timedelta

from src.trend_formatter import format_us, format_kr


KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 4, 27, 7, 30, tzinfo=KST)


def _sample_top3():
    return {
        "us_top3_sectors": [
            {"name": "AI 인프라", "reason": "미뉴스 30개 중 8건, 미커뮤 30개 중 5건 [미뉴스#3,#7,#12,#15,#18,#22,#25,#29] [미커뮤#2,#9,#14,#21,#27]"},
            {"name": "반도체", "reason": "미뉴스 30개 중 6건 [미뉴스#1,#4,#8,#11,#16,#20]"},
            {"name": "클라우드", "reason": "미뉴스 30개 중 5건 [미뉴스#5,#9,#13,#17,#23]"},
        ],
        "us_top3_stocks": [
            {"name": "Nvidia", "reason": "미뉴스 30개 중 7건 [미뉴스#3,#7,#12,#15,#18,#22,#25]"},
            {"name": "Microsoft", "reason": "미커뮤 30개 중 4건 [미커뮤#2,#9,#14,#21]"},
            {"name": "Apple", "reason": "미뉴스 30개 중 3건 [미뉴스#4,#11,#19]"},
        ],
        "kr_top3_sectors": [
            {"name": "반도체", "reason": "한뉴스 30개 중 9건 [한뉴스#1,#3,#5,#7,#10,#12,#15,#18,#22]"},
            {"name": "2차전지", "reason": "한뉴스 30개 중 5건 [한뉴스#2,#8,#13,#17,#24]"},
            {"name": "AI", "reason": "한커뮤 30개 중 4건 [한커뮤#4,#9,#16,#23]"},
        ],
        "kr_top3_stocks": [
            {"name": "삼성전자", "reason": "한뉴스 30개 중 8건 [한뉴스#1,#3,#5,#7,#10,#12,#15,#18]"},
            {"name": "SK하이닉스", "reason": "한뉴스 30개 중 5건 [한뉴스#2,#8,#13,#17,#22]"},
            {"name": "LG에너지솔루션", "reason": "한뉴스 30개 중 3건 [한뉴스#4,#11,#19]"},
        ],
    }


def _sample_outlook():
    return {
        "us_sector_outlook": [
            {"name": "AI 인프라", "outlook": "AI 인프라 수요 가속이 [미뉴스#3] [미커뮤#2]에서 다뤄짐. 다만 밸류에이션 부담 우려가 [미뉴스#7]에서 언급됨. 데이터센터 전력 비용 이슈가 [미커뮤#9]에 등장."},
            {"name": "반도체", "outlook": "AI 칩 수요가 [미뉴스#1] [미뉴스#4]에서 거론됨. 사이클 우려가 [미뉴스#8]에 언급. 반대 시각은 수집된 텍스트에 부재"},
            {"name": "클라우드", "outlook": "AWS·Azure 매출 성장이 [미뉴스#5]에서 보도됨. 다만 비용 효율 압박이 [미뉴스#9]에 언급됨. 반대 시각은 수집된 텍스트에 부재"},
        ],
        "us_stock_outlook": [
            {"name": "Nvidia", "outlook": "AI GPU 수요가 [미뉴스#3]에서 다뤄짐. 경쟁사 대안이 [미뉴스#22]에 언급됨. 반대 시각은 수집된 텍스트에 부재"},
            {"name": "Microsoft", "outlook": "Copilot 매출이 [미커뮤#2]에서 거론됨. 비용 부담이 [미커뮤#9]에 언급. 반대 시각은 수집된 텍스트에 부재"},
            {"name": "Apple", "outlook": "iPhone 판매가 [미뉴스#4]에서 다뤄짐. 중국 시장 우려가 [미뉴스#11]에 언급됨. 반대 시각은 수집된 텍스트에 부재"},
        ],
        "kr_sector_outlook": [
            {"name": "반도체", "outlook": "HBM 수요가 [한뉴스#1] [한뉴스#3]에서 다뤄짐. 가격 협상 이슈가 [한뉴스#7]에 언급됨. 반대 시각은 수집된 텍스트에 부재"},
            {"name": "2차전지", "outlook": "전기차 수요 둔화가 [한뉴스#2] [한뉴스#8]에서 거론됨. 다만 ESS 수요는 [한뉴스#13]에 언급. 반대 시각이 [한뉴스#17]에 등장"},
            {"name": "AI", "outlook": "K-AI 정책이 [한커뮤#4]에서 다뤄짐. 수익성 우려가 [한커뮤#9]에 언급됨. 반대 시각은 수집된 텍스트에 부재"},
        ],
        "kr_stock_outlook": [
            {"name": "삼성전자", "outlook": "HBM 양산이 [한뉴스#1]에서 거론됨. 메모리 가격 하락 우려가 [한뉴스#7]에 언급됨. 반대 시각은 수집된 텍스트에 부재"},
            {"name": "SK하이닉스", "outlook": "Nvidia 공급이 [한뉴스#2]에서 보도됨. 수율 이슈가 [한뉴스#8]에 언급됨. 반대 시각은 수집된 텍스트에 부재"},
            {"name": "LG에너지솔루션", "outlook": "북미 수주가 [한뉴스#4]에서 다뤄짐. 마진 압박이 [한뉴스#11]에 언급됨. 반대 시각은 수집된 텍스트에 부재"},
        ],
    }


def test_format_us_contains_top3_sectors_and_stocks():
    msg = format_us(NOW, _sample_top3(), _sample_outlook(), counts={"us_news": 30, "us_community": 30}, verify_result={"ok": True, "missing": [], "total_refs": 50})
    assert "🇺🇸" in msg
    assert "AI 인프라" in msg
    assert "Nvidia" in msg
    assert "30개 중 8건" in msg


def test_format_us_excludes_index_brackets():
    """가독성을 위해 [라벨#N] 인덱스 블록이 메시지에 노출되지 않음"""
    msg = format_us(NOW, _sample_top3(), _sample_outlook(),
                    counts={"us_news": 30, "us_community": 30},
                    verify_result={"ok": True, "missing": [], "total_refs": 50})
    assert "[미뉴스#" not in msg
    assert "[미커뮤#" not in msg
    assert "[한뉴스#" not in msg
    assert "[한커뮤#" not in msg


def test_format_excludes_zero_count_segments():
    """'라벨 30개 중 0건'은 의미 없으므로 표기 제거"""
    top3 = {
        "us_top3_sectors": [{
            "name": "AI",
            "reason": "미뉴스 30개 중 9건, 미커뮤 30개 중 0건 [미뉴스#1,#2] [미커뮤#]",
        }],
        "us_top3_stocks": [],
        "kr_top3_sectors": [],
        "kr_top3_stocks": [],
    }
    outlook = {"us_sector_outlook": [{"name": "AI", "outlook": "내용"}], "us_stock_outlook": [],
               "kr_sector_outlook": [], "kr_stock_outlook": []}
    msg = format_us(NOW, top3, outlook,
                    counts={"us_news": 30, "us_community": 0},
                    verify_result={"ok": True, "missing": [], "total_refs": 2})
    assert "30개 중 0건" not in msg
    assert "9건" in msg  # 0건이 아닌 빈도는 그대로 유지


def test_format_header_hides_zero_count_source():
    """수집 헤더에서 0건 소스는 표기 생략"""
    top3 = {"us_top3_sectors": [], "us_top3_stocks": [],
            "kr_top3_sectors": [], "kr_top3_stocks": []}
    outlook = {"us_sector_outlook": [], "us_stock_outlook": [],
               "kr_sector_outlook": [], "kr_stock_outlook": []}
    msg = format_us(NOW, top3, outlook,
                    counts={"us_news": 30, "us_community": 0},
                    verify_result={"ok": True, "missing": [], "total_refs": 0})
    assert "미국 뉴스 30" in msg
    assert "미국 커뮤니티 0" not in msg


def test_format_no_disclaimer():
    """※ 본 리포트는 ... 투자 권유 문구 제거"""
    msg = format_us(NOW, _sample_top3(), _sample_outlook(),
                    counts={"us_news": 30, "us_community": 30},
                    verify_result={"ok": True, "missing": [], "total_refs": 50})
    assert "투자 권유" not in msg
    assert "수집된 텍스트만을" not in msg


def test_format_us_warns_on_verify_fail():
    msg = format_us(NOW, _sample_top3(), _sample_outlook(), counts={"us_news": 30, "us_community": 30}, verify_result={"ok": False, "missing": [("us_news", 99)], "total_refs": 50})
    assert "⚠️" in msg
    assert "검증 실패" in msg


def test_format_us_warns_on_partial_collection():
    """30개 미달 시 표기"""
    msg = format_us(NOW, _sample_top3(), _sample_outlook(), counts={"us_news": 22, "us_community": 30}, verify_result={"ok": True, "missing": [], "total_refs": 50})
    assert "22" in msg


def test_format_kr_contains_top3():
    msg = format_kr(NOW, _sample_top3(), _sample_outlook(), counts={"kr_news": 30, "kr_community": 30}, verify_result={"ok": True, "missing": [], "total_refs": 50})
    assert "🇰🇷" in msg
    assert "삼성전자" in msg
    assert "반도체" in msg


def test_format_us_falls_back_to_index_when_outlook_name_mismatches():
    """outlook의 name이 top3와 미세하게 달라도 인덱스로 매칭"""
    top3 = {
        "us_top3_sectors": [{"name": "AI 인프라", "reason": "..."}],
        "us_top3_stocks": [],
        "kr_top3_sectors": [],
        "kr_top3_stocks": [],
    }
    outlook = {
        "us_sector_outlook": [{"name": "AI 인프라 (AI Infra)", "outlook": "내용 [미뉴스#1]"}],
        "us_stock_outlook": [],
        "kr_sector_outlook": [],
        "kr_stock_outlook": [],
    }
    msg = format_us(NOW, top3, outlook,
                    counts={"us_news": 30, "us_community": 30},
                    verify_result={"ok": True, "missing": [], "total_refs": 1})
    assert "내용" in msg  # 인덱스 블록은 제거되지만 본문은 남음
    assert "(전망 누락)" not in msg


def test_format_messages_under_4096_chars_for_typical_input():
    msg_us = format_us(NOW, _sample_top3(), _sample_outlook(), counts={"us_news": 30, "us_community": 30}, verify_result={"ok": True, "missing": [], "total_refs": 50})
    msg_kr = format_kr(NOW, _sample_top3(), _sample_outlook(), counts={"kr_news": 30, "kr_community": 30}, verify_result={"ok": True, "missing": [], "total_refs": 50})
    assert len(msg_us) < 4096
    assert len(msg_kr) < 4096

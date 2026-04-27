"""트렌드 스캐너 텔레그램 메시지 포매터"""
from datetime import datetime
from typing import Dict


SEP = "━━━━━━━━━━━━━━━━━━━━━━━━━"
DISCLAIMER = "※ 본 리포트는 수집된 텍스트만을 근거로 합니다. 투자 권유가 아닙니다."


def _verify_warning(verify_result: Dict) -> str:
    if verify_result.get("ok", True):
        return ""
    n = len(verify_result.get("missing", []))
    return f"⚠️ 인덱스 검증 실패 {n}건\n"


def _format_section(title_emoji: str, title: str, top3_list, outlook_list) -> str:
    """공통 — TOP3 항목 3개 + 각 항목의 outlook을 결합"""
    lines = [f"{title_emoji} {title}"]
    outlook_by_name = {o["name"]: o["outlook"] for o in outlook_list}
    for i, entry in enumerate(top3_list, start=1):
        name = entry["name"]
        reason = entry["reason"]
        outlook = outlook_by_name.get(name, "(전망 누락)")
        lines.append(f"{i}. {name} — {reason}")
        lines.append(f"   {outlook}")
    return "\n".join(lines)


def format_us(
    now: datetime,
    top3: Dict,
    outlook: Dict,
    counts: Dict[str, int],
    verify_result: Dict,
) -> str:
    """미국 메시지 (~2000자)"""
    timestamp = now.strftime("%Y-%m-%d %H:%M KST")
    header = (
        f"🇺🇸 [미국] 트렌드 스캔 — {timestamp}\n"
        f"수집: 미국 뉴스 {counts.get('us_news', 0)} + 미국 커뮤니티 {counts.get('us_community', 0)} (최근 24h)\n"
    )
    warning = _verify_warning(verify_result)

    sectors = _format_section("📊", "TOP3 섹터", top3.get("us_top3_sectors", []), outlook.get("us_sector_outlook", []))
    stocks = _format_section("🏢", "TOP3 종목", top3.get("us_top3_stocks", []), outlook.get("us_stock_outlook", []))

    body = "\n".join([header + warning, SEP, sectors, "", SEP, stocks, "", SEP, DISCLAIMER])
    return body


def format_kr(
    now: datetime,
    top3: Dict,
    outlook: Dict,
    counts: Dict[str, int],
    verify_result: Dict,
) -> str:
    """한국 메시지 (~2000자)"""
    timestamp = now.strftime("%Y-%m-%d %H:%M KST")
    header = (
        f"🇰🇷 [한국] 트렌드 스캔 — {timestamp}\n"
        f"수집: 한국 뉴스 {counts.get('kr_news', 0)} + 한국 커뮤니티 {counts.get('kr_community', 0)} (최근 24h)\n"
    )
    warning = _verify_warning(verify_result)

    sectors = _format_section("📊", "TOP3 섹터", top3.get("kr_top3_sectors", []), outlook.get("kr_sector_outlook", []))
    stocks = _format_section("🏢", "TOP3 종목", top3.get("kr_top3_stocks", []), outlook.get("kr_stock_outlook", []))

    body = "\n".join([header + warning, SEP, sectors, "", SEP, stocks, "", SEP, DISCLAIMER])
    return body

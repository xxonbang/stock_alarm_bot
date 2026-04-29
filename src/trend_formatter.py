"""트렌드 스캐너 텔레그램 메시지 포매터"""
import re
from datetime import datetime
from typing import Dict


SEP = "━━━━━━━━━━━━━━━━━━━━━━━━━"

# 인덱스 블록 (단일 또는 묶음, 빈 형태도): [미뉴스#3] / [미뉴스#3,#7,#12] / [미커뮤#]
_INDEX_BLOCK_RE = re.compile(r"\s*\[(?:미뉴스|미커뮤|한뉴스|한커뮤)(?:#\d+,?)*\]\s*")
# "라벨 30개 중 0건" (콤마 포함 또는 단독)
_ZERO_COUNT_RE = re.compile(r",?\s*(?:미뉴스|미커뮤|한뉴스|한커뮤)\s*30개 중 0건\s*")


def _clean_reason(text: str) -> str:
    """LLM 생성 reason·outlook 텍스트 정리:
    - [라벨#...] 인덱스 블록 제거 (가독성)
    - '라벨 30개 중 0건' 표기 제거 (수집 0건 소스는 의미 없음)
    - 잔여 콤마·공백 정리
    """
    s = _INDEX_BLOCK_RE.sub(" ", text)
    s = _ZERO_COUNT_RE.sub("", s)
    s = re.sub(r",\s*,", ",", s)
    s = re.sub(r"^[\s,]+", "", s)
    s = re.sub(r"[\s,]+$", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _verify_warning(verify_result: Dict) -> str:
    if verify_result.get("ok", True):
        return ""
    n = len(verify_result.get("missing", []))
    return f"⚠️ 인덱스 검증 실패 {n}건\n"


def _format_section(title_emoji: str, title: str, top3_list, outlook_list) -> str:
    """공통 — TOP3 항목 3개 + 각 항목의 outlook을 결합

    인덱스 기반 페어링으로 LLM이 outlook의 name을 미세 변형해도 매칭 안전.
    fallback: name 매칭 실패 시 outlook_list[i]의 outlook 필드 사용.
    빈 TOP3 (저빈도 필터로 제거된 경우)는 약한 시그널 안내 표시.
    """
    lines = [f"{title_emoji} {title}"]
    if not top3_list:
        lines.append("(이번 라운드는 강한 시그널 부재 — 빈도 임계값 미달)")
        return "\n".join(lines)
    outlook_by_name = {o["name"]: o["outlook"] for o in outlook_list}
    for i, entry in enumerate(top3_list, start=1):
        name = entry["name"]
        reason = _clean_reason(entry.get("reason", ""))
        outlook = outlook_by_name.get(name)
        if outlook is None and i - 1 < len(outlook_list):
            outlook = outlook_list[i - 1].get("outlook", "(전망 누락)")
        if outlook is None:
            outlook = "(전망 누락)"
        outlook = _clean_reason(outlook)
        if reason:
            lines.append(f"{i}. {name} — {reason}")
        else:
            lines.append(f"{i}. {name}")
        lines.append(f"   {outlook}")
    return "\n".join(lines)


def _format_header(emoji: str, region: str, timestamp: str,
                   counts: Dict[str, int], news_key: str, comm_key: str,
                   news_label: str, comm_label: str) -> str:
    """수집 헤더 — 0건 소스는 표기 생략"""
    parts = []
    n = counts.get(news_key, 0)
    c = counts.get(comm_key, 0)
    if n > 0:
        parts.append(f"{news_label} {n}")
    if c > 0:
        parts.append(f"{comm_label} {c}")
    collected = " + ".join(parts) if parts else "수집 데이터 없음"
    return (
        f"{emoji} [{region}] 트렌드 스캔 — {timestamp}\n"
        f"수집: {collected} (최근 24h)\n"
    )


def format_us(
    now: datetime,
    top3: Dict,
    outlook: Dict,
    counts: Dict[str, int],
    verify_result: Dict,
) -> str:
    """미국 메시지"""
    timestamp = now.strftime("%Y-%m-%d %H:%M KST")
    header = _format_header(
        "🇺🇸", "미국", timestamp, counts,
        news_key="us_news", comm_key="us_community",
        news_label="미국 뉴스", comm_label="미국 커뮤니티",
    )
    warning = _verify_warning(verify_result)

    sectors = _format_section("📊", "TOP3 섹터", top3.get("us_top3_sectors", []), outlook.get("us_sector_outlook", []))
    stocks = _format_section("🏢", "TOP3 종목", top3.get("us_top3_stocks", []), outlook.get("us_stock_outlook", []))

    return "\n".join([header + warning, SEP, sectors, "", SEP, stocks])


def format_youtube(now: datetime, yt_result: Dict, video_count: int) -> str:
    """유튜브 트렌드 메시지"""
    timestamp = now.strftime("%Y-%m-%d %H:%M KST")
    header = (
        f"🎬 [유튜브 트렌드] — {timestamp}\n"
        f"수집: 한국 주식 유튜브 영상 {video_count}개 (최근 7일)\n"
    )

    def _fmt_section(emoji, title, entries):
        lines = [f"{emoji} {title}"]
        if not entries:
            lines.append("(데이터 없음)")
            return "\n".join(lines)
        for i, e in enumerate(entries[:3], start=1):
            name = e.get("name", "")
            freq = e.get("freq", 0)
            summary = _clean_reason(e.get("summary", ""))
            lines.append(f"{i}. {name} — {video_count}개 중 {freq}건 언급")
            lines.append(f"   {summary}")
        return "\n".join(lines)

    sectors = _fmt_section("📊", "TOP3 섹터", yt_result.get("top3_sectors", []))
    stocks = _fmt_section("🏢", "TOP3 종목", yt_result.get("top3_stocks", []))
    return "\n".join([header, SEP, sectors, "", SEP, stocks])


def format_kr(
    now: datetime,
    top3: Dict,
    outlook: Dict,
    counts: Dict[str, int],
    verify_result: Dict,
) -> str:
    """한국 메시지"""
    timestamp = now.strftime("%Y-%m-%d %H:%M KST")
    header = _format_header(
        "🇰🇷", "한국", timestamp, counts,
        news_key="kr_news", comm_key="kr_community",
        news_label="한국 뉴스", comm_label="한국 커뮤니티",
    )
    warning = _verify_warning(verify_result)

    sectors = _format_section("📊", "TOP3 섹터", top3.get("kr_top3_sectors", []), outlook.get("kr_sector_outlook", []))
    stocks = _format_section("🏢", "TOP3 종목", top3.get("kr_top3_stocks", []), outlook.get("kr_stock_outlook", []))

    return "\n".join([header + warning, SEP, sectors, "", SEP, stocks])

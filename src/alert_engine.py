"""
경보 판정 엔진
수집된 데이터를 기반으로 평시/경보/주간 모드를 결정하고
각 모드에 맞는 텔레그램 메시지를 생성

4모드 시스템:
- 장중 (intraday): 장중 수급 속보. AI 호출 없음.
- 평시 (normal): 짧은 현황 메시지. AI 호출 없음.
- 경보 (alert): 임계값 돌파 시. AI가 상황 해석.
- 주간 (weekly): 월요일 아침. 구조적 점검 + AI 분석.
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")


def _is_previous_day_data(supply: Dict) -> bool:
    """수급 데이터가 전일 기준인지 판별"""
    data_date = supply.get('data_date')
    if not data_date:
        return True  # 날짜 정보 없으면 전일로 간주 (안전한 기본값)
    today_str = datetime.now(KST).strftime('%Y-%m-%d')
    return data_date != today_str

# 경보 임계값
THRESHOLDS = {
    'vix_red': 25,
    'vix_yellow': 20,
    'vix_daily_change_pct': 20,
    'usdkrw_daily_change': 15,
    'us10y_red': 4.5,
    'us10y_daily_change': 0.10,
    'rsi_overbought_red': 80,
    'rsi_overbought_yellow': 70,
    'rsi_oversold_red': 25,
    'rsi_oversold_yellow': 30,
    'fear_greed_extreme_fear': 20,
    'fear_greed_extreme_greed': 80,
    'stock_daily_change_pct': 3.0,
}


def determine_mode(
    stock_results: List[Dict],
    macro_text: str,
    fear_greed_score: Optional[float] = None,
    vix_value: Optional[float] = None,
    usdkrw: Optional[float] = None,
    usdkrw_change: Optional[float] = None,
    us10y: Optional[float] = None,
    nq_change_pct: Optional[float] = None,
) -> Tuple[str, List[str]]:
    """
    리포트 모드 결정

    Returns:
        (mode, alerts)
        mode: 'normal', 'alert', 'weekly'
        alerts: 발동된 경보 사유 리스트
    """
    now = datetime.now(KST)
    is_monday_morning = now.weekday() == 0 and now.hour < 12

    alerts = []

    # VIX 체크
    if vix_value is not None:
        if vix_value >= THRESHOLDS['vix_red']:
            alerts.append(f"VIX {vix_value:.1f} (경계선 {THRESHOLDS['vix_red']} 돌파)")

    # 환율 체크
    if usdkrw_change is not None and abs(usdkrw_change) >= THRESHOLDS['usdkrw_daily_change']:
        direction = "상승" if usdkrw_change > 0 else "하락"
        alerts.append(f"USD/KRW {direction} {abs(usdkrw_change):.0f}원")

    # 미 10Y 금리 체크
    if us10y is not None and us10y >= THRESHOLDS['us10y_red']:
        alerts.append(f"미 10Y 금리 {us10y:.2f}% (경계선 {THRESHOLDS['us10y_red']}% 돌파)")

    # Fear&Greed 극단 체크
    if fear_greed_score is not None:
        if fear_greed_score <= THRESHOLDS['fear_greed_extreme_fear']:
            alerts.append(f"Fear&Greed {fear_greed_score:.0f} (극단적 공포)")
        elif fear_greed_score >= THRESHOLDS['fear_greed_extreme_greed']:
            alerts.append(f"Fear&Greed {fear_greed_score:.0f} (극단적 탐욕)")

    # 개별 종목 RSI/변동률 체크
    for result in stock_results:
        ticker = result.get('ticker', '')
        technical = result.get('technical', {})
        returns = result.get('returns', {})
        rsi = technical.get('rsi')
        daily_change = returns.get('1D')

        if rsi is not None:
            if rsi >= THRESHOLDS['rsi_overbought_red']:
                alerts.append(f"{ticker} RSI {rsi:.0f} 극단적 과열")
            elif rsi <= THRESHOLDS['rsi_oversold_red']:
                alerts.append(f"{ticker} RSI {rsi:.0f} 극단적 과매도")

        if daily_change is not None and abs(daily_change) >= THRESHOLDS['stock_daily_change_pct']:
            direction = "급등" if daily_change > 0 else "급락"
            alerts.append(f"{ticker} {direction} {daily_change:+.1f}%")

    # 모드 결정
    if is_monday_morning:
        return 'weekly', alerts
    elif alerts:
        return 'alert', alerts
    else:
        return 'normal', alerts


def _get_market_regime(
    fear_greed_score: Optional[float],
    vix_value: Optional[float],
    nq_change_pct: Optional[float],
) -> Tuple[str, str]:
    """
    시장 체제 판단

    Returns:
        (체제명, 이모지)
    """
    score = 0

    if fear_greed_score is not None:
        if fear_greed_score >= 60:
            score += 2
        elif fear_greed_score >= 40:
            score += 1
        elif fear_greed_score >= 25:
            score -= 1
        else:
            score -= 2

    if vix_value is not None:
        if vix_value < 15:
            score += 2
        elif vix_value < 20:
            score += 1
        elif vix_value < 25:
            score -= 1
        else:
            score -= 2

    if nq_change_pct is not None:
        if nq_change_pct >= 0.5:
            score += 1
        elif nq_change_pct <= -1.0:
            score -= 1

    if score >= 3:
        return "적극 공격", "🟢"
    elif score >= 1:
        return "선별 매수", "🔵"
    elif score >= -1:
        return "약세 경계", "⚠️"
    else:
        return "방어 모드", "🔴"


def generate_normal_message(
    stock_results: List[Dict],
    macro_text: str,
    fear_greed_score: Optional[float] = None,
    vix_value: Optional[float] = None,
    usdkrw: Optional[float] = None,
    us10y: Optional[float] = None,
    nq_change_pct: Optional[float] = None,
    is_evening: bool = False,
) -> List[str]:
    """
    평시 메시지 생성 (1개 메시지, AI 호출 없음)
    친절하고 상세한 톤으로 작성
    """
    now = datetime.now(KST)
    date_str = now.strftime("%Y.%m.%d")
    weekday_map = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}
    weekday = weekday_map.get(now.weekday(), "")
    time_str = now.strftime("%H:%M")

    regime_name, regime_emoji = _get_market_regime(fear_greed_score, vix_value, nq_change_pct)

    lines = []
    lines.append(f"📅 {date_str} ({weekday}) {time_str} KST")
    lines.append("")

    if is_evening:
        lines.append(f"{regime_emoji} <b>장 마감 리포트</b>")
    else:
        lines.append(f"{regime_emoji} <b>오전 리포트</b> — 시장 {regime_name}")
    lines.append("")

    # 매크로 핵심 지표
    macro_parts = []
    if usdkrw is not None:
        macro_parts.append(f"환율 {usdkrw:,.0f}원")
    if vix_value is not None:
        macro_parts.append(f"VIX {vix_value:.1f}")
    if us10y is not None:
        macro_parts.append(f"미10Y {us10y:.2f}%")
    if fear_greed_score is not None:
        fg_label = _fear_greed_label(fear_greed_score)
        macro_parts.append(f"F&G {fear_greed_score:.0f}({fg_label})")
    if nq_change_pct is not None:
        nq_emoji = "🔴" if nq_change_pct >= 0 else "🔵"
        macro_parts.append(f"NQ {nq_emoji}{nq_change_pct:+.1f}%")

    if macro_parts:
        lines.append(" | ".join(macro_parts))
        lines.append("")

    # SK하이닉스 상세 현황
    for result in stock_results:
        ticker = result.get('ticker', '')
        if '000660' not in ticker:
            continue

        from config.ticker_names import get_ticker_name
        name = get_ticker_name(ticker) or "SK하이닉스"
        price = result.get('current_price', 0)
        returns = result.get('returns', {})
        technical = result.get('technical', {})
        supply = result.get('supply_demand_1d', {})

        lines.append(f"━━ <b>{name}(000660)</b> 상세 현황 ━━")
        lines.append("")

        # 가격 + 등락
        daily = returns.get('1D')
        if isinstance(price, (int, float)):
            price_str = f"{price:,.0f}원"
        else:
            price_str = str(price)

        if daily is not None:
            d_emoji = "🔴" if daily >= 0 else "🔵"
            lines.append(f"💰 현재가: <b>{price_str}</b> ({d_emoji}{daily:+.2f}%)")
        else:
            lines.append(f"💰 현재가: <b>{price_str}</b>")

        # 기간별 수익률
        period_parts = []
        for code, label in [('1W', '1주'), ('1M', '1개월'), ('3M', '3개월')]:
            val = returns.get(code)
            if val is not None:
                sign = "+" if val >= 0 else ""
                period_parts.append(f"{label} {sign}{val:.1f}%")
        if period_parts:
            lines.append(f"📊 수익률: {' | '.join(period_parts)}")

        # RSI + 기술적 상태
        rsi = technical.get('rsi')
        pullback = technical.get('pullback_status', '')
        macd = technical.get('macd', {})

        tech_parts = []
        if rsi is not None:
            if rsi >= 70:
                tech_parts.append(f"RSI <b>{rsi:.0f}</b> ⚠️과열 주의")
            elif rsi <= 30:
                tech_parts.append(f"RSI <b>{rsi:.0f}</b> ❄️과매도 → 반등 기회")
            else:
                tech_parts.append(f"RSI <b>{rsi:.0f}</b> 정상")

        if pullback and '눌림목' in pullback:
            tech_parts.append("✅ 눌림목 감지 → 매수 기회")

        if macd and isinstance(macd, dict):
            trend = macd.get('trend', '')
            if trend:
                tech_parts.append(f"MACD {trend}")

        if tech_parts:
            lines.append(f"📈 기술지표: {' | '.join(tech_parts)}")

        # 수급 (외국인/기관) — 전일 데이터는 표시하지 않음
        foreign = supply.get('foreign')
        institutional = supply.get('institutional')
        if (foreign is not None or institutional is not None) and not _is_previous_day_data(supply):
            sup_parts = []
            if foreign is not None:
                f_sign = "+" if foreign >= 0 else ""
                sup_parts.append(f"외국인 {f_sign}{foreign:.0f}만주")
            if institutional is not None:
                i_sign = "+" if institutional >= 0 else ""
                sup_parts.append(f"기관 {i_sign}{institutional:.0f}만주")

            if (foreign is not None and institutional is not None
                    and round(foreign) > 0 and round(institutional) > 0):
                sup_parts.append("🔥 <b>쌍끌이!</b>")
            elif (foreign is not None and institutional is not None
                    and round(foreign) < 0 and round(institutional) < 0):
                sup_parts.append("⚠️ 동반 매도")

            lines.append(f"🏦 수급: {' | '.join(sup_parts)}")

        lines.append("")

    # 종합 판단
    if not is_evening:
        lines.append("💡 특이사항 없는 하루입니다. 편안하게 지켜보셔도 됩니다.")
    else:
        lines.append("💡 오늘 하루 수고하셨습니다. 내일도 좋은 장이 되길 바랍니다.")

    return ["\n".join(lines)]


def generate_alert_messages(
    stock_results: List[Dict],
    alerts: List[str],
    macro_text: str,
    ai_insight: str = "",
    fear_greed_score: Optional[float] = None,
    vix_value: Optional[float] = None,
    usdkrw: Optional[float] = None,
    us10y: Optional[float] = None,
    nq_change_pct: Optional[float] = None,
    is_evening: bool = False,
) -> List[str]:
    """
    경보 메시지 생성 (2개 메시지)
    메시지1: 경보 상황 + 종목 상세
    메시지2: AI 인사이트 + 행동 옵션
    """
    now = datetime.now(KST)
    date_str = now.strftime("%Y.%m.%d")
    weekday_map = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}
    weekday = weekday_map.get(now.weekday(), "")
    time_str = now.strftime("%H:%M")

    # 메시지 1: 경보 상황
    msg1_lines = []
    msg1_lines.append(f"📅 {date_str} ({weekday}) {time_str} KST")
    msg1_lines.append("")
    msg1_lines.append("🔴 <b>경보 발생</b>")
    msg1_lines.append("")

    msg1_lines.append("━━ 무슨 일이 생겼나요? ━━")
    msg1_lines.append("")
    for alert in alerts:
        msg1_lines.append(f"⚠️ {alert}")
    msg1_lines.append("")

    # 매크로 현황
    macro_parts = []
    if usdkrw is not None:
        macro_parts.append(f"환율 {usdkrw:,.0f}원")
    if vix_value is not None:
        macro_parts.append(f"VIX {vix_value:.1f}")
    if us10y is not None:
        macro_parts.append(f"미10Y {us10y:.2f}%")
    if fear_greed_score is not None:
        fg_label = _fear_greed_label(fear_greed_score)
        macro_parts.append(f"F&G {fear_greed_score:.0f}({fg_label})")
    if nq_change_pct is not None:
        nq_emoji = "🔴" if nq_change_pct >= 0 else "🔵"
        macro_parts.append(f"NQ {nq_emoji}{nq_change_pct:+.1f}%")

    if macro_parts:
        msg1_lines.append(" | ".join(macro_parts))
        msg1_lines.append("")

    # SK하이닉스 상세
    for result in stock_results:
        ticker = result.get('ticker', '')
        if '000660' not in ticker:
            continue

        from config.ticker_names import get_ticker_name
        name = get_ticker_name(ticker) or "SK하이닉스"
        price = result.get('current_price', 0)
        returns = result.get('returns', {})
        technical = result.get('technical', {})
        supply = result.get('supply_demand_1d', {})

        msg1_lines.append(f"━━ <b>{name}(000660)</b> 현황 ━━")
        msg1_lines.append("")

        daily = returns.get('1D')
        if isinstance(price, (int, float)):
            price_str = f"{price:,.0f}원"
            if daily is not None:
                d_emoji = "🔴" if daily >= 0 else "🔵"
                msg1_lines.append(f"💰 <b>{price_str}</b> ({d_emoji}{daily:+.2f}%)")

        # 기간별
        for code, label in [('1W', '1주'), ('1M', '1개월'), ('3M', '3개월')]:
            val = returns.get(code)
            if val is not None:
                msg1_lines.append(f"  {label}: {val:+.1f}%")

        rsi = technical.get('rsi')
        if rsi is not None:
            msg1_lines.append(f"  RSI: {rsi:.0f}")

        foreign = supply.get('foreign')
        institutional = supply.get('institutional')
        if (foreign is not None or institutional is not None) and not _is_previous_day_data(supply):
            if foreign is not None:
                msg1_lines.append(f"  외국인: {foreign:+.0f}만주")
            if institutional is not None:
                msg1_lines.append(f"  기관: {institutional:+.0f}만주")

        msg1_lines.append("")

    msg1_lines.append("💡 아래 AI 분석 메시지에서 구체적인 판단과 행동 옵션을 확인하세요.")

    # 메시지 2: AI 인사이트
    msg2_lines = []
    if ai_insight:
        msg2_lines.append("<b>🤖 AI 상황 분석</b>")
        msg2_lines.append("")
        msg2_lines.append(ai_insight)
    else:
        msg2_lines.append("<b>🤖 AI 상황 분석</b>")
        msg2_lines.append("")
        msg2_lines.append("AI 분석을 생성하지 못했습니다.")
        msg2_lines.append("위 경보 내용을 참고하여 판단해 주세요.")

    messages = ["\n".join(msg1_lines)]
    if msg2_lines:
        messages.append("\n".join(msg2_lines))

    return messages


def generate_weekly_messages(
    stock_results: List[Dict],
    macro_text: str,
    ai_detailed: str = "",
    theme_text: str = "",
    signal_text: str = "",
    fear_greed_score: Optional[float] = None,
    vix_value: Optional[float] = None,
    usdkrw: Optional[float] = None,
    us10y: Optional[float] = None,
    nq_change_pct: Optional[float] = None,
) -> List[str]:
    """
    주간 리뷰 메시지 생성 (2~3개 메시지, 월요일 아침)
    """
    now = datetime.now(KST)
    date_str = now.strftime("%Y.%m.%d")
    weekday_map = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}
    weekday = weekday_map.get(now.weekday(), "")
    time_str = now.strftime("%H:%M")

    # 메시지 1: 주간 점검 + SK하이닉스
    msg1_lines = []
    msg1_lines.append(f"📅 {date_str} ({weekday}) {time_str} KST")
    msg1_lines.append("")
    msg1_lines.append("📋 <b>주간 점검 리포트</b>")
    msg1_lines.append("")
    msg1_lines.append("한 주의 시작입니다. SK하이닉스와 반도체 업종의 흐름을 꼼꼼히 점검해볼게요.")
    msg1_lines.append("")

    # 매크로 주간 추이
    msg1_lines.append("━━ 핵심 변수 현황 ━━")
    msg1_lines.append("")
    if usdkrw is not None:
        msg1_lines.append(f"  환율 USD/KRW: {usdkrw:,.0f}원")
    if us10y is not None:
        msg1_lines.append(f"  미국 10년물 금리: {us10y:.2f}%")
    if vix_value is not None:
        msg1_lines.append(f"  VIX 변동성: {vix_value:.1f}")
    if fear_greed_score is not None:
        fg_label = _fear_greed_label(fear_greed_score)
        msg1_lines.append(f"  Fear&Greed: {fear_greed_score:.0f} ({fg_label})")
    if nq_change_pct is not None:
        msg1_lines.append(f"  나스닥 선물: {nq_change_pct:+.1f}%")
    msg1_lines.append("")

    # SK하이닉스 상세
    for result in stock_results:
        ticker = result.get('ticker', '')
        if '000660' not in ticker:
            continue

        from config.ticker_names import get_ticker_name
        name = get_ticker_name(ticker) or "SK하이닉스"
        price = result.get('current_price', 0)
        returns = result.get('returns', {})
        technical = result.get('technical', {})
        supply = result.get('supply_demand_1d', {})

        msg1_lines.append(f"━━ <b>{name}(000660)</b> 주간 점검 ━━")
        msg1_lines.append("")

        if isinstance(price, (int, float)):
            msg1_lines.append(f"💰 현재가: <b>{price:,.0f}원</b>")

        for code, label in [('1D', '전일'), ('1W', '1주'), ('1M', '1개월'), ('3M', '3개월'), ('6M', '6개월')]:
            val = returns.get(code)
            if val is not None:
                msg1_lines.append(f"  {label} 수익률: {val:+.1f}%")

        rsi = technical.get('rsi')
        if rsi is not None:
            if rsi >= 70:
                msg1_lines.append(f"  RSI: {rsi:.0f} ⚠️ 과열 구간입니다. 추가 매수는 신중하게.")
            elif rsi <= 30:
                msg1_lines.append(f"  RSI: {rsi:.0f} ❄️ 과매도 구간입니다. 반등 기회를 노려볼 수 있어요.")
            else:
                msg1_lines.append(f"  RSI: {rsi:.0f} ✅ 정상 범위")

        pullback = technical.get('pullback_status', '')
        if pullback and '눌림목' in pullback:
            msg1_lines.append("  ✅ 눌림목 감지: 건강한 조정 구간, 분할매수 고려 가능")

        foreign = supply.get('foreign')
        institutional = supply.get('institutional')
        if (foreign is not None or institutional is not None) and not _is_previous_day_data(supply):
            msg1_lines.append("")
            msg1_lines.append("  수급 현황:")
            if foreign is not None:
                msg1_lines.append(f"    외국인: {foreign:+.0f}만주")
            if institutional is not None:
                msg1_lines.append(f"    기관: {institutional:+.0f}만주")

    msg1_lines.append("")

    # 메시지 2: 테마 + 시그널 + AI 분석
    msg2_lines = []
    msg2_lines.append("━━ 🎯 이번 주 시장 테마 & AI 시그널 ━━")
    msg2_lines.append("")

    if theme_text:
        msg2_lines.append("<b>테마 예측 (theme_analysis)</b>")
        # 간결하게 요약
        for line in theme_text.split("\n"):
            if line.startswith("["):
                continue
            if line.strip():
                msg2_lines.append(line)
        msg2_lines.append("")

    if signal_text:
        msg2_lines.append("<b>AI 교차검증 시그널 (signal_analysis)</b>")
        for line in signal_text.split("\n"):
            if line.startswith("["):
                continue
            if line.strip():
                msg2_lines.append(line)
        msg2_lines.append("")

    if ai_detailed:
        msg2_lines.append("━━ 🤖 AI 주간 분석 ━━")
        msg2_lines.append("")
        msg2_lines.append(ai_detailed)

    if not any([theme_text, signal_text, ai_detailed]):
        msg2_lines.append("이번 주 크로스 프로젝트 데이터가 아직 없습니다.")
        msg2_lines.append("theme_analysis, signal_analysis 실행 후 다시 확인해 주세요.")

    messages = ["\n".join(msg1_lines)]
    if msg2_lines:
        messages.append("\n".join(msg2_lines))

    return messages


def generate_intraday_message(intraday_data: Dict) -> List[str]:
    """
    장중 수급 속보 메시지 생성 (1개 메시지, AI 호출 없음)

    Args:
        intraday_data: cross_project_data.get_intraday_investor_data()의 반환값
    """
    now = datetime.now(KST)
    date_str = now.strftime("%Y.%m.%d")
    weekday_map = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}
    weekday = weekday_map.get(now.weekday(), "")
    time_str = now.strftime("%H:%M")

    data_time = intraday_data.get("time", "")
    data_date = intraday_data.get("date", "")
    stocks = intraday_data.get("stocks", {})
    prev_stocks = intraday_data.get("prev_stocks", {})
    prev_time = intraday_data.get("prev_time")

    lines = []
    lines.append(f"📅 {date_str} ({weekday}) {time_str} KST")
    lines.append("")
    lines.append(f"📊 <b>장중 수급 속보</b> ({data_time} 기준)")
    lines.append("")

    for code, info in stocks.items():
        name = info.get("name", code)
        price = info.get("current_price")
        change_rate = info.get("change_rate")
        foreign = info.get("foreign_net")
        institution = info.get("institution_net")
        program = info.get("program_net")

        lines.append(f"━━ <b>{name}({code})</b> ━━")
        lines.append("")

        # 현재가 + 등락률
        if price is not None:
            price_str = f"{price:,.0f}원"
            if change_rate is not None:
                cr_emoji = "🔴" if change_rate >= 0 else "🔵"
                lines.append(f"💰 현재가: <b>{price_str}</b> ({cr_emoji}{change_rate:+.2f}%)")
            else:
                lines.append(f"💰 현재가: <b>{price_str}</b>")

        # 수급 현황
        lines.append("")
        lines.append("🏦 <b>수급 현황</b> (장중 추정치)")

        if foreign is not None:
            f_sign = "+" if foreign >= 0 else ""
            f_man = foreign / 10000  # 주 → 만주
            f_emoji = "📈" if foreign > 0 else "📉" if foreign < 0 else "➖"
            lines.append(f"  {f_emoji} 외국인: <b>{f_sign}{f_man:,.1f}만주</b>")

        if institution is not None:
            i_sign = "+" if institution >= 0 else ""
            i_man = institution / 10000
            i_emoji = "📈" if institution > 0 else "📉" if institution < 0 else "➖"
            lines.append(f"  {i_emoji} 기관: <b>{i_sign}{i_man:,.1f}만주</b>")

        if program is not None:
            p_sign = "+" if program >= 0 else ""
            p_man = program / 10000
            lines.append(f"  🤖 프로그램: {p_sign}{p_man:,.1f}만주")

        # 쌍끌이 판단
        if foreign is not None and institution is not None:
            if foreign > 0 and institution > 0:
                lines.append("")
                lines.append("  🔥 <b>외국인+기관 동시 매수 중!</b> (쌍끌이)")
            elif foreign < 0 and institution < 0:
                lines.append("")
                lines.append("  ⚠️ 외국인+기관 동시 매도 중")

        # 이전 라운드 대비 변화 (추이)
        prev = prev_stocks.get(code)
        if prev and prev_time:
            lines.append("")
            lines.append(f"📈 <b>추이</b> ({prev_time} → {data_time})")

            changes = []
            if foreign is not None and prev.get("foreign_net") is not None:
                f_diff = (foreign - prev["foreign_net"]) / 10000
                f_dir = "매수 증가 📈" if f_diff > 0 else "매도 증가 📉" if f_diff < 0 else "변동 없음"
                changes.append(f"  외국인: {f_dir} ({f_diff:+,.1f}만주)")

            if institution is not None and prev.get("institution_net") is not None:
                i_diff = (institution - prev["institution_net"]) / 10000
                i_dir = "매수 증가 📈" if i_diff > 0 else "매도 증가 📉" if i_diff < 0 else "변동 없음"
                changes.append(f"  기관: {i_dir} ({i_diff:+,.1f}만주)")

            if prev.get("current_price") is not None and price is not None:
                p_diff = price - prev["current_price"]
                p_pct = (p_diff / prev["current_price"]) * 100 if prev["current_price"] else 0
                changes.append(f"  가격: {price:,.0f}원 ({p_pct:+.2f}%)")

            for c in changes:
                lines.append(c)

        lines.append("")

    # 마무리 멘트
    lines.append("💡 장중 추정치이며, 확정 데이터는 장 마감 후 저녁 리포트에서 확인하실 수 있습니다.")

    return ["\n".join(lines)]


def _fear_greed_label(score: float) -> str:
    """Fear&Greed 점수를 한글 라벨로 변환"""
    if score <= 20:
        return "극단적 공포"
    elif score <= 40:
        return "공포"
    elif score <= 60:
        return "중립"
    elif score <= 80:
        return "탐욕"
    else:
        return "극단적 탐욕"

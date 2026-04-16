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


# 관찰·행동 템플릿 (regime × RSI level)
_OBSERVATION_TEMPLATES = {
    ("적극 공격", "high"): "단기 과열 주의. 급등 시 분할 익절 검토.",
    ("적극 공격", "mid"): "상승 추세 건재. 눌림 시 추가 진입 가능.",
    ("적극 공격", "low"): "과매도 구간에서 시장 강세. 반등 기대.",
    ("선별 매수", "high"): "RSI 높은 편. 추격 매수 자제, 보유 유지.",
    ("선별 매수", "mid"): "중립 구간. 기준 철회 매도세 없으면 보유 유지.",
    ("선별 매수", "low"): "과매도 접근. 분할매수 검토 가능.",
    ("약세 경계", "high"): "약세장 과열. 단기 반락 가능성 높음.",
    ("약세 경계", "mid"): "방어 우선. 추가 진입은 F&G 반등 후.",
    ("약세 경계", "low"): "공포 구간. 현금 비중 유지, 역발상 진입은 신중히.",
    ("방어 모드", "high"): "극단 변동. 포지션 축소 우선.",
    ("방어 모드", "mid"): "불확실성 높음. 관망 유지.",
    ("방어 모드", "low"): "극단적 공포. 장기 관점 분할매수 대기.",
}


def _get_rsi_level(stock_results: List[Dict]) -> str:
    """stock_results의 평균 RSI 레벨"""
    rsis = [r.get('technical', {}).get('rsi') for r in stock_results]
    rsis = [r for r in rsis if r is not None]
    if not rsis:
        return "mid"
    avg = sum(rsis) / len(rsis)
    if avg >= 65:
        return "high"
    elif avg <= 35:
        return "low"
    return "mid"


def _generate_summary_line(stock_results: List[Dict]) -> str:
    """종목별 핵심 시그널 1줄 요약"""
    from config.ticker_names import get_ticker_name
    parts = []
    for r in stock_results:
        ticker = r.get('ticker', '')
        name = get_ticker_name(ticker) or ticker
        short_name = name[:4] if len(name) > 4 else name

        tech = r.get('technical', {})
        rsi = tech.get('rsi')
        supply = r.get('supply_demand_1d', {})
        foreign = supply.get('foreign')
        daily = r.get('returns', {}).get('1D')

        signals = []
        if rsi is not None:
            if rsi >= 70:
                signals.append(f"RSI {rsi:.0f}(과열)")
            elif rsi <= 30:
                signals.append(f"RSI {rsi:.0f}(과매도)")
            else:
                signals.append(f"RSI {rsi:.0f}")

        if foreign is not None and not _is_previous_day_data(supply):
            f_dir = "순매수" if foreign > 0 else "순매도"
            signals.append(f"외인 {f_dir}")

        if daily is not None and abs(daily) >= 1.0:
            signals.append(f"{daily:+.1f}%")

        if signals:
            parts.append(f"{short_name} {' · '.join(signals)}")

    if not parts:
        return "주요 변동 없음"
    return ", ".join(parts)


def _generate_headline(
    stock_results: List[Dict],
    regime_emoji: str,
    usdkrw: Optional[float] = None,
    vix_value: Optional[float] = None,
    us10y: Optional[float] = None,
) -> str:
    """동적 헤드라인 (텔레그램 peek에 보이는 첫 줄)"""
    from config.ticker_names import get_ticker_name
    candidates = []

    for r in stock_results:
        ticker = r.get('ticker', '')
        name = get_ticker_name(ticker) or ticker
        short = name[:4] if len(name) > 4 else name
        tech = r.get('technical', {})
        rsi = tech.get('rsi')
        supply = r.get('supply_demand_1d', {})
        daily = r.get('returns', {}).get('1D')
        foreign = supply.get('foreign')
        institutional = supply.get('institutional')

        if rsi is not None:
            if rsi >= 65:
                candidates.append((abs(rsi - 50), f"{short} RSI {rsi:.0f}(과열 주의)"))
            elif rsi <= 35:
                candidates.append((abs(rsi - 50), f"{short} RSI {rsi:.0f}(과매도)"))

        if daily is not None and abs(daily) >= 1.5:
            candidates.append((abs(daily) * 5, f"{short} {daily:+.1f}%"))

        if foreign is not None and not _is_previous_day_data(supply):
            if abs(foreign) >= 5:
                f_dir = "외인 순매수" if foreign > 0 else "외인 순매도"
                candidates.append((abs(foreign), f"{short} {f_dir} {abs(foreign):.0f}만주"))

        if (foreign is not None and institutional is not None
                and not _is_previous_day_data(supply)
                and round(foreign) > 0 and round(institutional) > 0):
            candidates.append((30, f"{short} 외인+기관 쌍끌이"))

    if vix_value is not None and vix_value >= 20:
        candidates.append((vix_value - 15, f"VIX {vix_value:.1f}"))
    if us10y is not None and us10y >= 4.3:
        candidates.append((10, f"미10Y {us10y:.2f}%"))

    candidates.sort(key=lambda x: x[0], reverse=True)

    if candidates:
        top = [c[1] for c in candidates[:2]]
        return f"{regime_emoji} {' | '.join(top)}"

    # fallback: 첫 종목 현재가
    if stock_results:
        first = stock_results[0]
        name = get_ticker_name(first.get('ticker', '')) or first.get('ticker', '')
        price = first.get('current_price', 0)
        if isinstance(price, (int, float)):
            return f"{regime_emoji} {name} {price:,.0f}원"

    return f"{regime_emoji} 시장 동향"


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

    # 동적 헤드라인 (텔레그램 peek에 보이는 첫 줄)
    if is_evening:
        headline = f"{regime_emoji} <b>장 마감 리포트</b>"
    else:
        headline = _generate_headline(
            stock_results, regime_emoji,
            usdkrw=usdkrw, vix_value=vix_value, us10y=us10y,
        )
    lines.append(headline)
    lines.append("")
    lines.append(f"📅 {date_str} ({weekday}) {time_str} — 시장 {regime_name}")
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

    # 종목별 상세 현황
    from config.ticker_names import get_ticker_name
    for result in stock_results:
        ticker = result.get('ticker', '')
        if not ticker:
            continue

        name = get_ticker_name(ticker) or ticker
        ticker_code = ticker.split('.')[0]
        price = result.get('current_price', 0)
        returns = result.get('returns', {})
        technical = result.get('technical', {})
        supply = result.get('supply_demand_1d', {})

        lines.append(f"━━ <b>{name}({ticker_code})</b> 상세 현황 ━━")
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

        # 볼린저/골든크로스/거래량 (이상 징후만)
        bollinger = technical.get('bollinger')
        bl = _format_bollinger_line(bollinger, mode='normal')
        if bl:
            lines.append(bl)

        gdc = technical.get('golden_dead_cross')
        gl = _format_golden_dead_cross_line(gdc, mode='normal')
        if gl:
            lines.append(gl)

        vs = technical.get('volume_spike')
        vl = _format_volume_spike_line(vs, mode='normal')
        if vl:
            lines.append(vl)

        # 수급 (외국인/기관/프로그램) — 전일 데이터는 표시하지 않음
        foreign = supply.get('foreign')
        institutional = supply.get('institutional')
        program = supply.get('program')
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

            if program is not None:
                p_sign = "+" if program >= 0 else ""
                lines.append(f"💻 프로그램: {p_sign}{program:.0f}만주")

        # 공매도 (값이 있을 때만)
        short_selling = result.get('short_selling')
        sl = _format_short_selling_line(short_selling)
        if sl:
            lines.append(sl)

        # 포트폴리오 수익
        pl = _format_portfolio_line(ticker, price)
        if pl:
            lines.append(pl)

        # 밸류에이션 (값이 있을 때만)
        valuation = result.get('valuation')
        val_l = _format_valuation_line(valuation)
        if val_l:
            lines.append(val_l)

        # 리스크 (값이 있을 때만)
        risk_metrics = result.get('risk_metrics')
        rl = _format_risk_line(risk_metrics)
        if rl:
            lines.append(rl)

        lines.append("")

    # 데이터 요약 + 관찰·행동
    summary = _generate_summary_line(stock_results)
    lines.append(f"📌 {summary}")

    observation = _OBSERVATION_TEMPLATES.get(
        (regime_name, _get_rsi_level(stock_results)),
        "시장 상황을 지켜보며 기존 전략 유지.",
    )
    if is_evening:
        lines.append(f"🔎 {observation} 오늘 하루 수고하셨습니다.")
    else:
        lines.append(f"🔎 {observation}")

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

    # 종목별 상세
    from config.ticker_names import get_ticker_name
    for result in stock_results:
        ticker = result.get('ticker', '')
        if not ticker:
            continue

        name = get_ticker_name(ticker) or ticker
        ticker_code = ticker.split('.')[0]
        price = result.get('current_price', 0)
        returns = result.get('returns', {})
        technical = result.get('technical', {})
        supply = result.get('supply_demand_1d', {})

        msg1_lines.append(f"━━ <b>{name}({ticker_code})</b> 현황 ━━")
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
        macd = technical.get('macd', {})
        tech_parts = []
        if rsi is not None:
            tech_parts.append(f"RSI {rsi:.0f}")
        if macd and isinstance(macd, dict):
            trend = macd.get('trend', '')
            if trend:
                tech_parts.append(f"MACD {trend}")
        if tech_parts:
            msg1_lines.append(f"  📈 기술지표: {' | '.join(tech_parts)}")

        # 볼린저/골든크로스/거래량/스토캐스틱/OBV/ATR (상세)
        bollinger = technical.get('bollinger')
        bl = _format_bollinger_line(bollinger, mode='normal')
        if bl:
            msg1_lines.append(bl)

        gdc = technical.get('golden_dead_cross')
        gl = _format_golden_dead_cross_line(gdc, mode='normal')
        if gl:
            msg1_lines.append(gl)

        vs = technical.get('volume_spike')
        vl = _format_volume_spike_line(vs, mode='normal')
        if vl:
            msg1_lines.append(vl)

        stoch = technical.get('stochastic')
        stl = _format_stochastic_line(stoch)
        if stl:
            msg1_lines.append(stl)

        obv = technical.get('obv')
        ol = _format_obv_line(obv)
        if ol:
            msg1_lines.append(ol)

        atr = technical.get('atr')
        al = _format_atr_line(atr)
        if al:
            msg1_lines.append(al)

        foreign = supply.get('foreign')
        institutional = supply.get('institutional')
        program = supply.get('program')
        if (foreign is not None or institutional is not None) and not _is_previous_day_data(supply):
            if foreign is not None:
                msg1_lines.append(f"  외국인: {foreign:+.0f}만주")
            if institutional is not None:
                msg1_lines.append(f"  기관: {institutional:+.0f}만주")
            if program is not None:
                msg1_lines.append(f"  프로그램: {program:+.0f}만주")

        # 공매도
        short_selling = result.get('short_selling')
        sl = _format_short_selling_line(short_selling)
        if sl:
            msg1_lines.append(sl)

        # 포트폴리오 수익
        pl = _format_portfolio_line(ticker, price)
        if pl:
            msg1_lines.append(pl)

        # 밸류에이션
        valuation = result.get('valuation')
        val_l = _format_valuation_line(valuation)
        if val_l:
            msg1_lines.append(val_l)

        # 리스크
        risk_metrics = result.get('risk_metrics')
        rl = _format_risk_line(risk_metrics)
        if rl:
            msg1_lines.append(rl)

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
    msg1_lines.append("한 주의 시작입니다. 보유·관심 종목의 흐름을 꼼꼼히 점검해볼게요.")
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

    # 종목별 주간 점검
    from config.ticker_names import get_ticker_name
    for result in stock_results:
        ticker = result.get('ticker', '')
        if not ticker:
            continue

        name = get_ticker_name(ticker) or ticker
        ticker_code = ticker.split('.')[0]
        price = result.get('current_price', 0)
        returns = result.get('returns', {})
        technical = result.get('technical', {})
        supply = result.get('supply_demand_1d', {})

        msg1_lines.append(f"━━ <b>{name}({ticker_code})</b> 주간 점검 ━━")
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

        macd = technical.get('macd', {})
        if macd and isinstance(macd, dict):
            trend = macd.get('trend', '')
            if trend:
                msg1_lines.append(f"  MACD: {trend}")

        # 볼린저/골든크로스/거래량/스토캐스틱/OBV/ATR (모두 표시)
        bollinger = technical.get('bollinger')
        bl = _format_bollinger_line(bollinger, mode='full')
        if bl:
            msg1_lines.append(bl)

        gdc = technical.get('golden_dead_cross')
        gl = _format_golden_dead_cross_line(gdc, mode='full')
        if gl:
            msg1_lines.append(gl)

        vs = technical.get('volume_spike')
        vl = _format_volume_spike_line(vs, mode='full')
        if vl:
            msg1_lines.append(vl)

        stoch = technical.get('stochastic')
        stl = _format_stochastic_line(stoch)
        if stl:
            msg1_lines.append(stl)

        obv = technical.get('obv')
        ol = _format_obv_line(obv)
        if ol:
            msg1_lines.append(ol)

        atr = technical.get('atr')
        al = _format_atr_line(atr)
        if al:
            msg1_lines.append(al)

        foreign = supply.get('foreign')
        institutional = supply.get('institutional')
        program = supply.get('program')
        if (foreign is not None or institutional is not None) and not _is_previous_day_data(supply):
            msg1_lines.append("")
            msg1_lines.append("  수급 현황:")
            if foreign is not None:
                msg1_lines.append(f"    외국인: {foreign:+.0f}만주")
            if institutional is not None:
                msg1_lines.append(f"    기관: {institutional:+.0f}만주")
            if program is not None:
                msg1_lines.append(f"    프로그램: {program:+.0f}만주")

        # 공매도
        short_selling = result.get('short_selling')
        sl = _format_short_selling_line(short_selling)
        if sl:
            msg1_lines.append(sl)

        msg1_lines.append("")

        # 포트폴리오 수익
        pl = _format_portfolio_line(ticker, price)
        if pl:
            msg1_lines.append(pl)

        # 밸류에이션 (모두 표시)
        valuation = result.get('valuation')
        val_l = _format_valuation_line(valuation)
        if val_l:
            msg1_lines.append(val_l)

        # 리스크 (모두 표시)
        risk_metrics = result.get('risk_metrics')
        rl = _format_risk_line(risk_metrics)
        if rl:
            msg1_lines.append(rl)

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


def _get_portfolio_buy_info(ticker: str) -> Optional[Dict]:
    """포트폴리오에서 매수 정보 조회 (buy_price, buy_quantity)"""
    try:
        from src.portfolio_manager import PortfolioManager
        pm = PortfolioManager()
        items = pm.list_by_category('possession')
        for item in items:
            if item.get('ticker') == ticker:
                buy_price = item.get('buy_price')
                if buy_price is not None:
                    return {'buy_price': buy_price, 'buy_quantity': item.get('buy_quantity')}
        return None
    except Exception:
        return None


def _format_bollinger_line(bollinger: Optional[Dict], mode: str = 'normal') -> Optional[str]:
    """볼린저 밴드 라인 포맷. mode='normal'이면 squeeze일 때만, 'full'이면 항상"""
    if not bollinger:
        return None
    squeeze = bollinger.get('squeeze')
    bandwidth = bollinger.get('bandwidth')
    percent_b = bollinger.get('percent_b')
    if mode == 'normal':
        if squeeze:
            return "   볼린저: 밴드 수축 중 ⚡ (큰 변동 임박)"
        return None
    # full mode (weekly)
    parts = []
    if bandwidth is not None:
        parts.append(f"밴드폭 {bandwidth:.1f}")
    if percent_b is not None:
        parts.append(f"%B {percent_b:.2f}")
    if squeeze:
        parts.append("⚡ 수축 중")
    return f"   볼린저: {' | '.join(parts)}" if parts else None


def _format_golden_dead_cross_line(gdc: Optional[Dict], mode: str = 'normal') -> Optional[str]:
    """골든/데드크로스 라인. mode='normal'이면 10일 이내만, 'full'이면 항상"""
    if not gdc:
        return None
    cross_type = gdc.get('cross_type')
    days_since = gdc.get('days_since')
    if cross_type is None:
        if mode == 'full':
            return "   골든/데드크로스: 없음"
        return None
    if mode == 'normal' and days_since is not None and days_since > 10:
        return None
    label = "골든크로스" if cross_type == 'golden' else "데드크로스"
    emoji = "⚡" if cross_type == 'golden' else "⚠️"
    days_str = f" ({days_since}일 전)" if days_since is not None else ""
    return f"   {emoji} {label} 발생{days_str}"


def _format_volume_spike_line(vs: Optional[Dict], mode: str = 'normal') -> Optional[str]:
    """거래량 급증 라인. mode='normal'이면 2배 이상만, 'full'이면 항상"""
    if not vs:
        return None
    is_spike = vs.get('is_spike', False)
    ratio = vs.get('ratio')
    if ratio is None:
        return None
    if mode == 'normal' and not is_spike:
        return None
    emoji = "⚡" if is_spike else ""
    return f"   거래량: 20일 평균 대비 {ratio:.1f}배 {emoji}".rstrip()


def _format_short_selling_line(short: Optional[Dict]) -> Optional[str]:
    """공매도 라인"""
    if not short:
        return None
    ratio = short.get('short_ratio')
    if ratio is None:
        return None
    return f"   공매도: {ratio:.1f}%"


def _format_valuation_line(val: Optional[Dict]) -> Optional[str]:
    """밸류에이션 라인"""
    if not val:
        return None
    parts = []
    per = val.get('per')
    pbr = val.get('pbr')
    if per is not None:
        parts.append(f"PER {per:.1f}")
    if pbr is not None:
        parts.append(f"PBR {pbr:.1f}")
    eps = val.get('eps')
    div_yield = val.get('div_yield')
    if eps is not None:
        parts.append(f"EPS {eps:,.0f}")
    if div_yield is not None:
        parts.append(f"배당률 {div_yield:.1f}%")
    return f"📊 밸류에이션: {' | '.join(parts)}" if parts else None


def _format_risk_line(risk: Optional[Dict]) -> Optional[str]:
    """리스크 라인"""
    if not risk:
        return None
    parts = []
    beta = risk.get('beta')
    mdd = risk.get('mdd_3m')
    sharpe = risk.get('sharpe')
    if beta is not None:
        parts.append(f"베타 {beta:.2f}")
    if mdd is not None:
        parts.append(f"3개월 MDD {mdd:.1f}%")
    if sharpe is not None:
        parts.append(f"샤프 {sharpe:.2f}")
    return f"⚠️ 리스크: {' | '.join(parts)}" if parts else None


def _format_portfolio_line(ticker: str, current_price) -> Optional[str]:
    """포트폴리오 내 수익 라인"""
    if not isinstance(current_price, (int, float)) or current_price <= 0:
        return None
    info = _get_portfolio_buy_info(ticker)
    if not info:
        return None
    buy_price = info['buy_price']
    if buy_price is None or buy_price <= 0:
        return None
    pct = (current_price - buy_price) / buy_price * 100
    return f"💼 내 수익: 매수가 {buy_price:,.0f} → 현재 {current_price:,.0f} ({pct:+.1f}%)"


def _format_stochastic_line(stoch: Optional[Dict]) -> Optional[str]:
    """스토캐스틱 라인"""
    if not stoch:
        return None
    k = stoch.get('k')
    d = stoch.get('d')
    if k is None and d is None:
        return None
    parts = []
    if k is not None:
        parts.append(f"%K {k:.0f}")
    if d is not None:
        parts.append(f"%D {d:.0f}")
    return f"   스토캐스틱: {' | '.join(parts)}"


def _format_obv_line(obv: Optional[Dict]) -> Optional[str]:
    """OBV 라인"""
    if not obv:
        return None
    trend = obv.get('trend')
    if trend is None:
        return None
    return f"   OBV: {trend}"


def _format_atr_line(atr) -> Optional[str]:
    """ATR 라인"""
    if atr is None:
        return None
    return f"   ATR: {atr:,.0f}"


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

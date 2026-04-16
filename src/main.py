"""
Stock Insight Bot 메인 실행 파일
3모드 리포트 시스템: 평시 / 경보 / 주간
"""
import logging
import sys
import os
import warnings
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import holidays

# 불필요한 경고 메시지 필터링
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*google.generativeai.*")

# gRPC DNS 리졸버 설정
os.environ["GRPC_DNS_RESOLVER"] = "native"
os.environ["GRPC_VERBOSITY"] = "ERROR"

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import settings
from src.analysis import get_stock_summary_by_category
from src.crawler import (
    get_market_news_with_context,
    get_market_indicators,
    translate_headlines,
    get_us_top_movers,
    get_korea_hot_themes,
    get_hankyung_consensus,
    get_google_news_rss,
    get_hot_news
)
from src.analysis import get_tradingview_technical_summary
from src.ai_researcher import create_researcher
from src.notifier import create_notifier
from src.alert_engine import determine_mode, generate_normal_message, generate_alert_messages, generate_weekly_messages, generate_intraday_message
from src.cross_project_data import get_enriched_data_for_ai, get_theme_forecast_text, get_cross_validated_signals_text, get_intraday_investor_data

# 테스트 모드 확인
TEST_MODE = os.getenv('TEST_MODE', 'false').lower() == 'true' or '--test' in sys.argv

# 수동 실행 확인
TRIGGER_TYPE = os.getenv('TRIGGER_TYPE', '')
IS_MANUAL_RUN = TRIGGER_TYPE == 'workflow_dispatch' or TRIGGER_TYPE == ''

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def is_korean_holiday_or_weekend() -> tuple[bool, str]:
    """대한민국 기준 공휴일 또는 주말인지 확인"""
    KST = ZoneInfo("Asia/Seoul")
    now_kst = datetime.now(KST)
    today = now_kst.date()

    if today.weekday() >= 5:
        day_name = "토요일" if today.weekday() == 5 else "일요일"
        return True, f"주말 ({day_name})"

    kr_holidays = holidays.KR(years=today.year)
    if today in kr_holidays:
        holiday_name = kr_holidays.get(today)
        return True, f"공휴일 ({holiday_name})"

    return False, ""


def should_skip_evening_report() -> tuple[bool, str]:
    """저녁 리포트 스킵 여부 (휴일에는 오전 1회만)"""
    KST = ZoneInfo("Asia/Seoul")
    now_kst = datetime.now(KST)
    is_evening = now_kst.hour >= 18

    if not is_evening:
        return False, ""

    is_holiday, holiday_reason = is_korean_holiday_or_weekend()
    if is_holiday:
        return True, f"{holiday_reason} - 저녁 리포트 스킵 (오전 1회만 발송)"

    return False, ""


def _parse_macro_values(macro_text: str) -> dict:
    """매크로 지표 텍스트에서 수치 추출"""
    import re
    values = {}

    # USD/KRW
    m = re.search(r'USD/KRW[:\s]*([0-9,]+\.?\d*)', macro_text)
    if m:
        values['usdkrw'] = float(m.group(1).replace(',', ''))

    # VIX
    m = re.search(r'VIX[:\s]*([0-9]+\.?\d*)', macro_text)
    if m:
        values['vix'] = float(m.group(1))

    # 미국 10Y
    m = re.search(r'10[Yy년][:\s]*([0-9]+\.?\d*)%?', macro_text)
    if m:
        values['us10y'] = float(m.group(1))

    # Fear & Greed
    m = re.search(r'[Ff]ear.*?[Gg]reed.*?(\d+)', macro_text)
    if m:
        values['fear_greed'] = float(m.group(1))

    return values


def _extract_stock_analysis_results() -> list:
    """보유·관심 국내 종목의 분석 결과를 추출"""
    from src.analysis import analyze_all_tickers
    tickers = (
        settings.tickers_possession_domestic
        + settings.tickers_interest_domestic
    )
    # 중복 제거 (순서 유지)
    tickers = list(dict.fromkeys(tickers))
    if not tickers:
        return []

    results = analyze_all_tickers(tickers)
    return results


def main():
    """메인 실행 함수"""
    try:
        logger.info("=" * 50)
        logger.info("Stock Insight Bot 시작 (v3 - 3모드 시스템)")
        if TEST_MODE:
            logger.info("🧪 테스트 모드 활성화")
        if IS_MANUAL_RUN:
            logger.info("🖐️ 수동 실행 감지")
        logger.info("=" * 50)

        # 휴일 저녁 리포트 스킵 체크
        should_skip, skip_reason = should_skip_evening_report()
        if should_skip and not TEST_MODE and not IS_MANUAL_RUN:
            logger.info(f"📅 {skip_reason}")
            return
        elif should_skip and IS_MANUAL_RUN:
            logger.info(f"📅 {skip_reason} (수동 실행이므로 계속 진행)")

        # 시간대 판단
        KST = ZoneInfo("Asia/Seoul")
        now_kst = datetime.now(KST)
        is_evening = now_kst.hour >= 18
        current_hour = now_kst.hour
        current_minute = now_kst.minute

        # 장중 수급 속보 모드 판단 (10:30, 13:50 실행)
        # theme_analysis가 10:01/13:21에 수급 수집 → 이 프로그램은 10:30/13:50에 읽어서 전송
        is_intraday = (
            (current_hour == 10 and 20 <= current_minute <= 45) or
            (current_hour == 13 and 40 <= current_minute <= 59)
        )

        # 장중 모드에서 사용할 타겟 라운드 (theme_analysis 수집 시간 기준)
        intraday_target_round = None
        if is_intraday:
            if current_hour == 10:
                intraday_target_round = "10:01"
            elif current_hour == 13:
                intraday_target_round = "13:21"

        logger.info(f"설정 로드: 관심종목 {len(settings.tickers)}개")
        if is_intraday:
            logger.info(f"📊 장중 수급 속보 모드 (타겟 라운드: {intraday_target_round})")

        # ================================
        # 장중 수급 속보 모드 (별도 경로)
        # ================================
        if is_intraday and not TEST_MODE:
            logger.info("\n[장중 모드] theme_analysis 수급 데이터 로드...")

            all_tickers = (
                settings.tickers_possession_domestic +
                settings.tickers_possession_overseas +
                settings.tickers_interest_domestic +
                settings.tickers_interest_overseas
            )
            # 국내 종목만 필터 (수급 데이터는 국내만)
            domestic_tickers = [t for t in all_tickers if '.KS' in t or '.KQ' in t]

            if not domestic_tickers:
                logger.info("국내 종목 없음 — 장중 수급 속보 스킵")
                return

            intraday_data = get_intraday_investor_data(domestic_tickers, target_round=intraday_target_round)

            if not intraday_data or not intraday_data.get("stocks"):
                logger.warning("장중 수급 데이터 없음 — theme_analysis 미실행 가능성")
                logger.info("장중 수급 속보 스킵")
                return

            logger.info(f"장중 수급 데이터 로드 완료: {len(intraday_data['stocks'])}개 종목, {intraday_data['time']} 라운드")

            messages = generate_intraday_message(intraday_data)

            # 텔레그램 발송
            notifier = create_notifier(settings.telegram_token, settings.chat_id)
            for msg in messages:
                if notifier.send_message(msg):
                    logger.info("✅ 장중 수급 속보 발송 성공")
                else:
                    logger.error("❌ 장중 수급 속보 발송 실패")

            logger.info("Stock Insight Bot 완료 (장중 수급 속보)")
            return

        # ================================
        # Step 1: 데이터 수집 (일반 모드)
        # ================================

        # 1-1: 듀얼 소스 배치 수집
        logger.info("\n[Step 1-1] 듀얼 소스 배치 수집...")
        try:
            from src.crawler import prefetch_dual_source_batch
            all_tickers = list(dict.fromkeys(
                settings.tickers_possession_domestic
                + settings.tickers_interest_domestic
            ))
            if all_tickers:
                prefetch_dual_source_batch(all_tickers)
                logger.info("듀얼 소스 배치 수집 완료")
        except Exception as e:
            logger.warning(f"듀얼 소스 배치 수집 실패: {e}")

        # 1-2: 주가 데이터 + 기술지표 분석
        logger.info("\n[Step 1-2] 주가 데이터 수집...")
        stock_results = _extract_stock_analysis_results()
        logger.info(f"주가 분석 완료: {len(stock_results)}개 종목")

        # 1-3: 카테고리별 요약 텍스트 (AI 프롬프트용)
        stock_summaries = get_stock_summary_by_category(
            possession_domestic=settings.tickers_possession_domestic,
            possession_overseas=settings.tickers_possession_overseas,
            interest_domestic=settings.tickers_interest_domestic,
            interest_overseas=settings.tickers_interest_overseas
        )

        # 1-4: 매크로 지표
        logger.info("\n[Step 1-4] 매크로 경제 지표 수집...")
        macro_indicators = get_market_indicators()

        # 매크로 수치 파싱
        macro_vals = _parse_macro_values(macro_indicators)
        usdkrw = macro_vals.get('usdkrw')
        vix_value = macro_vals.get('vix')
        us10y = macro_vals.get('us10y')
        fear_greed_score = macro_vals.get('fear_greed')

        # NQ 선물은 크로스 프로젝트 데이터에서 가져올 수 있음
        nq_change_pct = None
        try:
            from src.cross_project_data import get_macro_indicators as get_cross_macro
            cross_macro = get_cross_macro()
            if cross_macro and 'indicators' in cross_macro:
                for ind in cross_macro['indicators']:
                    if ind.get('symbol') == 'NQ=F':
                        nq_change_pct = ind.get('change_pct')
                        break
        except Exception:
            pass

        # ================================
        # Step 2: 모드 결정
        # ================================
        logger.info("\n[Step 2] 리포트 모드 결정...")
        mode, alerts, yellow_notes = determine_mode(
            stock_results=stock_results,
            macro_text=macro_indicators,
            fear_greed_score=fear_greed_score,
            vix_value=vix_value,
            usdkrw=usdkrw,
            usdkrw_change=None,  # 전일 대비 변화는 별도 계산 필요
            us10y=us10y,
            nq_change_pct=nq_change_pct,
        )
        logger.info(f"📋 리포트 모드: {mode} (경보 {len(alerts)}건, 주의 {len(yellow_notes)}건)")

        # ================================
        # Step 3: 모드별 메시지 생성
        # ================================
        messages = []
        token_usage = {}

        if mode in ('normal', 'yellow'):
            # === 평시/주의 모드: AI 호출 없음 ===
            logger.info(f"\n[Step 3] {mode} 모드 — AI 호출 없이 메시지 생성")

            messages = generate_normal_message(
                stock_results=stock_results,
                macro_text=macro_indicators,
                fear_greed_score=fear_greed_score,
                vix_value=vix_value,
                usdkrw=usdkrw,
                us10y=us10y,
                nq_change_pct=nq_change_pct,
                is_evening=is_evening,
                yellow_notes=yellow_notes if mode == 'yellow' else None,
            )

        elif mode == 'alert':
            # === 경보 모드: AI 호출하여 상황 해석 ===
            logger.info("\n[Step 3] 경보 모드 — 추가 데이터 수집 + AI 분석")

            # 추가 데이터 수집 (경보 시에만)
            us_top_movers = get_us_top_movers(max_items=10)
            korea_hot_themes = get_korea_hot_themes(max_themes=3)
            news_with_context = get_market_news_with_context(max_items=10)
            news_formatted = translate_headlines(news_with_context)
            hot_news = get_hot_news(overseas_count=10, domestic_count=10)
            hot_news_formatted = translate_headlines(hot_news)

            all_stock_summaries = "\n\n".join([msg for msg in stock_summaries.values() if msg])
            collected_data = f"""[PORTFOLIO_DATA]
{all_stock_summaries}

[MACRO_DATA]
{macro_indicators}

[US_TOP_MOVERS]
{us_top_movers}

[TODAYS_HOT_THEMES]
{korea_hot_themes}

[NEWS_DATA]
{news_formatted}

[HOT_NEWS]
{hot_news_formatted}"""

            # 크로스 프로젝트 데이터 추가
            enriched = get_enriched_data_for_ai()
            if enriched:
                collected_data += f"\n\n{enriched}"

            # AI 리포트 생성 (Compact만 사용)
            researcher = create_researcher()
            compact_briefing, _, token_usage = researcher.generate_briefing(collected_data)

            messages = generate_alert_messages(
                stock_results=stock_results,
                alerts=alerts,
                macro_text=macro_indicators,
                ai_insight=compact_briefing,
                fear_greed_score=fear_greed_score,
                vix_value=vix_value,
                usdkrw=usdkrw,
                us10y=us10y,
                nq_change_pct=nq_change_pct,
                is_evening=is_evening,
            )

        elif mode == 'weekly':
            # === 주간 모드: 전체 데이터 수집 + AI 심층 분석 ===
            logger.info("\n[Step 3] 주간 모드 — 전체 데이터 수집 + AI 심층 분석")

            # 전체 데이터 수집
            us_top_movers = get_us_top_movers(max_items=10)
            korea_hot_themes = get_korea_hot_themes(max_themes=3)
            hankyung_consensus = get_hankyung_consensus()
            google_news = get_google_news_rss()
            tradingview_signals = get_tradingview_technical_summary(settings.tickers[:10])
            news_with_context = get_market_news_with_context(max_items=10)
            news_formatted = translate_headlines(news_with_context)
            hot_news = get_hot_news(overseas_count=10, domestic_count=10)
            hot_news_formatted = translate_headlines(hot_news)

            all_stock_summaries = "\n\n".join([msg for msg in stock_summaries.values() if msg])
            collected_data = f"""[PORTFOLIO_DATA]
{all_stock_summaries}

[MACRO_DATA]
{macro_indicators}

[US_TOP_MOVERS]
{us_top_movers}

[TODAYS_HOT_THEMES]
{korea_hot_themes}

[MARKET_MATERIALS]
{hankyung_consensus}
{google_news}

[TECHNICAL_SIGNALS]
{tradingview_signals}

[NEWS_DATA]
{news_formatted}

[HOT_NEWS]
{hot_news_formatted}"""

            # 크로스 프로젝트 데이터 추가
            enriched = get_enriched_data_for_ai()
            if enriched:
                collected_data += f"\n\n{enriched}"

            # AI 리포트 생성 (Detailed 사용)
            researcher = create_researcher()
            _, detailed_briefing, token_usage = researcher.generate_briefing(collected_data)

            # 테마/시그널 텍스트
            theme_text = get_theme_forecast_text()
            signal_text = get_cross_validated_signals_text()

            messages = generate_weekly_messages(
                stock_results=stock_results,
                macro_text=macro_indicators,
                ai_detailed=detailed_briefing,
                theme_text=theme_text,
                signal_text=signal_text,
                fear_greed_score=fear_greed_score,
                vix_value=vix_value,
                usdkrw=usdkrw,
                us10y=us10y,
                nq_change_pct=nq_change_pct,
            )

        # ================================
        # Step 4: 텔레그램 발송
        # ================================
        logger.info(f"\n[Step 4] 텔레그램 발송 ({len(messages)}개 메시지)...")
        notifier = create_notifier(settings.telegram_token, settings.chat_id)

        messages_sent = 0
        messages_failed = 0

        # KRX API 경고 메시지 (필요 시)
        try:
            from src.crawler import get_krx_api_expired_status
            if get_krx_api_expired_status():
                krx_msg = "<b>⚠️ KRX API 키 인증 오류</b>\n현재 네이버 크롤링으로 수급 데이터를 수집하고 있습니다.\nKRX Data Marketplace에서 인증키를 확인해 주세요."
                if notifier.send_message(krx_msg):
                    messages_sent += 1
        except Exception:
            pass

        # 메인 메시지 발송
        for i, msg in enumerate(messages):
            if notifier.send_message(msg):
                messages_sent += 1
                logger.info(f"✅ 메시지 {i+1}/{len(messages)} 발송 성공")
            else:
                messages_failed += 1
                logger.error(f"❌ 메시지 {i+1}/{len(messages)} 발송 실패")

            # 연속 발송 방지
            if i < len(messages) - 1:
                import time
                time.sleep(1)

        # 결과 로깅
        if messages_failed == 0:
            logger.info(f"✅ 모든 메시지 발송 성공 (총 {messages_sent}개, 모드: {mode})")
        else:
            logger.error(f"⚠️ 발송 완료: 성공 {messages_sent}개, 실패 {messages_failed}개")
            if messages_sent == 0:
                sys.exit(1)

        if token_usage:
            logger.info(f"💾 토큰 사용: {token_usage.get('total_tokens', 0):,}개")

        logger.info("\n" + "=" * 50)
        logger.info(f"Stock Insight Bot 완료 (모드: {mode})")
        logger.info("=" * 50)

    except Exception as e:
        logger.error(f"프로그램 실행 중 오류 발생: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

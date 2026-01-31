"""
Stock Insight Bot 메인 실행 파일
전체 프로세스 오케스트레이션
"""
import logging
import sys
import os
import warnings
from pathlib import Path
from datetime import datetime, date
from zoneinfo import ZoneInfo

import holidays

# 불필요한 경고 메시지 필터링 (google-generativeai FutureWarning 등)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*google.generativeai.*")

# gRPC DNS 리졸버 설정 (DNS 해석 실패 문제 해결)
# c-ares 대신 OS의 기본 DNS 리졸버 사용
os.environ["GRPC_DNS_RESOLVER"] = "native"
os.environ["GRPC_VERBOSITY"] = "ERROR"  # 불필요한 gRPC 로그 끄기

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

# 테스트 모드 확인 (환경변수 또는 명령줄 인자)
TEST_MODE = os.getenv('TEST_MODE', 'false').lower() == 'true' or '--test' in sys.argv

# 수동 실행 확인 (GitHub Actions workflow_dispatch 또는 로컬 실행)
# - workflow_dispatch: GitHub에서 수동 실행
# - 로컬 실행: TRIGGER_TYPE이 없으면 수동 실행으로 간주
TRIGGER_TYPE = os.getenv('TRIGGER_TYPE', '')
IS_MANUAL_RUN = TRIGGER_TYPE == 'workflow_dispatch' or TRIGGER_TYPE == ''

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def is_korean_holiday_or_weekend() -> tuple[bool, str]:
    """
    대한민국 기준 공휴일 또는 주말인지 확인

    Returns:
        (is_holiday: bool, reason: str)
    """
    KST = ZoneInfo("Asia/Seoul")
    now_kst = datetime.now(KST)
    today = now_kst.date()

    # 주말 체크 (토요일=5, 일요일=6)
    if today.weekday() >= 5:
        day_name = "토요일" if today.weekday() == 5 else "일요일"
        return True, f"주말 ({day_name})"

    # 대한민국 공휴일 체크
    kr_holidays = holidays.KR(years=today.year)
    if today in kr_holidays:
        holiday_name = kr_holidays.get(today)
        return True, f"공휴일 ({holiday_name})"

    return False, ""


def should_skip_evening_report() -> tuple[bool, str]:
    """
    저녁 리포트를 스킵해야 하는지 확인
    휴일(주말/공휴일)에는 오전 8시 1회만 발송

    Returns:
        (should_skip: bool, reason: str)
    """
    KST = ZoneInfo("Asia/Seoul")
    now_kst = datetime.now(KST)
    current_hour = now_kst.hour

    # 저녁 시간대 판단 (18:00 이후 = 저녁 리포트)
    is_evening = current_hour >= 18

    if not is_evening:
        return False, ""

    # 휴일 체크
    is_holiday, holiday_reason = is_korean_holiday_or_weekend()

    if is_holiday:
        return True, f"{holiday_reason} - 저녁 리포트 스킵 (오전 1회만 발송)"

    return False, ""


def main():
    """메인 실행 함수"""
    try:
        logger.info("=" * 50)
        logger.info("Stock Insight Bot 시작")
        if TEST_MODE:
            logger.info("🧪 테스트 모드 활성화")
        if IS_MANUAL_RUN:
            logger.info("🖐️ 수동 실행 감지 (휴일 스킵 무시)")
        logger.info("=" * 50)

        # 휴일 저녁 리포트 스킵 체크
        # 단, 수동 실행(workflow_dispatch, 로컬) 또는 테스트 모드에서는 스킵하지 않음
        should_skip, skip_reason = should_skip_evening_report()
        if should_skip and not TEST_MODE and not IS_MANUAL_RUN:
            logger.info(f"📅 {skip_reason}")
            logger.info("프로그램 종료")
            return
        elif should_skip and IS_MANUAL_RUN:
            logger.info(f"📅 {skip_reason} (수동 실행이므로 계속 진행)")

        # 설정 로드 확인
        logger.info(f"설정 로드 확인: 티커 {len(settings.tickers)}개")
        logger.info(f"분석 대상 종목: {settings.tickers}")
        
        # Step 1: 주가 데이터 수집 및 요약 (카테고리별)
        logger.info("\n[Step 1] 주가 데이터 수집 및 요약 시작 (카테고리별)...")
        stock_summaries = get_stock_summary_by_category(
            possession_domestic=settings.tickers_possession_domestic,
            possession_overseas=settings.tickers_possession_overseas,
            interest_domestic=settings.tickers_interest_domestic,
            interest_overseas=settings.tickers_interest_overseas
        )
        logger.info("주가 요약 텍스트 생성 완료")
        
        # Step 2: 매크로 경제 지표 수집
        logger.info("\n[Step 2] 매크로 경제 지표 수집 시작...")
        macro_indicators = get_market_indicators()
        logger.info("매크로 경제 지표 수집 완료")
        
        # Step 2-1: 미국 Top Movers 수집 (나비 효과 분석용)
        logger.info("\n[Step 2-1] 미국 Top Movers 수집 시작...")
        us_top_movers = get_us_top_movers(max_items=10)
        logger.info("미국 Top Movers 수집 완료")
        
        # Step 2-2: 한국 Hot Themes 수집 (급등주 누락 방지)
        logger.info("\n[Step 2-2] 한국 Hot Themes 수집 시작...")
        korea_hot_themes = get_korea_hot_themes(max_themes=3)
        logger.info("한국 Hot Themes 수집 완료")
        
        # Step 2-3: 한경 컨센서스 수집 (국내 시장 재료)
        logger.info("\n[Step 2-3] 한경 컨센서스 수집 시작...")
        hankyung_consensus = get_hankyung_consensus()
        logger.info("한경 컨센서스 수집 완료")
        
        # Step 2-4: Google News RSS 수집 (해외 시장 재료)
        logger.info("\n[Step 2-4] Google News RSS 수집 시작...")
        google_news = get_google_news_rss()
        logger.info("Google News RSS 수집 완료")
        
        # Step 2-5: TradingView 기술적 분석 수집
        logger.info("\n[Step 2-5] TradingView 기술적 분석 수집 시작...")
        # 모든 종목 코드 추출
        all_tickers = (
            settings.tickers_possession_domestic +
            settings.tickers_possession_overseas +
            settings.tickers_interest_domestic +
            settings.tickers_interest_overseas
        )
        tradingview_signals = get_tradingview_technical_summary(all_tickers[:10])  # 상위 10개만
        logger.info("TradingView 기술적 분석 수집 완료")
        
        # Step 3: 뉴스 제목+요약 수집 (Python 크롤링, 필터링 적용)
        logger.info("\n[Step 3] 시장 뉴스 수집 시작 (제목+요약, 필터링 적용)...")
        news_with_context = get_market_news_with_context(max_items=10)
        logger.info("뉴스 수집 완료")
        
        # Step 4: 뉴스 포맷팅 (영어 뉴스 한국어 번역 포함 - deep-translator 사용)
        logger.info("\n[Step 4] 뉴스 포맷팅 시작 (영어 뉴스 번역 포함, deep-translator 사용)...")
        # deep-translator를 사용한 번역 (Gemini API 호출 없음)
        news_formatted = translate_headlines(news_with_context)
        logger.info("뉴스 포맷팅 완료")
        
        # Step 4-1: Hot/인기 뉴스 수집 (포트폴리오 필터링 없음)
        # 포트폴리오와 무관하지만 현재 화두가 되고 있는 뉴스를 수집하여 분석의 폭과 시야를 넓히는 것이 목적
        logger.info("\n[Step 4-1] Hot/인기 뉴스 수집 시작 (해외 10개, 국내 10개)...")
        hot_news = get_hot_news(overseas_count=10, domestic_count=10)
        logger.info("Hot/인기 뉴스 수집 완료")
        
        # Step 4-2: Hot 뉴스 포맷팅 및 번역
        logger.info("\n[Step 4-2] Hot 뉴스 포맷팅 및 번역 시작...")
        hot_news_formatted = translate_headlines(hot_news)
        logger.info("Hot 뉴스 포맷팅 및 번역 완료")
        
        # Step 5: 수집된 데이터 통합 (AI 분석용)
        logger.info("\n[Step 5] 수집된 데이터 통합 (AI 분석용)...")
        # AI 분석을 위해 모든 카테고리 메시지를 합침
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
        logger.info(f"통합 데이터 준비 완료: {len(collected_data)}자")
        
        # Step 6: AI 초기화 (리포트 생성용)
        logger.info("\n[Step 6] AI 리포트 생성 준비...")
        # AI researcher 초기화 (공유 API 키 매니저 사용)
        from config.settings import get_api_key_manager
        key_manager = get_api_key_manager()
        logger.info(f"  사용 가능한 Google API 키: {key_manager.total_keys}개 (현재 #{key_manager.current_key_number})")
        researcher = create_researcher()
        
        # Step 7: AI 일일 리포트 생성 (최종 1회 API 호출)
        logger.info("\n[Step 7] AI 일일 리포트 생성 시작 (최종 1회 API 호출)...")
        compact_briefing, detailed_briefing, token_usage = researcher.generate_briefing(collected_data)
        logger.info("AI 일일 리포트 생성 완료")
        
        # Step 8: 텔레그램 발송 (각 카테고리별로 개별 메시지 전송)
        logger.info("\n[Step 8] 텔레그램 메시지 발송 시작...")
        notifier = create_notifier(settings.telegram_token, settings.chat_id)
        
        # 현재 날짜/시간 (KST)
        kst = ZoneInfo('Asia/Seoul')
        now = datetime.now(kst)
        date_time_str = now.strftime("%Y년 %m월 %d일 %H시 %M분")
        
        # 메시지 발송 순서: 바리케이트 -> 각 티커 카테고리 -> 매크로 지표 -> 뉴스 -> AI 인사이트
        messages_sent = 0
        messages_failed = 0
        
        # KRX API 상태 확인 및 경고 메시지 준비
        krx_warning_message = None
        try:
            from src.crawler import get_krx_api_status, get_krx_api_expired_status
            
            # 401 오류 기반 만료 상태 확인 (유효기간 정보 없어도 작동)
            api_expired = get_krx_api_expired_status()
            
            # 유효기간 정보 기반 상태 확인 (상세 정보용)
            krx_status = get_krx_api_status()
            
            if api_expired:
                # 401 오류 발생으로 인한 만료 추정
                if krx_status.get('expired') or (krx_status.get('days_until_expiry') is not None and krx_status.get('days_until_expiry') <= 7):
                    # 유효기간 정보가 있는 경우: 상세 메시지
                    if krx_status.get('expired'):
                        # 유효기간 만료
                        expiry_date = krx_status.get('expiry_date')
                        expiry_str = expiry_date.strftime('%Y년 %m월 %d일') if expiry_date else '알 수 없음'
                        krx_warning_message = f"""<b>⚠️ KRX API 키 유효기간 만료 안내</b>

KRX API 키의 유효기간이 만료되었습니다.
만료일: {expiry_str}

현재는 네이버 크롤링으로 데이터를 수집하고 있습니다.
KRX Data Marketplace에서 새로운 인증키를 발급받아 주세요.

🔗 https://openapi.krx.co.kr"""
                    elif krx_status.get('days_until_expiry') is not None and krx_status.get('days_until_expiry') <= 7:
                        # 7일 이내 만료 예정
                        expiry_date = krx_status.get('expiry_date')
                        days_left = krx_status.get('days_until_expiry')
                        expiry_str = expiry_date.strftime('%Y년 %m월 %d일') if expiry_date else '알 수 없음'
                        krx_warning_message = f"""<b>⚠️ KRX API 키 유효기간 만료 임박 안내</b>

KRX API 키의 유효기간이 곧 만료됩니다.
만료일: {expiry_str}
남은 일수: {days_left}일

만료 전에 KRX Data Marketplace에서 인증키를 갱신해 주세요.

🔗 https://openapi.krx.co.kr"""
                else:
                    # 유효기간 정보가 없는 경우: 일반 경고 메시지
                    krx_warning_message = f"""<b>⚠️ KRX API 키 인증 실패 안내</b>

KRX API 호출 시 인증 오류가 발생했습니다.
가능한 원인:
• 인증키 유효기간 만료
• API 이용 신청 미승인
• 인증키 오류

현재는 네이버 크롤링으로 데이터를 수집하고 있습니다.
KRX Data Marketplace에서 인증키 상태를 확인하고 갱신해 주세요.

🔗 https://openapi.krx.co.kr"""
        except Exception as e:
            logger.debug(f"KRX API 상태 확인 실패: {e}")
        
        # 0. 바리케이트 메시지 전송 (이전 메시지 뭉치와 구분) - 일자 정보 포함
        # 듀얼 소스 상태 확인
        data_source_status = "🔄 듀얼 소스 (Agentic + API 병렬 수집)" if settings.use_dual_source else "📡 기존 방식 (순차 API 수집)"

        barrier_message = f"""<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>🚧🚧🚧🚧🚧🚧🚧🚧🚧🚧🚧🚧🚧🚧🚧</b>
<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>📅 리포트 생성 시간: {date_time_str} (KST)</b>
<b>📊 새로운 리포트 시작</b>
<b>{data_source_status}</b>
<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>"""
        
        if notifier.send_message(barrier_message):
            messages_sent += 1
            logger.info("✅ 바리케이트 메시지 발송 성공")
        else:
            messages_failed += 1
            logger.error("❌ 바리케이트 메시지 발송 실패")
        
        # KRX API 경고 메시지 발송 (있는 경우만)
        if krx_warning_message:
            if notifier.send_message(krx_warning_message):
                messages_sent += 1
                logger.info("✅ KRX API 경고 메시지 발송 성공")
            else:
                messages_failed += 1
                logger.error("❌ KRX API 경고 메시지 발송 실패")
        
        # 1. 각 티커 카테고리별 메시지 전송
        category_order = [
            ('possession_domestic', '💼 보유 종목 (국내)'),
            ('possession_overseas', '💼 보유 종목 (해외)'),
            ('interest_domestic', '👀 관심 종목 (국내)'),
            ('interest_overseas', '👀 관심 종목 (해외)'),
        ]
        
        for category_key, category_name in category_order:
            if category_key in stock_summaries and stock_summaries[category_key]:
                message = stock_summaries[category_key]
                if notifier.send_message(message):
                    messages_sent += 1
                    logger.info(f"✅ {category_name} 메시지 발송 성공")
                else:
                    messages_failed += 1
                    logger.error(f"❌ {category_name} 메시지 발송 실패")
        
        # 2. 매크로 경제 지표 메시지 전송
        macro_indicators_html = macro_indicators.replace("**매크로 경제 지표:**", "<b>📈 매크로 경제 지표</b>")
        if not macro_indicators_html.startswith("<b>"):
            macro_indicators_html = f"<b>📈 매크로 경제 지표</b>\n{macro_indicators_html}"
        macro_message = macro_indicators_html
        if notifier.send_message(macro_message):
            messages_sent += 1
            logger.info("✅ 매크로 경제 지표 메시지 발송 성공")
        else:
            messages_failed += 1
            logger.error("❌ 매크로 경제 지표 메시지 발송 실패")
        
        # 3. 주요 시장 뉴스 메시지 전송
        news_formatted_html = news_formatted.replace("**주요 시장 뉴스 헤드라인:**", "<b>📰 주요 시장 뉴스 (제목+요약)</b>")
        news_formatted_html = news_formatted_html.replace("**주요 시장 뉴스 (제목+요약):**", "<b>📰 주요 시장 뉴스 (제목+요약)</b>")
        if not news_formatted_html.startswith("<b>"):
            news_formatted_html = f"<b>📰 주요 시장 뉴스 (제목+요약)</b>\n{news_formatted_html}"
        news_message = news_formatted_html
        if notifier.send_message(news_message):
            messages_sent += 1
            logger.info("✅ 주요 시장 뉴스 메시지 발송 성공")
        else:
            messages_failed += 1
            logger.error("❌ 주요 시장 뉴스 메시지 발송 실패")
        
        # 3-1. Hot/인기 뉴스 메시지 전송
        hot_news_formatted_html = hot_news_formatted.replace("**🌎 해외시장 Hot 뉴스:**", "<b>🔥 해외시장 Hot 뉴스</b>")
        hot_news_formatted_html = hot_news_formatted_html.replace("**🇰🇷 국내시장 Hot 뉴스:**", "<b>🔥 국내시장 Hot 뉴스</b>")
        if not hot_news_formatted_html.startswith("<b>"):
            hot_news_formatted_html = f"<b>🔥 Hot/인기 뉴스</b>\n{hot_news_formatted_html}"
        hot_news_message = hot_news_formatted_html
        if notifier.send_message(hot_news_message):
            messages_sent += 1
            logger.info("✅ Hot/인기 뉴스 메시지 발송 성공")
        else:
            messages_failed += 1
            logger.error("❌ Hot/인기 뉴스 메시지 발송 실패")
        
        # 4. AI 투자 인사이트 메시지 전송 (Compact 먼저, 그 다음 Detailed)
        # 4-1. Compact 리포트 전송
        if compact_briefing:
            compact_briefing_html = f"<b>📱 AI 투자 인사이트 (Compact)</b>\n{compact_briefing}"
            compact_message = compact_briefing_html
            if notifier.send_message(compact_message):
                messages_sent += 1
                logger.info("✅ AI 투자 인사이트 (Compact) 메시지 발송 성공")
            else:
                messages_failed += 1
                logger.error("❌ AI 투자 인사이트 (Compact) 메시지 발송 실패")
        
        # 4-2. 구분선 메시지 전송
        separator_message = "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n<b>📊 상세 분석 리포트</b>\n<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>"
        if notifier.send_message(separator_message):
            messages_sent += 1
            logger.info("✅ AI 리포트 구분선 메시지 발송 성공")
        else:
            messages_failed += 1
            logger.error("❌ AI 리포트 구분선 메시지 발송 실패")
        
        # 4-3. Detailed 리포트 전송
        if detailed_briefing:
            detailed_briefing_html = f"<b>🤖 AI 투자 인사이트 (Detailed)</b>\n{detailed_briefing}"
            detailed_message = detailed_briefing_html
            if notifier.send_message(detailed_message):
                messages_sent += 1
                logger.info("✅ AI 투자 인사이트 (Detailed) 메시지 발송 성공")
            else:
                messages_failed += 1
                logger.error("❌ AI 투자 인사이트 (Detailed) 메시지 발송 실패")
        
        # 5. 바리케이트 메시지 전송 (메시지 뭉치 종료 표시) - 토큰 사용량 정보 포함
        token_info_text = ""
        if token_usage and token_usage.get('total_tokens', 0) > 0:
            prompt_tokens = token_usage.get('prompt_tokens', 0)
            completion_tokens = token_usage.get('completion_tokens', 0)
            total_tokens = token_usage.get('total_tokens', 0)
            token_info_text = f"\n<b>💾 LLM 토큰 사용량:</b> 입력 {prompt_tokens:,}개, 출력 {completion_tokens:,}개, 총 {total_tokens:,}개"
        
        barrier_end_message = f"""<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>🚧🚧🚧🚧🚧🚧🚧🚧🚧🚧🚧🚧🚧🚧🚧</b>
<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>📊 리포트 종료</b>{token_info_text}
<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>"""
        
        if notifier.send_message(barrier_end_message):
            messages_sent += 1
            logger.info("✅ 바리케이트 종료 메시지 발송 성공")
        else:
            messages_failed += 1
            logger.error("❌ 바리케이트 종료 메시지 발송 실패")
        
        # 최종 결과
        if messages_failed == 0:
            logger.info(f"✅ 모든 텔레그램 메시지 발송 성공 (총 {messages_sent}개)")
        else:
            logger.error(f"⚠️ 텔레그램 메시지 발송 완료: 성공 {messages_sent}개, 실패 {messages_failed}개")
            if messages_sent == 0:
                sys.exit(1)
        
        logger.info("\n" + "=" * 50)
        logger.info("Stock Insight Bot 완료")
        logger.info("=" * 50)
        
    except Exception as e:
        logger.error(f"프로그램 실행 중 오류 발생: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()



"""
Stock Insight Bot 메인 실행 파일
전체 프로세스 오케스트레이션
"""
import logging
import sys
import os
from pathlib import Path
from datetime import datetime
import pytz

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
    get_us_top_movers
)
from src.ai_researcher import create_researcher
from src.notifier import create_notifier

# 테스트 모드 확인 (환경변수 또는 명령줄 인자)
TEST_MODE = os.getenv('TEST_MODE', 'false').lower() == 'true' or '--test' in sys.argv

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def main():
    """메인 실행 함수"""
    try:
        logger.info("=" * 50)
        logger.info("Stock Insight Bot 시작")
        if TEST_MODE:
            logger.info("🧪 테스트 모드 활성화 - 메시지 발송 포함")
        logger.info("=" * 50)
        
        # 설정 로드 확인
        logger.info(f"설정 로드 완료: {settings}")
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
        
        # Step 3: 뉴스 제목+요약 수집 (Python 크롤링, 필터링 적용)
        logger.info("\n[Step 3] 시장 뉴스 수집 시작 (제목+요약, 필터링 적용)...")
        news_with_context = get_market_news_with_context(max_items=10)
        logger.info("뉴스 수집 완료")
        
        # Step 4: AI 초기화 (뉴스 번역 및 요약에 사용)
        logger.info("\n[Step 4] AI 초기화...")
        researcher = create_researcher(settings.google_api_key)
        
        # Step 5: 뉴스 한글 번역
        logger.info("\n[Step 5] 뉴스 한글 번역 시작...")
        news_translated = translate_headlines(news_with_context, researcher)
        logger.info("뉴스 번역 완료")
        
        # Step 6: 수집된 데이터 통합 (AI 분석용)
        logger.info("\n[Step 6] 수집된 데이터 통합...")
        # AI 분석을 위해 모든 카테고리 메시지를 합침
        all_stock_summaries = "\n\n".join([msg for msg in stock_summaries.values() if msg])
        collected_data = f"""{all_stock_summaries}

{macro_indicators}

{us_top_movers}

{news_translated}"""
        logger.info(f"통합 데이터 준비 완료: {len(collected_data)}자")
        
        # Step 7: AI 요약 코멘트 생성 (AI는 요약만 수행)
        logger.info("\n[Step 7] AI 요약 코멘트 생성 시작...")
        ai_briefing, token_usage = researcher.generate_briefing(collected_data)
        logger.info("AI 요약 코멘트 생성 완료")
        
        # Step 8: 텔레그램 발송 (각 카테고리별로 개별 메시지 전송)
        logger.info("\n[Step 8] 텔레그램 메시지 발송 시작...")
        notifier = create_notifier(settings.telegram_token, settings.chat_id)
        
        # 현재 날짜/시간 (KST)
        kst = pytz.timezone('Asia/Seoul')
        now = datetime.now(kst)
        date_time_str = now.strftime("%Y년 %m월 %d일 %H시 %M분")
        
        # 메시지 발송 순서: 바리케이트 -> 각 티커 카테고리 -> 매크로 지표 -> 뉴스 -> AI 인사이트
        messages_sent = 0
        messages_failed = 0
        
        # 0. 바리케이트 메시지 전송 (이전 메시지 뭉치와 구분) - 일자 정보 포함
        barrier_message = f"""<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>🚧🚧🚧🚧🚧🚧🚧🚧🚧🚧🚧🚧🚧🚧🚧</b>
<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>📅 리포트 생성 시간: {date_time_str} (KST)</b>
<b>📊 새로운 리포트 시작</b>
<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>"""
        
        if notifier.send_message(barrier_message):
            messages_sent += 1
            logger.info("✅ 바리케이트 메시지 발송 성공")
        else:
            messages_failed += 1
            logger.error("❌ 바리케이트 메시지 발송 실패")
        
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
        news_translated_html = news_translated.replace("**주요 시장 뉴스 헤드라인:**", "<b>📰 주요 시장 뉴스 (제목+요약)</b>")
        news_translated_html = news_translated_html.replace("**주요 시장 뉴스 (제목+요약):**", "<b>📰 주요 시장 뉴스 (제목+요약)</b>")
        if not news_translated_html.startswith("<b>"):
            news_translated_html = f"<b>📰 주요 시장 뉴스 (제목+요약)</b>\n{news_translated_html}"
        news_message = news_translated_html
        if notifier.send_message(news_message):
            messages_sent += 1
            logger.info("✅ 주요 시장 뉴스 메시지 발송 성공")
        else:
            messages_failed += 1
            logger.error("❌ 주요 시장 뉴스 메시지 발송 실패")
        
        # 4. AI 투자 인사이트 메시지 전송
        ai_briefing_html = f"<b>🤖 AI 투자 인사이트</b>\n{ai_briefing}"
        ai_message = ai_briefing_html
        if notifier.send_message(ai_message):
            messages_sent += 1
            logger.info("✅ AI 투자 인사이트 메시지 발송 성공")
        else:
            messages_failed += 1
            logger.error("❌ AI 투자 인사이트 메시지 발송 실패")
        
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



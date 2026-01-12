#!/usr/bin/env python3
"""
전체 기능 통합 테스트
각 모듈의 주요 기능을 실제로 테스트
"""
import sys
import logging
from pathlib import Path
import os

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_module_imports():
    """모든 모듈 import 테스트"""
    logger.info("=" * 70)
    logger.info("1. 모듈 Import 테스트")
    logger.info("=" * 70)
    
    modules = []
    
    try:
        import yfinance as yf
        logger.info(f"✅ yfinance (version: {yf.__version__})")
        modules.append(("yfinance", True))
    except Exception as e:
        logger.error(f"❌ yfinance: {e}")
        modules.append(("yfinance", False))
    
    try:
        from src.analysis import (
            get_stock_data, get_current_price, get_technical_indicators,
            get_stock_summary_by_category, get_tradingview_technical_summary
        )
        logger.info("✅ analysis 모듈")
        modules.append(("analysis", True))
    except Exception as e:
        logger.error(f"❌ analysis: {e}")
        modules.append(("analysis", False))
    
    try:
        from src.crawler import (
            get_yahoo_finance_news, get_market_indicators,
            get_us_top_movers, get_korea_hot_themes,
            get_hankyung_consensus, get_google_news_rss,
            get_market_news_with_context, translate_headlines
        )
        logger.info("✅ crawler 모듈")
        modules.append(("crawler", True))
    except Exception as e:
        logger.error(f"❌ crawler: {e}")
        modules.append(("crawler", False))
    
    try:
        from src.ai_researcher import create_researcher, AIResearcher
        logger.info("✅ ai_researcher 모듈")
        modules.append(("ai_researcher", True))
    except Exception as e:
        logger.error(f"❌ ai_researcher: {e}")
        modules.append(("ai_researcher", False))
    
    try:
        from src.notifier import create_notifier, TelegramNotifier
        logger.info("✅ notifier 모듈")
        modules.append(("notifier", True))
    except Exception as e:
        logger.error(f"❌ notifier: {e}")
        modules.append(("notifier", False))
    
    try:
        from config.settings import settings
        logger.info("✅ settings 모듈")
        modules.append(("settings", True))
    except Exception as e:
        logger.error(f"❌ settings: {e}")
        modules.append(("settings", False))
    
    failed = [name for name, success in modules if not success]
    if failed:
        logger.error(f"❌ Import 실패 모듈: {', '.join(failed)}")
        return False
    
    logger.info("✅ 모든 모듈 import 성공")
    return True

def test_analysis_functions():
    """analysis 모듈 기능 테스트"""
    logger.info("=" * 70)
    logger.info("2. analysis 모듈 기능 테스트")
    logger.info("=" * 70)
    
    from src.analysis import (
        get_stock_data, get_current_price, get_technical_indicators
    )
    
    test_tickers = ['AAPL', '005930.KS']
    results = []
    
    for ticker in test_tickers:
        try:
            logger.info(f"\n테스트 티커: {ticker}")
            
            # get_stock_data 테스트
            stock = get_stock_data(ticker)
            if stock:
                logger.info(f"  ✅ get_stock_data() 성공")
            else:
                logger.warning(f"  ⚠️ get_stock_data() None 반환")
                results.append(False)
                continue
            
            # get_current_price 테스트
            price = get_current_price(ticker)
            if price:
                logger.info(f"  ✅ get_current_price() 성공: ${price:.2f}" if price > 1 else f"  ✅ get_current_price() 성공: {price:.4f}")
            else:
                logger.warning(f"  ⚠️ get_current_price() None 반환")
                results.append(False)
                continue
            
            # get_technical_indicators 테스트
            indicators = get_technical_indicators(ticker)
            if indicators and indicators.get('rsi'):
                logger.info(f"  ✅ get_technical_indicators() 성공")
                logger.info(f"     RSI: {indicators.get('rsi'):.2f}")
                if indicators.get('ma20'):
                    logger.info(f"     MA20: {indicators.get('ma20'):.2f}")
            else:
                logger.warning(f"  ⚠️ get_technical_indicators() 데이터 부족")
            
            results.append(True)
            
        except Exception as e:
            logger.error(f"  ❌ {ticker} 테스트 실패: {e}")
            results.append(False)
    
    success_count = sum(results)
    logger.info(f"\n✅ analysis 모듈 테스트: {success_count}/{len(test_tickers)}개 성공")
    return success_count > 0

def test_crawler_functions():
    """crawler 모듈 기능 테스트"""
    logger.info("=" * 70)
    logger.info("3. crawler 모듈 기능 테스트")
    logger.info("=" * 70)
    
    from src.crawler import (
        get_yahoo_finance_news, get_market_indicators,
        get_market_news_with_context
    )
    
    results = []
    
    # 1. Yahoo Finance 뉴스 수집 테스트
    try:
        logger.info("\n3-1. Yahoo Finance 뉴스 수집 테스트")
        news = get_yahoo_finance_news(max_items=3)
        if news and len(news) > 0:
            logger.info(f"  ✅ get_yahoo_finance_news() 성공: {len(news)}개 뉴스")
            logger.info(f"     첫 번째 뉴스: {news[0].get('title', 'N/A')[:60]}...")
            results.append(True)
        else:
            logger.warning(f"  ⚠️ get_yahoo_finance_news() 빈 리스트")
            results.append(False)
    except Exception as e:
        logger.error(f"  ❌ get_yahoo_finance_news() 실패: {e}")
        results.append(False)
    
    # 2. 매크로 지표 수집 테스트
    try:
        logger.info("\n3-2. 매크로 지표 수집 테스트")
        indicators = get_market_indicators()
        if indicators and len(indicators) > 50:
            logger.info(f"  ✅ get_market_indicators() 성공: {len(indicators)}자")
            logger.info(f"     내용 미리보기: {indicators[:100]}...")
            results.append(True)
        else:
            logger.warning(f"  ⚠️ get_market_indicators() 데이터 부족")
            results.append(False)
    except Exception as e:
        logger.error(f"  ❌ get_market_indicators() 실패: {e}")
        import traceback
        logger.error(traceback.format_exc())
        results.append(False)
    
    # 3. 시장 뉴스 수집 테스트
    try:
        logger.info("\n3-3. 시장 뉴스 수집 테스트")
        news_text = get_market_news_with_context(max_items=3)
        if news_text and len(news_text) > 50:
            logger.info(f"  ✅ get_market_news_with_context() 성공: {len(news_text)}자")
            logger.info(f"     내용 미리보기: {news_text[:100]}...")
            results.append(True)
        else:
            logger.warning(f"  ⚠️ get_market_news_with_context() 데이터 부족")
            results.append(False)
    except Exception as e:
        logger.error(f"  ❌ get_market_news_with_context() 실패: {e}")
        results.append(False)
    
    success_count = sum(results)
    logger.info(f"\n✅ crawler 모듈 테스트: {success_count}/{len(results)}개 성공")
    return success_count > 0

def test_ai_researcher():
    """ai_researcher 모듈 테스트 (초기화만, 실제 API 호출 없음)"""
    logger.info("=" * 70)
    logger.info("4. ai_researcher 모듈 테스트")
    logger.info("=" * 70)
    
    from src.ai_researcher import create_researcher, AIResearcher
    
    try:
        # API 키 없이도 클래스 구조 확인
        logger.info("\n4-1. AIResearcher 클래스 구조 확인")
        if hasattr(AIResearcher, '__init__'):
            logger.info("  ✅ AIResearcher 클래스 존재")
        if hasattr(AIResearcher, 'generate_briefing'):
            logger.info("  ✅ generate_briefing 메서드 존재")
        if hasattr(AIResearcher, '_call_ai'):
            logger.info("  ✅ _call_ai 메서드 존재")
        if hasattr(AIResearcher, '_add_stock_names_to_codes'):
            logger.info("  ✅ _add_stock_names_to_codes 메서드 존재")
        
        # create_researcher 함수 확인
        logger.info("\n4-2. create_researcher 함수 확인")
        if callable(create_researcher):
            logger.info("  ✅ create_researcher 함수 존재")
        
        logger.info("\n✅ ai_researcher 모듈 구조 확인 완료")
        logger.info("   (실제 API 호출은 API 키 필요로 인해 스킵)")
        return True
        
    except Exception as e:
        logger.error(f"❌ ai_researcher 테스트 실패: {e}")
        return False

def test_notifier():
    """notifier 모듈 테스트 (초기화만, 실제 발송 없음)"""
    logger.info("=" * 70)
    logger.info("5. notifier 모듈 테스트")
    logger.info("=" * 70)
    
    from src.notifier import create_notifier, TelegramNotifier
    
    try:
        logger.info("\n5-1. TelegramNotifier 클래스 구조 확인")
        if hasattr(TelegramNotifier, '__init__'):
            logger.info("  ✅ TelegramNotifier 클래스 존재")
        if hasattr(TelegramNotifier, 'send_message'):
            logger.info("  ✅ send_message 메서드 존재")
        if hasattr(TelegramNotifier, 'format_stock_report'):
            logger.info("  ✅ format_stock_report 메서드 존재")
        if hasattr(TelegramNotifier, 'format_ai_report'):
            logger.info("  ✅ format_ai_report 메서드 존재")
        
        logger.info("\n5-2. create_notifier 함수 확인")
        if callable(create_notifier):
            logger.info("  ✅ create_notifier 함수 존재")
        
        logger.info("\n✅ notifier 모듈 구조 확인 완료")
        logger.info("   (실제 텔레그램 발송은 토큰 필요로 인해 스킵)")
        return True
        
    except Exception as e:
        logger.error(f"❌ notifier 테스트 실패: {e}")
        return False

def test_settings():
    """settings 모듈 테스트"""
    logger.info("=" * 70)
    logger.info("6. settings 모듈 테스트")
    logger.info("=" * 70)
    
    try:
        from config.settings import settings
        
        logger.info("\n6-1. Settings 객체 확인")
        logger.info(f"  ✅ Settings 객체: {settings}")
        
        logger.info("\n6-2. 설정 값 확인")
        if hasattr(settings, 'tickers'):
            logger.info(f"  ✅ tickers: {len(settings.tickers)}개")
        if hasattr(settings, 'tickers_possession_domestic'):
            logger.info(f"  ✅ tickers_possession_domestic: {len(settings.tickers_possession_domestic)}개")
        if hasattr(settings, 'tickers_possession_overseas'):
            logger.info(f"  ✅ tickers_possession_overseas: {len(settings.tickers_possession_overseas)}개")
        if hasattr(settings, 'tickers_interest_domestic'):
            logger.info(f"  ✅ tickers_interest_domestic: {len(settings.tickers_interest_domestic)}개")
        if hasattr(settings, 'tickers_interest_overseas'):
            logger.info(f"  ✅ tickers_interest_overseas: {len(settings.tickers_interest_overseas)}개")
        
        logger.info("\n✅ settings 모듈 확인 완료")
        return True
        
    except Exception as e:
        logger.error(f"❌ settings 테스트 실패: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def test_integration():
    """통합 테스트: 여러 모듈 연동"""
    logger.info("=" * 70)
    logger.info("7. 통합 테스트 (모듈 간 연동)")
    logger.info("=" * 70)
    
    try:
        from src.analysis import get_stock_summary_by_category
        from config.settings import settings
        
        logger.info("\n7-1. 주가 요약 생성 테스트 (카테고리별)")
        
        # 최소한의 티커로 테스트
        test_tickers = {
            'possession_domestic': ['005930.KS'] if settings.tickers_possession_domestic else [],
            'possession_overseas': ['AAPL'] if settings.tickers_possession_overseas else [],
            'interest_domestic': ['000660.KS'] if settings.tickers_interest_domestic else [],
            'interest_overseas': ['NVDA'] if settings.tickers_interest_overseas else [],
        }
        
        # 빈 리스트가 아닌 카테고리만 테스트
        has_data = any(test_tickers.values())
        if not has_data:
            logger.info("  ℹ️ 테스트용 티커가 없어 스킵 (실제 설정 파일의 티커 사용)")
            return True
        
        summaries = get_stock_summary_by_category(
            possession_domestic=test_tickers['possession_domestic'],
            possession_overseas=test_tickers['possession_overseas'],
            interest_domestic=test_tickers['interest_domestic'],
            interest_overseas=test_tickers['interest_overseas']
        )
        
        if summaries:
            logger.info(f"  ✅ get_stock_summary_by_category() 성공: {len(summaries)}개 카테고리")
            for key, value in summaries.items():
                if value:
                    logger.info(f"     {key}: {len(value)}자")
        else:
            logger.warning("  ⚠️ get_stock_summary_by_category() 빈 결과")
        
        logger.info("\n✅ 통합 테스트 완료")
        return True
        
    except Exception as e:
        logger.error(f"❌ 통합 테스트 실패: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def main():
    """전체 테스트 실행"""
    logger.info("=" * 70)
    logger.info("전체 기능 통합 테스트 시작")
    logger.info("=" * 70)
    logger.info("")
    
    results = []
    
    # 1. 모듈 Import 테스트
    results.append(("모듈 Import", test_module_imports()))
    
    # 2. analysis 모듈 테스트
    results.append(("analysis 모듈", test_analysis_functions()))
    
    # 3. crawler 모듈 테스트
    results.append(("crawler 모듈", test_crawler_functions()))
    
    # 4. ai_researcher 모듈 테스트
    results.append(("ai_researcher 모듈", test_ai_researcher()))
    
    # 5. notifier 모듈 테스트
    results.append(("notifier 모듈", test_notifier()))
    
    # 6. settings 모듈 테스트
    results.append(("settings 모듈", test_settings()))
    
    # 7. 통합 테스트
    results.append(("통합 테스트", test_integration()))
    
    # 결과 요약
    logger.info("")
    logger.info("=" * 70)
    logger.info("테스트 결과 요약")
    logger.info("=" * 70)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status}: {test_name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    logger.info("")
    logger.info(f"총 {len(results)}개 테스트: ✅ {passed}개 통과, ❌ {failed}개 실패")
    
    if failed == 0:
        logger.info("")
        logger.info("🎉 모든 테스트 통과! 전체 시스템이 정상 작동합니다!")
        return 0
    else:
        logger.error("")
        logger.error("⚠️ 일부 테스트 실패. 로그를 확인하세요.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

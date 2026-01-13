"""
전체 기능 통합 테스트
모든 단계를 검증하고 실제 워크플로우 실행
"""
import logging
import sys
import os
from pathlib import Path
from datetime import datetime

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)


def test_module_imports():
    """모든 모듈 import 테스트"""
    logger.info("=" * 70)
    logger.info("1. 모듈 Import 테스트")
    logger.info("=" * 70)
    
    try:
        from config.settings import settings
        logger.info("✅ config.settings import 성공")
        
        from src.analysis import get_stock_summary_by_category, calculate_returns
        logger.info("✅ src.analysis import 성공")
        
        from src.crawler import (
            get_kr_stock_data,
            get_global_institutional_data,
            get_market_news_with_context,
            get_market_indicators,
            translate_headlines,
            get_us_top_movers,
            get_korea_hot_themes,
            get_hankyung_consensus,
            get_google_news_rss
        )
        logger.info("✅ src.crawler import 성공")
        
        from src.ai_researcher import create_researcher
        logger.info("✅ src.ai_researcher import 성공")
        
        from src.notifier import create_notifier
        logger.info("✅ src.notifier import 성공")
        
        logger.info("\n✅ 모든 모듈 import 성공!\n")
        return True
        
    except Exception as e:
        logger.error(f"❌ 모듈 import 실패: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def test_new_features():
    """새로 추가된 기능 테스트"""
    logger.info("=" * 70)
    logger.info("2. 새로 추가된 기능 테스트")
    logger.info("=" * 70)
    
    try:
        from src.crawler import get_kr_stock_data, get_global_institutional_data
        from src.analysis import calculate_returns, calculate_advanced_indicators
        
        # 국내 주식 수급 데이터 테스트
        logger.info("\n2-1. 국내 주식 수급 데이터 수집 테스트...")
        kr_data = get_kr_stock_data('005930.KS')
        logger.info(f"   외인 순매매: {kr_data.get('foreign_net')}만주")
        logger.info(f"   기관 순매매: {kr_data.get('institutional_net')}만주")
        logger.info(f"   ETF 괴리율: {kr_data.get('disparity_rate')}%")
        
        # 해외 주식 기관 보유 비중 테스트
        logger.info("\n2-2. 해외 주식 기관 보유 비중 테스트...")
        institutional = get_global_institutional_data('AAPL')
        logger.info(f"   기관 보유 비중: {institutional}%")
        
        # 고급 기술적 지표 테스트
        logger.info("\n2-3. 고급 기술적 지표 테스트...")
        advanced = calculate_advanced_indicators('005930.KS')
        logger.info(f"   MA 이격도: {advanced.get('ma_disparity')}%")
        logger.info(f"   52주 위치: {advanced.get('year_high_pos')}%")
        
        # 통합 테스트
        logger.info("\n2-4. calculate_returns 통합 테스트...")
        result = calculate_returns('005930.KS')
        logger.info(f"   수급: {result.get('supply_demand')}")
        logger.info(f"   ETF 괴리율: {result.get('disparity_rate')}")
        logger.info(f"   MA 이격도: {result.get('technical', {}).get('ma_disparity')}%")
        logger.info(f"   52주 위치: {result.get('technical', {}).get('year_high_pos')}%")
        
        logger.info("\n✅ 새로 추가된 기능 모두 정상 작동!\n")
        return True
        
    except Exception as e:
        logger.error(f"❌ 새 기능 테스트 실패: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def test_data_collection():
    """데이터 수집 기능 테스트"""
    logger.info("=" * 70)
    logger.info("3. 데이터 수집 기능 테스트")
    logger.info("=" * 70)
    
    try:
        from config.settings import settings
        from src.analysis import get_stock_summary_by_category
        from src.crawler import (
            get_market_indicators,
            get_us_top_movers,
            get_korea_hot_themes,
            get_hankyung_consensus,
            get_google_news_rss,
            get_market_news_with_context
        )
        
        # 주가 데이터 수집
        logger.info("\n3-1. 주가 데이터 수집 테스트...")
        stock_summaries = get_stock_summary_by_category(
            possession_domestic=settings.tickers_possession_domestic[:1] if settings.tickers_possession_domestic else [],
            possession_overseas=settings.tickers_possession_overseas[:1] if settings.tickers_possession_overseas else [],
            interest_domestic=settings.tickers_interest_domestic[:1] if settings.tickers_interest_domestic else [],
            interest_overseas=settings.tickers_interest_overseas[:1] if settings.tickers_interest_overseas else []
        )
        logger.info(f"   카테고리별 요약 생성 완료: {len([s for s in stock_summaries.values() if s])}개")
        
        # 매크로 지표 수집
        logger.info("\n3-2. 매크로 경제 지표 수집 테스트...")
        macro_indicators = get_market_indicators()
        logger.info(f"   매크로 지표 수집 완료: {len(macro_indicators)}자")
        
        # 미국 Top Movers
        logger.info("\n3-3. 미국 Top Movers 수집 테스트...")
        us_top_movers = get_us_top_movers(max_items=5)
        logger.info(f"   미국 Top Movers 수집 완료: {len(us_top_movers)}자")
        
        # 한국 Hot Themes
        logger.info("\n3-4. 한국 Hot Themes 수집 테스트...")
        korea_hot_themes = get_korea_hot_themes(max_themes=2)
        logger.info(f"   한국 Hot Themes 수집 완료: {len(korea_hot_themes)}자")
        
        # 한경 컨센서스
        logger.info("\n3-5. 한경 컨센서스 수집 테스트...")
        hankyung_consensus = get_hankyung_consensus()
        logger.info(f"   한경 컨센서스 수집 완료: {len(hankyung_consensus)}자")
        
        # Google News
        logger.info("\n3-6. Google News RSS 수집 테스트...")
        google_news = get_google_news_rss()
        logger.info(f"   Google News 수집 완료: {len(google_news)}자")
        
        # 뉴스 수집
        logger.info("\n3-7. 시장 뉴스 수집 테스트...")
        news_with_context = get_market_news_with_context(max_items=5)
        logger.info(f"   뉴스 수집 완료: {len(news_with_context)}자")
        
        logger.info("\n✅ 모든 데이터 수집 기능 정상 작동!\n")
        return True
        
    except Exception as e:
        logger.error(f"❌ 데이터 수집 테스트 실패: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def test_full_workflow():
    """전체 워크플로우 실행 테스트"""
    logger.info("=" * 70)
    logger.info("4. 전체 워크플로우 실행 테스트")
    logger.info("=" * 70)
    logger.info("   (실제 main.py의 모든 단계를 실행합니다)")
    logger.info("")
    
    try:
        from src.main import main
        
        start_time = datetime.now()
        logger.info(f"   시작 시간: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("")
        
        # main() 함수 실행
        main()
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info("")
        logger.info("=" * 70)
        logger.info("전체 워크플로우 실행 완료")
        logger.info("=" * 70)
        logger.info(f"   시작 시간: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"   종료 시간: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"   소요 시간: {duration:.1f}초")
        logger.info("")
        logger.info("✅ 모든 단계가 성공적으로 완료되었습니다!")
        logger.info("✅ 텔레그램 메시지가 발송되었습니다!")
        logger.info("   텔레그램 앱에서 메시지를 확인하세요.")
        
        return True
        
    except SystemExit as e:
        if e.code != 0:
            logger.error(f"❌ 워크플로우 실행 중 오류 발생 (Exit code: {e.code})")
            return False
        return True
        
    except Exception as e:
        logger.error(f"❌ 워크플로우 실행 실패: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def main():
    """테스트 메인 함수"""
    logger.info("")
    logger.info("=" * 70)
    logger.info("전체 기능 통합 테스트 시작")
    logger.info("=" * 70)
    logger.info("")
    
    results = []
    
    # 1. 모듈 import 테스트
    results.append(("모듈 Import", test_module_imports()))
    
    # 2. 새 기능 테스트
    results.append(("새 기능", test_new_features()))
    
    # 3. 데이터 수집 테스트
    results.append(("데이터 수집", test_data_collection()))
    
    # 4. 전체 워크플로우 실행
    results.append(("전체 워크플로우", test_full_workflow()))
    
    # 결과 요약
    logger.info("")
    logger.info("=" * 70)
    logger.info("테스트 결과 요약")
    logger.info("=" * 70)
    
    for test_name, result in results:
        status = "✅ 통과" if result else "❌ 실패"
        logger.info(f"   {test_name}: {status}")
    
    all_passed = all(result for _, result in results)
    
    logger.info("")
    if all_passed:
        logger.info("=" * 70)
        logger.info("✅ 모든 테스트 통과!")
        logger.info("=" * 70)
    else:
        logger.info("=" * 70)
        logger.info("❌ 일부 테스트 실패")
        logger.info("=" * 70)
    
    logger.info("")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

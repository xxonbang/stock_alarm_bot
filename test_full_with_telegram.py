#!/usr/bin/env python3
"""
전체 기능 통합 테스트 (실제 텔레그램 메시지 발송 포함)
main.py의 전체 워크플로우를 실행하여 모든 기능을 테스트
"""
import sys
import logging
import os
from pathlib import Path
from datetime import datetime
import pytz

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_full_workflow():
    """전체 워크플로우 테스트 (실제 메시지 발송 포함)"""
    logger.info("=" * 70)
    logger.info("전체 기능 통합 테스트 (실제 텔레그램 메시지 발송 포함)")
    logger.info("=" * 70)
    logger.info("")
    
    # 설정 확인
    try:
        from config.settings import settings
        logger.info("1. 설정 확인")
        logger.info(f"   ✅ 티커: {len(settings.tickers)}개")
        logger.info(f"   ✅ Telegram Token: {'설정됨' if settings.telegram_token else '없음'}")
        logger.info(f"   ✅ Chat ID: {'설정됨' if settings.chat_id else '없음'}")
        logger.info(f"   ✅ Google API Key: {'설정됨' if settings.google_api_key else '없음'}")
        
        if not settings.telegram_token or not settings.chat_id:
            logger.error("❌ 텔레그램 설정이 없습니다. 테스트를 중단합니다.")
            return False
        
        logger.info("")
    except Exception as e:
        logger.error(f"❌ 설정 로드 실패: {e}")
        return False
    
    # main.py의 전체 워크플로우 실행
    try:
        logger.info("2. 전체 워크플로우 실행 시작")
        logger.info("   (main.py의 모든 단계를 실행합니다)")
        logger.info("")
        
        # main.py의 main() 함수 직접 호출
        from src.main import main
        
        # 실행 시작 시간 기록
        start_time = datetime.now()
        logger.info(f"   시작 시간: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("")
        
        # main() 함수 실행
        try:
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
            # main()에서 sys.exit(1)이 호출된 경우
            if e.code != 0:
                logger.error("")
                logger.error("❌ 워크플로우 실행 중 오류 발생")
                logger.error(f"   Exit code: {e.code}")
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
    logger.info("실제 텔레그램 메시지 발송 포함")
    logger.info("=" * 70)
    logger.info("")
    
    # 경고 메시지
    logger.warning("⚠️  이 테스트는 실제로 텔레그램 메시지를 발송합니다!")
    logger.warning("⚠️  API 호출이 발생하므로 비용이 발생할 수 있습니다.")
    logger.info("")
    
    result = test_full_workflow()
    
    logger.info("")
    logger.info("=" * 70)
    logger.info("테스트 결과")
    logger.info("=" * 70)
    
    if result:
        logger.info("✅ 전체 기능 테스트 성공!")
        logger.info("✅ 모든 모듈이 정상 작동합니다!")
        logger.info("✅ 텔레그램 메시지가 발송되었습니다!")
        return 0
    else:
        logger.error("❌ 전체 기능 테스트 실패!")
        logger.error("   로그를 확인하여 문제를 해결하세요.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
텔레그램 발송 테스트
실제로 메시지를 발송하여 확인
"""
import sys
import logging
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_telegram_send():
    """텔레그램 메시지 발송 테스트"""
    logger.info("=" * 70)
    logger.info("텔레그램 메시지 발송 테스트")
    logger.info("=" * 70)
    
    try:
        from config.settings import settings
        from src.notifier import create_notifier
        
        # 설정 확인
        logger.info("\n1. 설정 확인")
        if not hasattr(settings, 'telegram_token') or not settings.telegram_token:
            logger.error("❌ TELEGRAM_TOKEN이 설정되지 않았습니다.")
            logger.error("   .env 파일 또는 환경변수에 TELEGRAM_TOKEN을 설정하세요.")
            return False
        
        if not hasattr(settings, 'chat_id') or not settings.chat_id:
            logger.error("❌ CHAT_ID가 설정되지 않았습니다.")
            logger.error("   .env 파일 또는 환경변수에 CHAT_ID를 설정하세요.")
            return False
        
        logger.info("  ✅ Telegram Token: 설정됨")
        logger.info("  ✅ Chat ID: 설정됨")
        
        # Notifier 생성
        logger.info("\n2. Notifier 생성")
        notifier = create_notifier(settings.telegram_token, settings.chat_id)
        logger.info("  ✅ Notifier 생성 성공")
        
        # 테스트 메시지 발송
        logger.info("\n3. 테스트 메시지 발송")
        test_message = """<b>🧪 테스트 메시지</b>

이것은 전체 기능 테스트 후 텔레그램 발송 확인을 위한 테스트 메시지입니다.

✅ 시스템 상태: 정상 작동
✅ yfinance 1.0.0: 정상 작동
✅ google-genai: 정상 작동
✅ 모든 모듈: 정상 작동

테스트 시간: 2026-01-12"""
        
        result = notifier.send_message(test_message)
        
        if result:
            logger.info("  ✅ 텔레그램 메시지 발송 성공!")
            logger.info("     텔레그램 앱에서 메시지를 확인하세요.")
            return True
        else:
            logger.error("  ❌ 텔레그램 메시지 발송 실패")
            logger.error("     토큰 또는 Chat ID를 확인하세요.")
            return False
        
    except Exception as e:
        logger.error(f"❌ 텔레그램 테스트 실패: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    success = test_telegram_send()
    sys.exit(0 if success else 1)

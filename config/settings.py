"""
설정 로더 모듈
환경변수와 config.yaml을 로드하여 사용
"""
import os
import logging
import yaml
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# .env 파일 로드 (로컬 개발용)
try:
    from dotenv import load_dotenv
    # 프로젝트 루트의 .env 파일 로드
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    # python-dotenv가 설치되지 않은 경우 무시 (GitHub Actions에서는 환경변수 사용)
    pass


def load_config():
    """config.yaml 파일을 로드"""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_env_var(key: str, default: str = None) -> str:
    """환경변수에서 값을 가져옴 (GitHub Secrets 또는 .env 파일)"""
    value = os.getenv(key, default)
    if value is None:
        raise ValueError(f"환경변수 {key}가 설정되지 않았습니다. GitHub Secrets 또는 .env 파일을 확인하세요.")
    return value


class Settings:
    """애플리케이션 설정 클래스"""
    
    def __init__(self):
        config = load_config()
        
        # 카테고리별로 티커 저장 (빈 리스트는 None 또는 빈 리스트로 유지)
        self.tickers_possession_domestic = config.get('tickers_possession_domestic', []) or []
        self.tickers_possession_overseas = config.get('tickers_possession_overseas', []) or []
        self.tickers_interest_domestic = config.get('tickers_interest_domestic', []) or []
        self.tickers_interest_overseas = config.get('tickers_interest_overseas', []) or []
        
        # 전체 티커 리스트 (분석용)
        all_tickers = []
        all_tickers.extend(self.tickers_possession_domestic)
        all_tickers.extend(self.tickers_possession_overseas)
        all_tickers.extend(self.tickers_interest_domestic)
        all_tickers.extend(self.tickers_interest_overseas)
        
        # 중복 제거 및 정렬
        self.tickers = sorted(list(set(all_tickers)))
        self.schedule_times = config.get('schedule_times', [])
        
        # API Keys (환경변수에서 로드)
        # 주의: 실제 키는 GitHub Secrets 또는 .env 파일에 저장
        self.telegram_token = get_env_var('TELEGRAM_TOKEN')
        self.chat_id = get_env_var('CHAT_ID')
        
        # Google API Keys (01, 02, 03으로 구분)
        # 01번 키 (필수), 02/03번 키 (선택적, fallback용)
        self.google_api_key_01 = get_env_var('GOOGLE_API_KEY_01')
        # 02번, 03번 키는 선택적 (fallback용이므로 없어도 됨)
        self.google_api_key_02 = os.getenv('GOOGLE_API_KEY_02', None)
        self.google_api_key_03 = os.getenv('GOOGLE_API_KEY_03', None)

        # 기본값은 01번 키 (하위 호환성)
        self.google_api_key = self.google_api_key_01

        # 사용 가능한 모든 API 키 리스트 (fallback 순서대로)
        self.google_api_keys = [self.google_api_key_01]
        if self.google_api_key_02:
            self.google_api_keys.append(self.google_api_key_02)
        if self.google_api_key_03:
            self.google_api_keys.append(self.google_api_key_03)
        
        # KRX API Key (optional, 없어도 기존 기능 동작)
        self.krx_api_key = os.getenv('KRX_API_KEY', None)
        
        # KRX API 유효기간 (optional, 환경변수에서 로드)
        # 형식: "YYYY-MM-DD" (예: "2027-01-12")
        krx_expiry_str = os.getenv('KRX_API_KEY_EXPIRY', None)
        self.krx_api_key_expiry = None
        if krx_expiry_str:
            try:
                from datetime import datetime
                self.krx_api_key_expiry = datetime.strptime(krx_expiry_str, '%Y-%m-%d').date()
            except ValueError:
                # logger가 아직 초기화되지 않았을 수 있으므로 print 사용
                import sys
                print(f"⚠️ KRX_API_KEY_EXPIRY 형식 오류: {krx_expiry_str} (YYYY-MM-DD 형식 필요)", file=sys.stderr)

        # 듀얼 소스 시스템 활성화 여부 (환경변수 USE_DUAL_SOURCE로 제어)
        # 기본값: True (듀얼 소스 사용, 실패 시 기존 방식으로 fallback)
        use_dual_source_str = os.getenv('USE_DUAL_SOURCE', 'true').lower()
        self.use_dual_source = use_dual_source_str in ('true', '1', 'yes', 'on')

        # === 추가 데이터 소스 API 키 (선택사항) ===

        # 한국투자증권 (KIS) API (한국 주식 수급 데이터)
        # https://apiportal.koreainvestment.com 에서 발급
        self.kis_app_key = os.getenv('KIS_APP_KEY', None)
        self.kis_app_secret = os.getenv('KIS_APP_SECRET', None)

        # Twelve Data API (미국 주식 주요 Fallback)
        # https://twelvedata.com 에서 무료 발급 (800 calls/day)
        self.twelve_data_api_key = os.getenv('TWELVE_DATA_API_KEY', None)

        # Finnhub API (미국 주식 Fallback)
        # https://finnhub.io 에서 무료 발급 (60 calls/min)
        self.finnhub_api_key = os.getenv('FINNHUB_API_KEY', None)

        # Financial Modeling Prep (FMP) API (미국 주식 Fallback, 기관보유 전용)
        # https://financialmodelingprep.com 에서 발급 (무료: 250 calls/day)
        self.fmp_api_key = os.getenv('FMP_API_KEY', None)
    
    def __repr__(self):
        return f"Settings(tickers={len(self.tickers)}개, schedule_times={len(self.schedule_times)}개)"


# 싱글톤 인스턴스
settings = Settings()


class GoogleAPIKeyManager:
    """
    Google API 키 관리자 (세션 전체에서 공유)

    - 여러 API 키를 순차적으로 fallback
    - 세션 동안 성공한 키를 기억하여 불필요한 재시도 방지
    - AIResearcher, AgenticScreenshotSource 등에서 공유 사용
    """

    _instance: Optional['GoogleAPIKeyManager'] = None

    def __new__(cls):
        """싱글톤 패턴"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._api_keys = settings.google_api_keys.copy()
        self._current_index = 0
        self._exhausted_keys = set()  # 할당량 초과된 키 인덱스
        self._initialized = True

        logger.info(f"🔑 Google API 키 매니저 초기화: {len(self._api_keys)}개 키 사용 가능")

    @property
    def current_key(self) -> str:
        """현재 사용 중인 API 키"""
        return self._api_keys[self._current_index]

    @property
    def current_key_number(self) -> int:
        """현재 사용 중인 키 번호 (1부터 시작)"""
        return self._current_index + 1

    @property
    def total_keys(self) -> int:
        """전체 키 개수"""
        return len(self._api_keys)

    @property
    def available_keys_count(self) -> int:
        """사용 가능한 키 개수 (소진되지 않은)"""
        return len(self._api_keys) - len(self._exhausted_keys)

    def get_current_key(self) -> Tuple[str, int]:
        """
        현재 사용할 API 키 반환

        Returns:
            (API 키, 키 번호)
        """
        return self.current_key, self.current_key_number

    def mark_key_exhausted(self, key_index: Optional[int] = None) -> bool:
        """
        현재 키를 할당량 초과로 표시하고 다음 키로 전환

        Args:
            key_index: 소진된 키 인덱스 (None이면 현재 키)

        Returns:
            다음 키로 전환 성공 여부
        """
        if key_index is None:
            key_index = self._current_index

        self._exhausted_keys.add(key_index)
        logger.warning(f"⚠️ API 키 #{key_index + 1:02d} 할당량 초과로 표시됨")

        return self._switch_to_next_available()

    def _switch_to_next_available(self) -> bool:
        """
        다음 사용 가능한 키로 전환

        Returns:
            전환 성공 여부
        """
        # 다음 사용 가능한 키 찾기
        for i in range(self._current_index + 1, len(self._api_keys)):
            if i not in self._exhausted_keys:
                old_index = self._current_index
                self._current_index = i
                logger.info(f"🔄 API 키 전환: #{old_index + 1:02d} → #{i + 1:02d}")
                print(f"🔄 API 키 전환: #{old_index + 1:02d} → #{i + 1:02d}")
                return True

        logger.error(f"❌ 모든 API 키({len(self._api_keys)}개) 할당량 초과")
        return False

    def reset(self):
        """키 상태 초기화 (새 세션 시작 시)"""
        self._current_index = 0
        self._exhausted_keys.clear()
        logger.info("🔑 API 키 매니저 리셋: 모든 키 사용 가능")

    def is_all_exhausted(self) -> bool:
        """모든 키가 소진되었는지 확인"""
        return len(self._exhausted_keys) >= len(self._api_keys)


# 전역 API 키 매니저 인스턴스
def get_api_key_manager() -> GoogleAPIKeyManager:
    """Google API 키 매니저 싱글톤 인스턴스 반환"""
    return GoogleAPIKeyManager()


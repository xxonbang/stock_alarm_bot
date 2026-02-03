"""
Supabase 기반 API 자격증명 관리자

타 프로젝트와 API 키를 공유하기 위해 Supabase를 사용합니다.
환경변수 fallback을 지원하여 Supabase 연결 실패 시에도 동작합니다.

테이블 구조 (api_credentials):
- service_name: 서비스 이름 (예: 'kis')
- credential_type: 자격증명 타입 (예: 'app_key', 'app_secret', 'access_token', 'token_expires_at')
- credential_value: 자격증명 값
- is_active: 활성 상태

KIS 토큰 공유:
- access_token: OAuth 액세스 토큰 (24시간 유효)
- token_expires_at: 토큰 만료 시간 (Unix timestamp)
- 여러 프로젝트에서 동일한 토큰을 공유하여 1일 1회 발급 제한 준수
"""
import os
import logging
import time
from typing import Optional, Dict, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class KISCredentials:
    """KIS API 자격증명"""
    app_key: str
    app_secret: str
    source: str  # 'supabase' or 'env'


@dataclass
class KISToken:
    """KIS API 액세스 토큰 (여러 프로젝트 간 공유)"""
    access_token: str
    expires_at: float  # Unix timestamp
    source: str  # 'supabase' or 'local'

    @property
    def is_valid(self) -> bool:
        """토큰 유효성 확인 (만료 5분 전까지 유효)"""
        return time.time() < (self.expires_at - 300)

    @property
    def remaining_hours(self) -> int:
        """남은 유효시간 (시간)"""
        return max(0, int((self.expires_at - time.time()) / 3600))


class SupabaseCredentialsManager:
    """
    Supabase 기반 자격증명 관리자 (싱글톤)

    - Supabase에서 API 키 조회
    - 환경변수 fallback 지원
    - 캐싱으로 반복 조회 방지
    """

    _instance: Optional['SupabaseCredentialsManager'] = None

    # Supabase 프로젝트 정보
    DEFAULT_SUPABASE_URL = "https://fyklcplybyfrfryopzvx.supabase.co"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._supabase_url: Optional[str] = None
        self._supabase_key: Optional[str] = None
        self._client = None
        self._cache: Dict[str, Dict[str, str]] = {}  # {service_name: {credential_type: value}}
        self._initialized = True
        self._connection_failed = False

        self._init_supabase()

    def _init_supabase(self):
        """Supabase 클라이언트 초기화"""
        try:
            # 환경변수에서 Supabase 설정 로드
            self._supabase_url = os.getenv('SUPABASE_URL', self.DEFAULT_SUPABASE_URL)
            self._supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

            if not self._supabase_key:
                logger.info("SUPABASE_SERVICE_ROLE_KEY 미설정 - 환경변수 모드로 동작")
                self._connection_failed = True
                return

            from supabase import create_client, Client
            self._client: Client = create_client(self._supabase_url, self._supabase_key)
            logger.info(f"✅ Supabase 클라이언트 초기화 완료: {self._supabase_url}")

        except ImportError:
            logger.warning("supabase 패키지 미설치 - 환경변수 모드로 동작")
            self._connection_failed = True
        except Exception as e:
            logger.warning(f"Supabase 초기화 실패: {e} - 환경변수 모드로 동작")
            self._connection_failed = True

    def _fetch_credentials_from_supabase(self, service_name: str) -> Dict[str, str]:
        """
        Supabase에서 자격증명 조회

        Args:
            service_name: 서비스 이름 (예: 'kis')

        Returns:
            {credential_type: credential_value} 딕셔너리
        """
        if self._connection_failed or not self._client:
            return {}

        try:
            response = self._client.table('api_credentials') \
                .select('credential_type, credential_value') \
                .eq('service_name', service_name) \
                .eq('environment', 'production') \
                .eq('is_active', True) \
                .execute()

            if not response.data:
                logger.debug(f"Supabase에서 {service_name} 자격증명 없음")
                return {}

            result = {}
            for row in response.data:
                result[row['credential_type']] = row['credential_value']

            logger.info(f"✅ Supabase에서 {service_name} 자격증명 로드: {list(result.keys())}")
            return result

        except Exception as e:
            logger.warning(f"Supabase 조회 실패 ({service_name}): {e}")
            return {}

    def get_kis_credentials(self) -> Optional[KISCredentials]:
        """
        KIS API 자격증명 조회

        우선순위:
        1. 캐시된 Supabase 데이터
        2. Supabase에서 새로 조회
        3. 환경변수 fallback

        Returns:
            KISCredentials 또는 None
        """
        # 1. 캐시 확인
        if 'kis' in self._cache:
            cached = self._cache['kis']
            if 'app_key' in cached and 'app_secret' in cached:
                return KISCredentials(
                    app_key=cached['app_key'],
                    app_secret=cached['app_secret'],
                    source='supabase (cached)'
                )

        # 2. Supabase에서 조회
        if not self._connection_failed:
            credentials = self._fetch_credentials_from_supabase('kis')
            if credentials.get('app_key') and credentials.get('app_secret'):
                self._cache['kis'] = credentials
                return KISCredentials(
                    app_key=credentials['app_key'],
                    app_secret=credentials['app_secret'],
                    source='supabase'
                )

        # 3. 환경변수 fallback
        app_key = os.getenv('KIS_APP_KEY')
        app_secret = os.getenv('KIS_APP_SECRET')

        if app_key and app_secret:
            logger.info("KIS 자격증명: 환경변수에서 로드")
            return KISCredentials(
                app_key=app_key,
                app_secret=app_secret,
                source='env'
            )

        logger.warning("KIS 자격증명을 찾을 수 없음 (Supabase 및 환경변수 모두 없음)")
        return None

    def update_kis_credentials(self, app_key: str, app_secret: str) -> bool:
        """
        KIS API 자격증명 업데이트 (Supabase에 저장)

        Args:
            app_key: KIS 앱 키
            app_secret: KIS 앱 시크릿

        Returns:
            성공 여부
        """
        if self._connection_failed or not self._client:
            logger.warning("Supabase 연결 불가 - 자격증명 업데이트 실패")
            return False

        try:
            # app_key 업데이트 (upsert)
            self._client.table('api_credentials').upsert({
                'service_name': 'kis',
                'credential_type': 'app_key',
                'credential_value': app_key,
                'environment': 'production',
                'is_active': True,
            }, on_conflict='service_name,credential_type,environment').execute()

            # app_secret 업데이트 (upsert)
            self._client.table('api_credentials').upsert({
                'service_name': 'kis',
                'credential_type': 'app_secret',
                'credential_value': app_secret,
                'environment': 'production',
                'is_active': True,
            }, on_conflict='service_name,credential_type,environment').execute()

            # 캐시 갱신
            self._cache['kis'] = {
                'app_key': app_key,
                'app_secret': app_secret,
            }

            logger.info("✅ KIS 자격증명 Supabase 업데이트 완료")
            return True

        except Exception as e:
            logger.error(f"KIS 자격증명 업데이트 실패: {e}")
            return False

    # ===== KIS 토큰 공유 (여러 프로젝트 간) =====

    def get_kis_token(self) -> Optional[KISToken]:
        """
        Supabase에서 공유 KIS 토큰 조회

        여러 프로젝트에서 동일한 토큰을 공유하여 1일 1회 발급 제한을 준수합니다.

        Returns:
            KISToken (유효한 경우) 또는 None (없거나 만료됨)
        """
        if self._connection_failed or not self._client:
            return None

        try:
            # Supabase에서 토큰 정보 조회
            credentials = self._fetch_credentials_from_supabase('kis')

            access_token = credentials.get('access_token')
            expires_at_str = credentials.get('token_expires_at')

            if not access_token or not expires_at_str:
                logger.debug("Supabase에 KIS 토큰 없음")
                return None

            try:
                expires_at = float(expires_at_str)
            except (ValueError, TypeError):
                logger.warning(f"KIS 토큰 만료시간 파싱 실패: {expires_at_str}")
                return None

            token = KISToken(
                access_token=access_token,
                expires_at=expires_at,
                source='supabase'
            )

            if token.is_valid:
                logger.info(f"✅ Supabase에서 KIS 토큰 로드 (남은 유효시간: ~{token.remaining_hours}시간)")
                return token
            else:
                logger.info("⏰ Supabase의 KIS 토큰 만료됨")
                return None

        except Exception as e:
            logger.warning(f"Supabase KIS 토큰 조회 실패: {e}")
            return None

    def update_kis_token(self, access_token: str, expires_at: float) -> bool:
        """
        KIS 토큰을 Supabase에 업데이트 (여러 프로젝트 간 공유)

        토큰 갱신 시 호출하여 다른 프로젝트에서도 동일한 토큰을 사용할 수 있게 합니다.

        Args:
            access_token: 액세스 토큰
            expires_at: 만료 시간 (Unix timestamp)

        Returns:
            성공 여부
        """
        if self._connection_failed or not self._client:
            logger.debug("Supabase 연결 불가 - 토큰 업데이트 스킵")
            return False

        try:
            # access_token 업데이트
            self._client.table('api_credentials').upsert({
                'service_name': 'kis',
                'credential_type': 'access_token',
                'credential_value': access_token,
                'environment': 'production',
                'is_active': True,
            }, on_conflict='service_name,credential_type,environment').execute()

            # token_expires_at 업데이트
            self._client.table('api_credentials').upsert({
                'service_name': 'kis',
                'credential_type': 'token_expires_at',
                'credential_value': str(expires_at),
                'environment': 'production',
                'is_active': True,
            }, on_conflict='service_name,credential_type,environment').execute()

            # 캐시 갱신
            if 'kis' not in self._cache:
                self._cache['kis'] = {}
            self._cache['kis']['access_token'] = access_token
            self._cache['kis']['token_expires_at'] = str(expires_at)

            logger.info("✅ KIS 토큰 Supabase 업데이트 완료 (여러 프로젝트 공유)")
            return True

        except Exception as e:
            logger.error(f"KIS 토큰 Supabase 업데이트 실패: {e}")
            return False

    def invalidate_kis_token(self) -> bool:
        """
        Supabase의 KIS 토큰 무효화

        토큰이 더 이상 유효하지 않을 때 호출하여
        다른 프로젝트에서도 새 토큰을 발급받도록 합니다.

        Returns:
            성공 여부
        """
        if self._connection_failed or not self._client:
            return False

        try:
            # access_token 비활성화
            self._client.table('api_credentials').update({
                'is_active': False,
            }).eq('service_name', 'kis').eq('credential_type', 'access_token').eq('environment', 'production').execute()

            # token_expires_at 비활성화
            self._client.table('api_credentials').update({
                'is_active': False,
            }).eq('service_name', 'kis').eq('credential_type', 'token_expires_at').eq('environment', 'production').execute()

            # 캐시에서 토큰 제거
            if 'kis' in self._cache:
                self._cache['kis'].pop('access_token', None)
                self._cache['kis'].pop('token_expires_at', None)

            logger.info("🔄 Supabase KIS 토큰 무효화 완료")
            return True

        except Exception as e:
            logger.error(f"KIS 토큰 무효화 실패: {e}")
            return False

    def clear_cache(self, service_name: Optional[str] = None):
        """캐시 초기화"""
        if service_name:
            self._cache.pop(service_name, None)
        else:
            self._cache.clear()
        logger.debug("Supabase 자격증명 캐시 초기화")

    @property
    def is_supabase_available(self) -> bool:
        """Supabase 연결 가능 여부"""
        return not self._connection_failed and self._client is not None


# 싱글톤 인스턴스 접근자
def get_supabase_credentials_manager() -> SupabaseCredentialsManager:
    """Supabase 자격증명 관리자 싱글톤 인스턴스 반환"""
    return SupabaseCredentialsManager()

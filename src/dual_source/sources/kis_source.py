"""
한국투자증권 Open API (KIS) 데이터 소스

실시간 시세, 일별 시세, 수급 데이터 제공
- 토큰 기반 인증 (24시간 유효)
- 파일 기반 토큰 캐싱 (1일 1회 발급 제한 준수)
- 토큰 만료 시 자동 재발급 (HTTP 200 + rt_cd:"1" 또는 HTTP 401)

장점:
- 공식 증권사 API로 데이터 신뢰성 높음
- 실시간 수급 데이터 (외국인/기관 순매수량)
- 상세 시세 정보 (52주 고가/저가, PER, PBR 등)

단점:
- 토큰 관리 필요 (24시간 만료)
- 초당 호출 제한 (약 20회/초)
- 앱키/시크릿 필요

주의:
- 토큰 발급은 1일 1회 제한이므로 파일 캐싱 필수
- 토큰 캐시 파일: .cache/kis_token.json
"""
import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

import requests

from .base import DataSourceBase
from ..types import SupplyDemandData

logger = logging.getLogger(__name__)

# HTTP 세션 (재사용)
_session = requests.Session()


class KISTokenManager:
    """
    KIS API 토큰 관리자 (싱글톤 + 파일 캐싱)

    중요: 한국투자증권 API는 토큰 발급이 1일 1회로 제한됩니다.
    프로그램 재시작 시에도 기존 토큰을 재사용하기 위해 파일에 캐싱합니다.
    """

    _instance: Optional['KISTokenManager'] = None

    BASE_URL = "https://openapi.koreainvestment.com:9443"

    # 토큰 캐시 파일 경로 (프로젝트 루트/.cache/kis_token.json)
    CACHE_DIR = ".cache"
    CACHE_FILE = "kis_token.json"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
        self._app_key: Optional[str] = None
        self._app_secret: Optional[str] = None
        self._cache_file_path: Optional[Path] = None
        self._lock = threading.Lock()
        self._last_refresh_time: float = 0
        self._initialized = True

    def _get_cache_file_path(self) -> Path:
        """토큰 캐시 파일 경로 반환 (프로젝트 루트 기준)"""
        if self._cache_file_path:
            return self._cache_file_path

        # 프로젝트 루트 찾기 (src/dual_source/sources/ 에서 3단계 상위)
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent.parent

        cache_dir = project_root / self.CACHE_DIR
        cache_dir.mkdir(exist_ok=True)

        self._cache_file_path = cache_dir / self.CACHE_FILE
        return self._cache_file_path

    def _load_token_from_file(self) -> bool:
        """
        파일에서 토큰 로드

        Returns:
            True: 유효한 토큰 로드 성공
            False: 파일 없음 또는 토큰 만료
        """
        try:
            cache_file = self._get_cache_file_path()
            if not cache_file.exists():
                logger.debug("KIS 토큰 캐시 파일 없음")
                return False

            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            token = data.get('access_token')
            expires_at = data.get('expires_at', 0)
            cached_app_key = data.get('app_key_hash')  # 앱키 해시로 검증

            # 앱키가 변경되었는지 확인 (다른 계정으로 전환 시)
            current_key_hash = self._hash_app_key()
            if cached_app_key and cached_app_key != current_key_hash:
                logger.info("🔄 KIS 앱키 변경 감지, 기존 토큰 무효화")
                return False

            # 토큰 만료 확인 (5분 여유)
            if not token or time.time() >= (expires_at - 300):
                logger.info("⏰ KIS 캐시 토큰 만료됨")
                return False

            # 유효한 토큰 로드
            self._access_token = token
            self._token_expires_at = expires_at

            remaining = int((expires_at - time.time()) / 3600)
            logger.info(f"✅ KIS 캐시 토큰 로드 성공 (남은 유효시간: ~{remaining}시간)")
            return True

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"KIS 토큰 캐시 파일 손상: {e}")
            return False
        except Exception as e:
            logger.warning(f"KIS 토큰 캐시 로드 오류: {e}")
            return False

    def _save_token_to_file(self) -> bool:
        """
        토큰을 파일에 저장

        Returns:
            True: 저장 성공
            False: 저장 실패
        """
        if not self._access_token:
            return False

        try:
            cache_file = self._get_cache_file_path()

            data = {
                'access_token': self._access_token,
                'expires_at': self._token_expires_at,
                'app_key_hash': self._hash_app_key(),
                'created_at': datetime.now().isoformat(),
            }

            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.debug(f"KIS 토큰 캐시 저장: {cache_file}")
            return True

        except Exception as e:
            logger.warning(f"KIS 토큰 캐시 저장 실패: {e}")
            return False

    def _delete_cache_file(self):
        """캐시 파일 삭제"""
        try:
            cache_file = self._get_cache_file_path()
            if cache_file.exists():
                cache_file.unlink()
                logger.debug("KIS 토큰 캐시 파일 삭제됨")
        except Exception as e:
            logger.warning(f"KIS 토큰 캐시 삭제 실패: {e}")

    def _hash_app_key(self) -> str:
        """앱키 해시 (마지막 4자리만 저장하여 변경 감지)"""
        if not self._app_key:
            return ""
        return self._app_key[-4:] if len(self._app_key) >= 4 else self._app_key

    def configure(self, app_key: str, app_secret: str):
        """API 키 설정 및 캐시 토큰 로드 시도"""
        self._app_key = app_key
        self._app_secret = app_secret

        # 설정 후 캐시에서 토큰 로드 시도
        self._load_token_from_file()

    def is_configured(self) -> bool:
        """API 키가 설정되었는지 확인"""
        return bool(self._app_key and self._app_secret)

    def get_token(self) -> Optional[str]:
        """
        유효한 액세스 토큰 반환 (Supabase 공유 → 파일 캐시 → 신규 발급)

        스레드 안전: Lock + double-check 패턴으로 동시 발급 방지
        1. Lock 없이 메모리 확인 (빠른 경로)
        2. Lock 획득 후 전체 캐스케이드 실행
        """
        if not self.is_configured():
            return None

        # 1. Lock 없이 메모리 확인 (빠른 경로 - 대부분 여기서 반환)
        if self._access_token and time.time() < (self._token_expires_at - 300):
            return self._access_token

        # 2. Lock 획득 후 전체 캐스케이드 (동시 발급 방지)
        with self._lock:
            # Double-check: 다른 스레드가 이미 토큰을 갱신했을 수 있음
            if self._access_token and time.time() < (self._token_expires_at - 300):
                return self._access_token

            # Supabase에서 공유 토큰 로드 시도
            if self._load_token_from_supabase():
                return self._access_token

            # 파일에서 토큰 로드 시도
            if self._load_token_from_file():
                return self._access_token

            # 새 토큰 발급 (주의: 1일 1회 제한)
            logger.info("🔄 KIS 토큰 신규 발급 시도 (1일 1회 제한 주의)")
            return self._refresh_token()

    def _load_token_from_supabase(self) -> bool:
        """
        Supabase에서 공유 토큰 로드 (여러 프로젝트 간 토큰 공유)

        Returns:
            True: 유효한 토큰 로드 성공
            False: 토큰 없음 또는 만료
        """
        try:
            from config.supabase_credentials import get_supabase_credentials_manager

            creds_manager = get_supabase_credentials_manager()
            if not creds_manager.is_supabase_available:
                return False

            kis_token = creds_manager.get_kis_token()
            if not kis_token or not kis_token.is_valid:
                return False

            # Supabase 토큰을 메모리와 파일에 저장
            self._access_token = kis_token.access_token
            self._token_expires_at = kis_token.expires_at

            # 로컬 파일에도 캐싱 (다음 실행 시 Supabase 조회 없이 사용 가능)
            self._save_token_to_file()

            logger.info(f"✅ Supabase에서 KIS 공유 토큰 로드 (남은 유효시간: ~{kis_token.remaining_hours}시간)")
            return True

        except Exception as e:
            logger.debug(f"Supabase 토큰 로드 실패: {e}")
            return False

    # 토큰 발급 최소 간격 (초) - 동일 프로세스 내 중복 발급 방지
    _REFRESH_COOLDOWN = 30

    def _refresh_token(self) -> Optional[str]:
        """
        토큰 발급/갱신

        주의: 한국투자증권 API는 1일 1회 토큰 발급 제한이 있습니다.
        발급 성공 시 파일 및 Supabase에 저장하여 여러 프로젝트에서 공유합니다.

        스레드 안전: 이 메서드는 반드시 self._lock 내부에서 호출되어야 합니다.
        """
        # 쿨다운 체크: 최근 발급 이력이 있으면 다른 소스 재확인 후 차단
        now = time.time()
        if self._last_refresh_time and (now - self._last_refresh_time) < self._REFRESH_COOLDOWN:
            elapsed = now - self._last_refresh_time
            logger.warning(f"⚠️ KIS 토큰 {elapsed:.0f}초 전에 발급됨, 재발급 대신 캐시 재확인")
            if self._load_token_from_supabase():
                return self._access_token
            if self._load_token_from_file():
                return self._access_token
            logger.error(f"❌ KIS 토큰 발급 쿨다운 중 ({self._REFRESH_COOLDOWN}초), 캐시에도 없음")
            return None

        try:
            url = f"{self.BASE_URL}/oauth2/tokenP"
            payload = {
                "grant_type": "client_credentials",
                "appkey": self._app_key,
                "appsecret": self._app_secret,
            }
            headers = {"Content-Type": "application/json"}

            response = _session.post(url, json=payload, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                expires_in = int(data.get("expires_in", 86400))  # 기본 24시간

                # expires_at를 먼저 설정 (Lock 밖에서 읽는 스레드가 불일치 값을 보지 않도록)
                self._token_expires_at = time.time() + expires_in
                self._access_token = data.get("access_token")
                self._last_refresh_time = time.time()

                logger.info(f"✅ KIS 토큰 발급 성공 (유효기간: {expires_in // 3600}시간)")

                # 파일에 캐싱 (다음 실행 시 재사용)
                self._save_token_to_file()

                # Supabase에 저장 (여러 프로젝트 간 공유)
                self._save_token_to_supabase()

                return self._access_token
            else:
                logger.error(f"❌ KIS 토큰 발급 실패: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"❌ KIS 토큰 발급 오류: {e}")
            return None

    def _save_token_to_supabase(self) -> bool:
        """
        토큰을 Supabase에 저장 (여러 프로젝트 간 공유)

        Returns:
            성공 여부
        """
        if not self._access_token:
            return False

        try:
            from config.supabase_credentials import get_supabase_credentials_manager

            creds_manager = get_supabase_credentials_manager()
            if not creds_manager.is_supabase_available:
                logger.debug("Supabase 미연결 - 토큰 공유 스킵")
                return False

            return creds_manager.update_kis_token(
                access_token=self._access_token,
                expires_at=self._token_expires_at
            )

        except Exception as e:
            logger.debug(f"Supabase 토큰 저장 실패: {e}")
            return False

    def invalidate(self):
        """토큰 무효화 (토큰 만료 감지 시 호출, 스레드 안전)"""
        with self._lock:
            # 이미 무효화된 상태면 중복 작업 방지
            if self._access_token is None and self._token_expires_at == 0:
                logger.debug("KIS 토큰 이미 무효화 상태, 스킵")
                return

            self._access_token = None
            self._token_expires_at = 0
            self._delete_cache_file()

            # Supabase에서도 토큰 무효화 (다른 프로젝트에서 새 토큰 발급 유도)
            try:
                from config.supabase_credentials import get_supabase_credentials_manager
                creds_manager = get_supabase_credentials_manager()
                if creds_manager.is_supabase_available:
                    creds_manager.invalidate_kis_token()
            except Exception as e:
                logger.debug(f"Supabase 토큰 무효화 실패: {e}")

            logger.info("🔄 KIS 토큰 무효화됨 (로컬 캐시 + Supabase 삭제, 재발급 필요)")

    @property
    def app_key(self) -> Optional[str]:
        return self._app_key

    @property
    def app_secret(self) -> Optional[str]:
        return self._app_secret


# 전역 토큰 매니저
_token_manager = KISTokenManager()


def get_kis_token_manager() -> KISTokenManager:
    """KIS 토큰 매니저 싱글톤 인스턴스 반환"""
    return _token_manager


class KISSource(DataSourceBase):
    """한국투자증권 Open API 데이터 소스"""

    BASE_URL = "https://openapi.koreainvestment.com:9443"

    def __init__(self, app_key: Optional[str] = None, app_secret: Optional[str] = None):
        """
        Args:
            app_key: KIS 앱키 (Supabase 또는 환경변수에서 로드 가능)
            app_secret: KIS 앱 시크릿 (Supabase 또는 환경변수에서 로드 가능)
        """
        super().__init__()
        self._token_manager = get_kis_token_manager()

        key = app_key
        secret = app_secret

        # 인자가 없으면 Supabase → 환경변수 순으로 로드
        if not (key and secret):
            try:
                from config.supabase_credentials import get_supabase_credentials_manager
                creds_manager = get_supabase_credentials_manager()
                kis_creds = creds_manager.get_kis_credentials()

                if kis_creds:
                    key = kis_creds.app_key
                    secret = kis_creds.app_secret
                    logger.info(f"✅ KIS 자격증명 로드됨 (소스: {kis_creds.source})")
            except Exception as e:
                logger.debug(f"Supabase 자격증명 로드 실패: {e}")

        # 여전히 없으면 환경변수에서 직접 로드 (fallback)
        if not (key and secret):
            import os
            key = os.getenv('KIS_APP_KEY')
            secret = os.getenv('KIS_APP_SECRET')
            if key and secret:
                logger.info("✅ KIS 자격증명 로드됨 (소스: env fallback)")

        if key and secret:
            self._token_manager.configure(key, secret)
            logger.info("✅ KIS API 소스 초기화됨")

    @property
    def source_name(self) -> str:
        return "kis_api"

    @property
    def priority(self) -> int:
        return 1  # 높은 우선순위 (공식 증권사 API)

    def is_supported(self, ticker_code: str) -> bool:
        """한국 주식만 지원"""
        return self._is_korean_stock(ticker_code)

    def _is_korean_stock(self, ticker_code: str) -> bool:
        """한국 주식인지 확인"""
        return '.KS' in ticker_code or '.KQ' in ticker_code

    def _get_headers(self, tr_id: str) -> Optional[Dict[str, str]]:
        """API 요청 헤더 생성"""
        token = self._token_manager.get_token()
        if not token:
            return None

        return {
            "authorization": f"Bearer {token}",
            "appkey": self._token_manager.app_key,
            "appsecret": self._token_manager.app_secret,
            "tr_id": tr_id,
            "Content-Type": "application/json; charset=utf-8",
        }

    def _get_market_code(self, ticker_code: str) -> str:
        """시장 구분 코드 반환"""
        if '.KQ' in ticker_code:
            return 'Q'  # 코스닥
        return 'J'  # 코스피

    def _extract_code(self, ticker_code: str) -> str:
        """티커에서 6자리 종목코드 추출"""
        return ticker_code.replace('.KS', '').replace('.KQ', '')

    def _request_with_retry(
        self, url: str, params: Dict, tr_id: str, max_retries: int = 2
    ) -> Optional[Dict[str, Any]]:
        """재시도 로직이 포함된 API 요청"""
        for attempt in range(max_retries):
            headers = self._get_headers(tr_id)
            if not headers:
                return None

            try:
                response = _session.get(url, params=params, headers=headers, timeout=10)

                if response.status_code == 200:
                    data = response.json()
                    # 성공 코드 확인
                    if data.get('rt_cd') == '0':
                        return data
                    else:
                        # KIS API는 토큰 만료 시 HTTP 200 + rt_cd: "1" 반환
                        # 예: {"rt_cd": "1", "msg1": "기간이 만료된 token 입니다"}
                        msg = data.get('msg1', '')
                        if '만료' in msg or 'token' in msg.lower() or '토큰' in msg:
                            logger.warning(f"🔄 KIS 토큰 만료 감지 (rt_cd=1): {msg}")
                            self._token_manager.invalidate()
                            continue  # 토큰 재발급 후 재시도
                        else:
                            logger.warning(f"KIS API 응답 오류: {msg}")
                            return None

                elif response.status_code == 401:
                    # 토큰 만료 → 재발급 후 재시도
                    logger.warning("🔄 KIS 토큰 만료, 재발급 시도...")
                    self._token_manager.invalidate()
                    continue

                else:
                    logger.warning(f"KIS API 요청 실패: {response.status_code}")
                    return None

            except requests.Timeout:
                logger.warning(f"KIS API 타임아웃 (시도 {attempt + 1}/{max_retries})")
                continue
            except Exception as e:
                logger.error(f"KIS API 오류: {e}")
                return None

        return None

    def _get_current_price(self, code: str, market: str) -> Optional[Dict[str, Any]]:
        """현재가 조회"""
        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
        params = {
            "FID_COND_MRKT_DIV_CODE": market,
            "FID_INPUT_ISCD": code,
        }
        return self._request_with_retry(url, params, "FHKST01010100")

    def _parse_supply_demand(self, output: Dict[str, Any]) -> SupplyDemandData:
        """현재가 응답에서 수급 데이터 추출"""
        result: SupplyDemandData = {}

        try:
            # 외국인 순매수량 (주 → 만주)
            frgn_qty = output.get('frgn_ntby_qty')
            if frgn_qty and frgn_qty != '':
                qty = float(frgn_qty.replace(',', ''))
                result['foreign_net_1d'] = round(qty / 10000, 2)

            # 기관 순매수량 (주 → 만주)
            pgtr_qty = output.get('pgtr_ntby_qty')
            if pgtr_qty and pgtr_qty != '':
                qty = float(pgtr_qty.replace(',', ''))
                result['institutional_net_1d'] = round(qty / 10000, 2)

            # 거래량
            acml_vol = output.get('acml_vol')
            if acml_vol and acml_vol != '':
                result['total_volume_1d'] = float(acml_vol.replace(',', ''))

        except (ValueError, TypeError) as e:
            logger.debug(f"KIS 수급 데이터 파싱 오류: {e}")

        return result

    def _collect_sync(self, ticker_code: str) -> SupplyDemandData:
        """동기 방식으로 데이터 수집"""
        if not self._token_manager.is_configured():
            logger.debug("KIS API 미설정 (APP_KEY/APP_SECRET 필요)")
            return {}

        if not self._is_korean_stock(ticker_code):
            return {}

        code = self._extract_code(ticker_code)
        market = self._get_market_code(ticker_code)

        # 현재가 조회
        data = self._get_current_price(code, market)
        if not data:
            return {}

        output = data.get('output', {})
        if not output:
            return {}

        result = self._parse_supply_demand(output)

        # 주의: KIS 현재가 API는 1일 데이터만 제공
        # 3거래일 합계(foreign_net, institutional_net)는 설정하지 않음
        # → pykrx에서 실제 3일 합계 데이터를 제공하도록 함

        logger.debug(
            f"KIS {ticker_code}: 외인={result.get('foreign_net_1d')}만주, "
            f"기관={result.get('institutional_net_1d')}만주"
        )

        return result

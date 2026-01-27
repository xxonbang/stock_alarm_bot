"""
Twelve Data API 데이터 소스

미국/글로벌 주식 실시간 시세, 히스토리컬 데이터, 기술적 지표 제공
한국 주식 (KRX) 일부 지원

장점:
- 무료 플랜: 800 calls/day (FMP보다 3배+)
- 분당 8 calls (안정적)
- 기술적 지표 내장 제공
- 글로벌 시장 지원 (KRX 포함)

단점:
- 기관 보유 데이터 미제공
- 일부 고급 기능 유료
"""
import logging
from datetime import datetime
from typing import Optional, List

import requests

from .base import DataSourceBase
from ..types import SupplyDemandData

logger = logging.getLogger(__name__)

# HTTP 세션 (재사용)
_session = requests.Session()


class TwelveDataSource(DataSourceBase):
    """Twelve Data API 데이터 소스 (미국 주식 주요 Fallback)"""

    BASE_URL = "https://api.twelvedata.com"

    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: Twelve Data API 키 (환경변수에서 로드 가능)
        """
        super().__init__()

        import os
        self._api_key = api_key or os.getenv('TWELVE_DATA_API_KEY')

        if self._api_key:
            logger.info("✅ Twelve Data API 소스 초기화됨")
        else:
            logger.debug("Twelve Data API 미설정 (TWELVE_DATA_API_KEY 필요)")

    @property
    def source_name(self) -> str:
        return "twelvedata"

    @property
    def priority(self) -> int:
        return 2  # yfinance 다음, Finnhub/FMP보다 우선

    def is_supported(self, ticker_code: str) -> bool:
        """미국 주식 지원 (한국 제외)"""
        return not self._is_korean_stock(ticker_code)

    def _is_korean_stock(self, ticker_code: str) -> bool:
        """한국 주식인지 확인"""
        return '.KS' in ticker_code or '.KQ' in ticker_code

    def _normalize_symbol(self, ticker_code: str) -> str:
        """티커 심볼 정규화 (Twelve Data 형식)"""
        symbol = ticker_code.upper()
        # 암호화폐: BTC-USD → BTC/USD
        if '-USD' in symbol:
            symbol = symbol.replace('-USD', '/USD')
        return symbol

    def _request(self, endpoint: str, params: Optional[dict] = None) -> Optional[dict]:
        """API 요청"""
        if not self._api_key:
            return None

        url = f"{self.BASE_URL}/{endpoint}"
        if params is None:
            params = {}
        params['apikey'] = self._api_key

        try:
            response = _session.get(url, params=params, timeout=15)

            if response.status_code == 200:
                data = response.json()
                # 에러 체크
                if data.get('status') == 'error':
                    logger.debug(f"Twelve Data API 오류: {data.get('message')}")
                    return None
                return data
            elif response.status_code == 429:
                logger.warning("⚠️ Twelve Data Rate Limit 도달 (800 calls/day)")
                return None
            elif response.status_code == 401:
                logger.warning("⚠️ Twelve Data API 키 인증 실패")
                return None
            else:
                logger.debug(f"Twelve Data API 오류: {response.status_code}")
                return None

        except requests.Timeout:
            logger.warning("Twelve Data API 타임아웃")
            return None
        except Exception as e:
            logger.debug(f"Twelve Data API 요청 실패: {e}")
            return None

    def _get_quote(self, symbol: str) -> Optional[dict]:
        """실시간 시세 조회"""
        return self._request("quote", {"symbol": symbol})

    def _get_price(self, symbol: str) -> Optional[dict]:
        """현재가만 조회 (가벼운 요청)"""
        return self._request("price", {"symbol": symbol})

    def _collect_sync(self, ticker_code: str) -> SupplyDemandData:
        """동기 방식으로 데이터 수집"""
        if not self._api_key:
            return {}

        if self._is_korean_stock(ticker_code):
            return {}

        symbol = self._normalize_symbol(ticker_code)

        # 시세 조회
        quote = self._get_quote(symbol)
        if not quote:
            return {}

        result: SupplyDemandData = {}

        try:
            # Twelve Data Quote 응답:
            # symbol, name, exchange, currency
            # open, high, low, close, volume
            # previous_close, change, percent_change
            # fifty_two_week (high/low)

            # 거래량 정보
            volume = quote.get('volume')
            if volume and str(volume).isdigit():
                result['total_volume_1d'] = float(volume)

            # 평균 거래량 (quote에서 제공되지 않음)
            # 별도 API 호출 필요하나, 호출 절약을 위해 생략

            logger.debug(
                f"TwelveData {symbol}: 거래량={result.get('total_volume_1d')}"
            )

        except Exception as e:
            logger.debug(f"Twelve Data 데이터 파싱 오류: {e}")

        return result

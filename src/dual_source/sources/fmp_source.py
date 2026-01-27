"""
Financial Modeling Prep (FMP) API 데이터 소스

미국 주식 실시간 시세, 히스토리컬 데이터, 재무제표 제공
NASDAQ 공식 라이선스 보유

장점:
- NASDAQ 공식 데이터 제공
- 재무제표/키 메트릭 포함
- 배치 시세 지원 (여러 종목 한번에)

단점:
- 무료 티어: 250 calls/day
- 유료 플랜 권장 ($19/month)
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


class FMPSource(DataSourceBase):
    """Financial Modeling Prep API 데이터 소스 (미국 주식 Fallback)"""

    # 신규 Stable API URL (2024+)
    BASE_URL = "https://financialmodelingprep.com/stable"

    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: FMP API 키 (환경변수에서 로드 가능)
        """
        super().__init__()

        import os
        self._api_key = api_key or os.getenv('FMP_API_KEY')

        if self._api_key:
            logger.info("✅ FMP API 소스 초기화됨")
        else:
            logger.debug("FMP API 미설정 (FMP_API_KEY 필요)")

    @property
    def source_name(self) -> str:
        return "fmp"

    @property
    def priority(self) -> int:
        return 4  # Finnhub (3) 다음 fallback

    def is_supported(self, ticker_code: str) -> bool:
        """미국 주식만 지원"""
        return not self._is_korean_stock(ticker_code)

    def _is_korean_stock(self, ticker_code: str) -> bool:
        """한국 주식인지 확인"""
        return '.KS' in ticker_code or '.KQ' in ticker_code

    def _normalize_symbol(self, ticker_code: str) -> str:
        """티커 심볼 정규화 (FMP 형식)"""
        # 암호화폐: BTC-USD → BTCUSD
        symbol = ticker_code.upper()
        if '-USD' in symbol:
            symbol = symbol.replace('-USD', 'USD')
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
                # FMP는 배열로 반환하거나 단일 객체로 반환
                return data
            elif response.status_code == 429:
                logger.warning("⚠️ FMP Rate Limit 도달 (250 calls/day)")
                return None
            elif response.status_code == 401:
                logger.warning("⚠️ FMP API 키 인증 실패")
                return None
            else:
                logger.debug(f"FMP API 오류: {response.status_code}")
                return None

        except requests.Timeout:
            logger.warning("FMP API 타임아웃")
            return None
        except Exception as e:
            logger.debug(f"FMP API 요청 실패: {e}")
            return None

    def _get_quote(self, symbol: str) -> Optional[dict]:
        """단일 종목 시세 조회"""
        data = self._request("quote", {"symbol": symbol})
        if data and isinstance(data, list) and len(data) > 0:
            return data[0]
        return None

    def _get_batch_quote(self, symbols: List[str]) -> Optional[List[dict]]:
        """여러 종목 배치 시세 조회"""
        symbols_str = ",".join(symbols)
        data = self._request("batch-quote", {"symbols": symbols_str})
        if data and isinstance(data, list):
            return data
        return None

    def _get_key_metrics(self, symbol: str) -> Optional[dict]:
        """키 메트릭 (TTM) 조회"""
        data = self._request("key-metrics-ttm", {"symbol": symbol})
        if data and isinstance(data, list) and len(data) > 0:
            return data[0]
        return None

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
            # FMP Quote 응답:
            # symbol, name, price, change, changePercentage
            # dayLow, dayHigh, yearHigh, yearLow, marketCap
            # volume, avgVolume, exchange, open, previousClose
            # eps, pe

            # 거래량 정보
            volume = quote.get('volume')
            if volume and volume > 0:
                result['total_volume_1d'] = float(volume)

            avg_volume = quote.get('avgVolume')
            if avg_volume and avg_volume > 0:
                result['total_volume'] = float(avg_volume)

            # FMP는 기관/외국인 수급 데이터를 직접 제공하지 않음
            # 추가 정보를 위해 키 메트릭 조회 시도
            metrics = self._get_key_metrics(symbol)
            if metrics:
                # 기관 보유 비율 (if available)
                inst_ownership = metrics.get('institutionalOwnership')
                if inst_ownership is not None:
                    result['institutional_net'] = round(float(inst_ownership) * 100, 2)

            logger.debug(
                f"FMP {symbol}: 거래량={result.get('total_volume_1d')}, "
                f"평균거래량={result.get('total_volume')}"
            )

        except Exception as e:
            logger.debug(f"FMP 데이터 파싱 오류: {e}")

        return result

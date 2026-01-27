"""
Finnhub API 데이터 소스

미국 주식 실시간 시세, 뉴스 제공
한국/미국 모두 지원 (한국은 KRX 심볼 형식)

장점:
- 무료 플랜: 60 calls/min
- 실시간 시세 제공
- 글로벌 주식 지원

단점:
- 무료 플랜 Candle API 제한
- 수급 데이터 미제공 (yfinance fallback 필요)
"""
import logging
from datetime import datetime
from typing import Optional

import requests

from .base import DataSourceBase
from ..types import SupplyDemandData

logger = logging.getLogger(__name__)

# HTTP 세션 (재사용)
_session = requests.Session()


class FinnhubSource(DataSourceBase):
    """Finnhub API 데이터 소스 (미국 주식 Fallback)"""

    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: Finnhub API 키 (환경변수에서 로드 가능)
        """
        super().__init__()

        import os
        self._api_key = api_key or os.getenv('FINNHUB_API_KEY')

        if self._api_key:
            logger.info("✅ Finnhub API 소스 초기화됨")
        else:
            logger.debug("Finnhub API 미설정 (FINNHUB_API_KEY 필요)")

    @property
    def source_name(self) -> str:
        return "finnhub"

    @property
    def priority(self) -> int:
        return 3  # yfinance (2) 다음 fallback

    def is_supported(self, ticker_code: str) -> bool:
        """미국 주식만 지원 (한국 제외)"""
        return not self._is_korean_stock(ticker_code)

    def _is_korean_stock(self, ticker_code: str) -> bool:
        """한국 주식인지 확인"""
        return '.KS' in ticker_code or '.KQ' in ticker_code

    def _normalize_symbol(self, ticker_code: str) -> str:
        """티커 심볼 정규화"""
        # BTC-USD → BINANCE:BTCUSDT (암호화폐 처리는 별도)
        return ticker_code.upper()

    def _request(self, endpoint: str, params: dict) -> Optional[dict]:
        """API 요청"""
        if not self._api_key:
            return None

        url = f"{self.BASE_URL}/{endpoint}"
        params['token'] = self._api_key

        try:
            response = _session.get(url, params=params, timeout=10)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                logger.warning("⚠️ Finnhub Rate Limit 도달 (60 calls/min)")
                return None
            else:
                logger.debug(f"Finnhub API 오류: {response.status_code}")
                return None

        except requests.Timeout:
            logger.warning("Finnhub API 타임아웃")
            return None
        except Exception as e:
            logger.debug(f"Finnhub API 요청 실패: {e}")
            return None

    def _get_quote(self, symbol: str) -> Optional[dict]:
        """실시간 시세 조회"""
        return self._request("quote", {"symbol": symbol})

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
            # Finnhub Quote 응답:
            # c: current price, d: change, dp: percent change
            # h: high, l: low, o: open, pc: previous close, t: timestamp

            # Finnhub는 수급 데이터(기관/외국인)를 제공하지 않음
            # 대신 기본 거래량/시세 정보를 제공
            # 수급 정보는 yfinance에서 가져오는 것으로 대체

            # 거래 활성도 확인용 (시세 유효성 체크)
            current = quote.get('c')
            prev_close = quote.get('pc')

            if current and current > 0:
                logger.debug(f"Finnhub {symbol}: 현재가={current}, 전일종가={prev_close}")
                # 수급 데이터는 제공하지 않으나, 시세 확인 성공
                # 필드가 비어있으면 validation에서 yfinance 데이터 사용됨

        except Exception as e:
            logger.debug(f"Finnhub 데이터 파싱 오류: {e}")

        return result

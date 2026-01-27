"""
Yahoo Finance Direct Chart API 데이터 소스

crumb 토큰 불필요 → Rate Limit에 강함
yfinance 라이브러리 대신 직접 Chart API 호출

장점:
- crumb 토큰 인증 불필요 (장기 안정성)
- Rate Limit에 강함 (토큰 만료 없음)
- 빠른 응답 속도 (~250ms vs yfinance ~900ms)
- 한 번의 호출로 가격 + 메타데이터 획득

단점:
- 기관보유 데이터 미제공 (yfinance 필요)
- 상세 기업 정보 미제공 (PER, 시가총액 등)
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

import requests

from .base import DataSourceBase
from ..types import SupplyDemandData

logger = logging.getLogger(__name__)

# HTTP 세션 (재사용)
_session = requests.Session()

# User-Agent (브라우저 위장)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Accept-Language': 'en-US,en;q=0.9',
}


class YahooChartSource(DataSourceBase):
    """Yahoo Finance Direct Chart API 소스 (미국 주식 최우선)"""

    BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

    def __init__(self):
        super().__init__()
        logger.info("✅ Yahoo Chart API 소스 초기화됨 (crumb 불필요)")

    @property
    def source_name(self) -> str:
        return "yahoo_chart"

    @property
    def priority(self) -> int:
        return 1  # 최우선순위

    def is_supported(self, ticker_code: str) -> bool:
        """미국 주식 지원 (한국 제외)"""
        return not self._is_korean_stock(ticker_code)

    def _is_korean_stock(self, ticker_code: str) -> bool:
        """한국 주식인지 확인"""
        return '.KS' in ticker_code or '.KQ' in ticker_code

    def _encode_symbol(self, ticker_code: str) -> str:
        """티커 심볼 인코딩 (특수문자 처리)"""
        # 암호화폐: BTC-USD 그대로 사용
        # 선물: CL=F 등 그대로 사용
        return ticker_code.upper()

    def _get_range(self, days: int = 180) -> str:
        """기간에 따른 range 파라미터 반환"""
        if days <= 5:
            return '5d'
        elif days <= 30:
            return '1mo'
        elif days <= 90:
            return '3mo'
        elif days <= 180:
            return '6mo'
        elif days <= 365:
            return '1y'
        else:
            return '2y'

    def _request_chart(
        self,
        symbol: str,
        interval: str = '1d',
        range_param: str = '6mo'
    ) -> Optional[Dict[str, Any]]:
        """
        Chart API 직접 호출

        Args:
            symbol: 티커 심볼
            interval: 간격 ('1d', '1h', '5m' 등)
            range_param: 기간 ('1d', '5d', '1mo', '3mo', '6mo', '1y', '2y')

        Returns:
            차트 데이터 또는 None
        """
        url = f"{self.BASE_URL}/{self._encode_symbol(symbol)}"
        params = {
            'interval': interval,
            'range': range_param,
        }

        try:
            response = _session.get(
                url,
                params=params,
                headers=HEADERS,
                timeout=15
            )

            if response.status_code == 200:
                data = response.json()

                # 에러 체크
                chart = data.get('chart', {})
                if chart.get('error'):
                    error = chart['error']
                    logger.debug(
                        f"Yahoo Chart API 오류: {error.get('code')} - {error.get('description')}"
                    )
                    return None

                result = chart.get('result')
                if result and len(result) > 0:
                    return result[0]

                return None

            elif response.status_code == 404:
                logger.debug(f"{symbol}: 티커를 찾을 수 없음")
                return None
            elif response.status_code == 429:
                logger.warning("⚠️ Yahoo Chart API Rate Limit")
                return None
            else:
                logger.debug(f"Yahoo Chart API 오류: {response.status_code}")
                return None

        except requests.Timeout:
            logger.warning(f"Yahoo Chart API 타임아웃: {symbol}")
            return None
        except Exception as e:
            logger.debug(f"Yahoo Chart API 요청 실패: {e}")
            return None

    def _parse_chart_data(self, chart_data: Dict[str, Any]) -> SupplyDemandData:
        """차트 데이터 파싱"""
        result: SupplyDemandData = {}

        try:
            meta = chart_data.get('meta', {})
            indicators = chart_data.get('indicators', {})

            # === 메타 데이터에서 추출 ===

            # 현재 거래량 (당일)
            volume = meta.get('regularMarketVolume')
            if volume and volume > 0:
                result['total_volume_1d'] = float(volume)

            # === 히스토리컬 데이터에서 평균 거래량 계산 ===
            quotes = indicators.get('quote', [])
            if quotes and len(quotes) > 0:
                volumes = quotes[0].get('volume', [])
                # 최근 20일 평균 거래량
                valid_volumes = [v for v in volumes[-20:] if v is not None and v > 0]
                if valid_volumes:
                    avg_volume = sum(valid_volumes) / len(valid_volumes)
                    result['total_volume'] = round(avg_volume, 0)

            # 로깅
            symbol = meta.get('symbol', 'Unknown')
            logger.debug(
                f"Yahoo Chart {symbol}: "
                f"거래량={result.get('total_volume_1d')}, "
                f"평균거래량={result.get('total_volume')}"
            )

        except Exception as e:
            logger.debug(f"Yahoo Chart 데이터 파싱 오류: {e}")

        return result

    def get_quote(self, ticker_code: str) -> Optional[Dict[str, Any]]:
        """
        현재가 및 메타 정보 조회 (외부 사용용)

        Returns:
            {
                'price': float,           # 현재가
                'previous_close': float,  # 전일 종가
                'change': float,          # 변동
                'change_percent': float,  # 변동률 (%)
                'volume': int,            # 거래량
                'day_high': float,        # 당일 고가
                'day_low': float,         # 당일 저가
                'week_52_high': float,    # 52주 최고
                'week_52_low': float,     # 52주 최저
            }
        """
        chart_data = self._request_chart(ticker_code, interval='1d', range_param='1d')
        if not chart_data:
            return None

        meta = chart_data.get('meta', {})

        price = meta.get('regularMarketPrice')
        prev_close = meta.get('chartPreviousClose') or meta.get('previousClose')

        change = None
        change_percent = None
        if price and prev_close:
            change = price - prev_close
            change_percent = (change / prev_close) * 100 if prev_close else 0

        return {
            'price': price,
            'previous_close': prev_close,
            'change': round(change, 2) if change else None,
            'change_percent': round(change_percent, 2) if change_percent else None,
            'volume': meta.get('regularMarketVolume'),
            'day_high': meta.get('regularMarketDayHigh'),
            'day_low': meta.get('regularMarketDayLow'),
            'week_52_high': meta.get('fiftyTwoWeekHigh'),
            'week_52_low': meta.get('fiftyTwoWeekLow'),
        }

    def get_historical(
        self,
        ticker_code: str,
        days: int = 180
    ) -> Optional[List[Dict[str, Any]]]:
        """
        히스토리컬 데이터 조회 (외부 사용용)

        Returns:
            [
                {
                    'date': '2024-01-15',
                    'open': 150.0,
                    'high': 152.0,
                    'low': 149.0,
                    'close': 151.5,
                    'adj_close': 151.5,
                    'volume': 50000000,
                },
                ...
            ]
        """
        range_param = self._get_range(days)
        chart_data = self._request_chart(ticker_code, interval='1d', range_param=range_param)
        if not chart_data:
            return None

        timestamps = chart_data.get('timestamp', [])
        indicators = chart_data.get('indicators', {})
        quotes = indicators.get('quote', [{}])[0]
        adj_closes = indicators.get('adjclose', [{}])
        adj_close_list = adj_closes[0].get('adjclose', []) if adj_closes else []

        opens = quotes.get('open', [])
        highs = quotes.get('high', [])
        lows = quotes.get('low', [])
        closes = quotes.get('close', [])
        volumes = quotes.get('volume', [])

        result = []
        for i, ts in enumerate(timestamps):
            if ts is None:
                continue

            date_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')

            result.append({
                'date': date_str,
                'open': opens[i] if i < len(opens) else None,
                'high': highs[i] if i < len(highs) else None,
                'low': lows[i] if i < len(lows) else None,
                'close': closes[i] if i < len(closes) else None,
                'adj_close': adj_close_list[i] if i < len(adj_close_list) else closes[i] if i < len(closes) else None,
                'volume': volumes[i] if i < len(volumes) else None,
            })

        return result

    def _collect_sync(self, ticker_code: str) -> SupplyDemandData:
        """동기 방식으로 데이터 수집"""
        if self._is_korean_stock(ticker_code):
            return {}

        # Chart API 호출 (6개월 데이터로 평균 거래량 계산)
        chart_data = self._request_chart(ticker_code, interval='1d', range_param='1mo')
        if not chart_data:
            return {}

        return self._parse_chart_data(chart_data)

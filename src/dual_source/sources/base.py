"""
데이터 소스 추상 베이스 클래스

모든 데이터 소스가 구현해야 하는 인터페이스를 정의합니다.
"""
from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime
import time
import logging
from concurrent.futures import ThreadPoolExecutor

from ..types import SupplyDemandData, CollectionResult

logger = logging.getLogger(__name__)


class DataSourceBase(ABC):
    """데이터 소스 추상 베이스 클래스"""

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1)

    @property
    @abstractmethod
    def source_name(self) -> str:
        """소스 이름을 반환합니다."""
        pass

    @property
    @abstractmethod
    def priority(self) -> int:
        """
        소스 우선순위를 반환합니다.
        낮은 값일수록 우선순위가 높습니다.
        """
        pass

    @abstractmethod
    def _collect_sync(self, ticker_code: str) -> SupplyDemandData:
        """
        동기 방식으로 데이터를 수집합니다.
        하위 클래스에서 구현해야 합니다.

        Args:
            ticker_code: 티커 코드 (예: '005930.KS')

        Returns:
            수집된 데이터
        """
        pass

    def collect(self, ticker_code: str) -> CollectionResult:
        """
        데이터를 수집하고 결과를 반환합니다.

        Args:
            ticker_code: 티커 코드

        Returns:
            수집 결과
        """
        start_time = time.time()
        result: CollectionResult = {
            'source_name': self.source_name,
            'data': {},
            'success': False,
            'error': None,
            'elapsed_time': 0.0,
            'timestamp': datetime.now(),
        }

        try:
            data = self._collect_sync(ticker_code)
            result['data'] = data
            result['success'] = True
            logger.debug(f"{self.source_name}: {ticker_code} 수집 성공")
        except Exception as e:
            result['error'] = str(e)
            logger.warning(f"{self.source_name}: {ticker_code} 수집 실패 - {e}")

        result['elapsed_time'] = round(time.time() - start_time, 3)
        return result

    async def collect_async(self, ticker_code: str) -> CollectionResult:
        """
        비동기 방식으로 데이터를 수집합니다.
        ThreadPoolExecutor를 사용하여 동기 메서드를 비동기로 래핑합니다.

        Args:
            ticker_code: 티커 코드

        Returns:
            수집 결과
        """
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self.collect, ticker_code)

    def is_supported(self, ticker_code: str) -> bool:
        """
        해당 티커를 지원하는지 확인합니다.

        Args:
            ticker_code: 티커 코드

        Returns:
            지원 여부
        """
        return True

    def __del__(self):
        """정리 작업"""
        if hasattr(self, '_executor'):
            self._executor.shutdown(wait=False)

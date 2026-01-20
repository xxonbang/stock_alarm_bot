"""
듀얼 소스 병렬 수집기

Source A (Agentic Screenshot)와 Source B (전통적 API)에서
병렬로 데이터를 수집하고 교차 검증합니다.

┌─────────────────────────────────────────────────────────────────────────┐
│   [Source A]                              [Source B]                    │
│   Agentic Screenshot                      전통적 API                    │
│   (Playwright + Gemini Vision AI)         (pykrx, KRX API, yfinance)   │
│        │                                       │                        │
│        └───────────────┬───────────────────────┘                        │
│                        ▼                                                │
│              ┌──────────────────┐                                       │
│              │   검증 엔진       │                                       │
│              └──────────────────┘                                       │
│                        │                                                │
│                        ▼                                                │
│              ┌──────────────────┐                                       │
│              │ ValidatedStockData│                                      │
│              │ (신뢰도 포함)      │                                      │
│              └──────────────────┘                                       │
└─────────────────────────────────────────────────────────────────────────┘
"""
import asyncio
import logging
import os
from typing import List, Optional, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

from .types import ValidatedStockData, CollectionResult
from .validation_engine import ValidationEngine
from .sources.base import DataSourceBase
from .sources.agentic_source import AgenticScreenshotSource
from .sources.api_source import TraditionalAPISource

logger = logging.getLogger(__name__)


class DualSourceCollector:
    """듀얼 소스 병렬 수집기"""

    def __init__(
        self,
        google_api_key: Optional[str] = None,
        krx_api_key: Optional[str] = None,
        timeout: float = 30.0,
        enable_agentic: bool = True,
    ):
        """
        Args:
            google_api_key: Google AI API Key (Agentic Screenshot용)
            krx_api_key: KRX OpenAPI 인증키 (전통적 API용)
            timeout: 수집 타임아웃 (초)
            enable_agentic: Agentic Screenshot 활성화 여부 (서버리스 환경에서 비활성화)
        """
        self._timeout = timeout
        self._enable_agentic = enable_agentic
        self._validation_engine = ValidationEngine()

        # 환경 감지: Vercel 등 서버리스 환경에서는 Agentic 비활성화
        if os.environ.get('VERCEL') or os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
            self._enable_agentic = False
            logger.info("서버리스 환경 감지: Agentic Screenshot 비활성화")

        # Source A: Agentic Screenshot (Playwright + Gemini Vision)
        self._source_a: Optional[AgenticScreenshotSource] = None
        if self._enable_agentic:
            self._source_a = AgenticScreenshotSource(google_api_key=google_api_key)

        # Source B: 전통적 API (pykrx, KRX API, 네이버, yfinance)
        self._source_b = TraditionalAPISource(krx_api_key=krx_api_key)

        # 스레드풀
        self._executor = ThreadPoolExecutor(max_workers=4)

        logger.info(
            f"DualSourceCollector 초기화: "
            f"Source A (Agentic)={'활성' if self._enable_agentic else '비활성'}, "
            f"Source B (API)=활성"
        )

    def collect_sync(self, ticker_code: str) -> ValidatedStockData:
        """
        동기 방식으로 데이터를 수집합니다.

        Args:
            ticker_code: 티커 코드

        Returns:
            검증된 데이터
        """
        source_a_result: Optional[CollectionResult] = None
        source_b_result: Optional[CollectionResult] = None

        # 병렬 수집 준비
        futures = {}

        # Source A: Agentic Screenshot (활성화된 경우만)
        if self._source_a and self._enable_agentic:
            futures['source_a'] = self._executor.submit(
                self._source_a.collect, ticker_code
            )

        # Source B: 전통적 API (항상 사용)
        futures['source_b'] = self._executor.submit(
            self._source_b.collect, ticker_code
        )

        # 결과 수집 (타임아웃 적용)
        for key, future in futures.items():
            try:
                result = future.result(timeout=self._timeout)
                if key == 'source_a':
                    source_a_result = result
                else:
                    source_b_result = result
            except Exception as e:
                logger.warning(f"{ticker_code} {key} 수집 실패: {e}")

        # 교차 검증 및 병합
        validated = self._validation_engine.validate_and_merge(
            ticker_code, source_a_result, source_b_result
        )

        # 사용된 소스 로깅
        sources_used = []
        if source_a_result and source_a_result.get('success'):
            sources_used.append('Agentic')
        if source_b_result and source_b_result.get('success'):
            sources_used.append('API')

        logger.info(
            f"{ticker_code} 듀얼 소스 수집 완료: "
            f"소스={','.join(sources_used) or 'None'}, "
            f"신뢰도={validated.get('confidence', 0):.1f}%, "
            f"상태={validated.get('validation', {}).get('status', 'unknown')}"
        )

        return validated

    async def collect_async(self, ticker_code: str) -> ValidatedStockData:
        """
        비동기 방식으로 데이터를 수집합니다.

        Args:
            ticker_code: 티커 코드

        Returns:
            검증된 데이터
        """
        tasks = []

        # Source A: Agentic Screenshot
        if self._source_a and self._enable_agentic:
            tasks.append(self._source_a.collect_async(ticker_code))
        else:
            tasks.append(asyncio.coroutine(lambda: None)())

        # Source B: 전통적 API
        tasks.append(self._source_b.collect_async(ticker_code))

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self._timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"{ticker_code} 수집 타임아웃 ({self._timeout}초)")
            results = [None, None]

        source_a_result = results[0] if not isinstance(results[0], Exception) else None
        source_b_result = results[1] if len(results) > 1 and not isinstance(results[1], Exception) else None

        if isinstance(results[0], Exception):
            logger.warning(f"{ticker_code} Source A 수집 실패: {results[0]}")
        if len(results) > 1 and isinstance(results[1], Exception):
            logger.warning(f"{ticker_code} Source B 수집 실패: {results[1]}")

        # 교차 검증 및 병합
        validated = self._validation_engine.validate_and_merge(
            ticker_code, source_a_result, source_b_result
        )

        return validated

    def collect_batch_sync(
        self, ticker_codes: List[str]
    ) -> Dict[str, ValidatedStockData]:
        """
        여러 티커에 대해 동기 방식으로 배치 수집합니다.

        Args:
            ticker_codes: 티커 코드 리스트

        Returns:
            티커별 검증된 데이터 딕셔너리
        """
        result_dict: Dict[str, ValidatedStockData] = {}

        futures = {
            self._executor.submit(self.collect_sync, ticker): ticker
            for ticker in ticker_codes
        }

        for future in as_completed(futures, timeout=self._timeout * len(ticker_codes)):
            ticker = futures[future]
            try:
                result = future.result()
                result_dict[ticker] = result
            except Exception as e:
                logger.error(f"{ticker} 배치 수집 실패: {e}")

        return result_dict

    async def collect_batch_async(
        self, ticker_codes: List[str]
    ) -> Dict[str, ValidatedStockData]:
        """
        여러 티커에 대해 비동기 방식으로 배치 수집합니다.

        Args:
            ticker_codes: 티커 코드 리스트

        Returns:
            티커별 검증된 데이터 딕셔너리
        """
        tasks = [self.collect_async(ticker) for ticker in ticker_codes]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        result_dict: Dict[str, ValidatedStockData] = {}
        for ticker, result in zip(ticker_codes, results):
            if isinstance(result, Exception):
                logger.error(f"{ticker} 배치 수집 실패: {result}")
                continue
            result_dict[ticker] = result

        return result_dict

    def __del__(self):
        """정리 작업"""
        if hasattr(self, '_executor'):
            self._executor.shutdown(wait=False)


# 기본 컬렉터 인스턴스 (싱글톤 패턴)
_default_collector: Optional[DualSourceCollector] = None


def get_collector(
    google_api_key: Optional[str] = None,
    krx_api_key: Optional[str] = None,
    enable_agentic: bool = True,
) -> DualSourceCollector:
    """
    기본 컬렉터 인스턴스를 반환합니다.

    Args:
        google_api_key: Google AI API Key (없으면 설정에서 로드)
        krx_api_key: KRX API 키 (없으면 설정에서 로드)
        enable_agentic: Agentic Screenshot 활성화 여부

    Returns:
        DualSourceCollector 인스턴스
    """
    global _default_collector

    if _default_collector is None:
        # 설정에서 API 키 로드
        try:
            from config.settings import settings
            if google_api_key is None:
                google_api_key = settings.google_api_key
            if krx_api_key is None:
                krx_api_key = settings.krx_api_key
        except Exception:
            pass

        _default_collector = DualSourceCollector(
            google_api_key=google_api_key,
            krx_api_key=krx_api_key,
            enable_agentic=enable_agentic,
        )

    return _default_collector

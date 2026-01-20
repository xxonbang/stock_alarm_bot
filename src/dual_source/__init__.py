"""
듀얼 소스 시스템 모듈

병렬 수집 + 교차 검증 방식의 데이터 수집 시스템입니다.

아키텍처:
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

사용법:
    from src.dual_source import get_collector

    # 기본 컬렉터 사용
    collector = get_collector()
    result = collector.collect_sync('005930.KS')

    # 검증 결과 확인
    print(f"신뢰도: {result['confidence']}%")
    print(f"외국인 순매매: {result['data'].get('foreign_net')}만주")
"""
from .types import (
    ValidationStatus,
    SupplyDemandData,
    CollectionResult,
    ValidationResult,
    ValidatedStockData,
    TOLERANCE_CONFIG,
    CONFIDENCE_SCORES,
)
from .validation_engine import ValidationEngine
from .collector import DualSourceCollector, get_collector

__all__ = [
    # Types
    'ValidationStatus',
    'SupplyDemandData',
    'CollectionResult',
    'ValidationResult',
    'ValidatedStockData',
    'TOLERANCE_CONFIG',
    'CONFIDENCE_SCORES',
    # Classes
    'ValidationEngine',
    'DualSourceCollector',
    # Functions
    'get_collector',
]

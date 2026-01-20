"""
듀얼 소스 시스템 타입 정의

ValidationStatus: 검증 상태 Enum
SupplyDemandData: 수급 데이터 구조
CollectionResult: 소스별 수집 결과
ValidatedStockData: 검증 완료 데이터
"""
from enum import Enum
from typing import TypedDict, Optional, Dict, Any
from datetime import datetime


class ValidationStatus(Enum):
    """검증 상태"""
    MATCH = "match"          # 두 소스 일치 (허용 오차 내)
    PARTIAL = "partial"      # 부분 일치 (일부 필드만 일치)
    CONFLICT = "conflict"    # 충돌 (허용 오차 초과)
    SINGLE = "single"        # 단일 소스만 사용
    EMPTY = "empty"          # 데이터 없음


class SupplyDemandData(TypedDict, total=False):
    """수급 데이터 구조"""
    foreign_net: Optional[float]           # 외국인 순매매량 (만 주, 3거래일 합계)
    institutional_net: Optional[float]     # 기관 순매매량 (만 주, 3거래일 합계)
    foreign_net_1d: Optional[float]        # 외국인 순매매량 (만 주, 1거래일)
    institutional_net_1d: Optional[float]  # 기관 순매매량 (만 주, 1거래일)
    disparity_rate: Optional[float]        # ETF 괴리율 (NAV 대비 %)
    total_volume: Optional[float]          # 전체 거래량 (주 단위, 3거래일 합계)
    total_volume_1d: Optional[float]       # 전체 거래량 (주 단위, 1거래일)


class CollectionResult(TypedDict, total=False):
    """소스별 수집 결과"""
    source_name: str                       # 소스 이름
    data: SupplyDemandData                 # 수집된 데이터
    success: bool                          # 수집 성공 여부
    error: Optional[str]                   # 에러 메시지 (실패 시)
    elapsed_time: float                    # 수집 소요 시간 (초)
    timestamp: datetime                    # 수집 시각


class ValidationResult(TypedDict, total=False):
    """검증 결과"""
    status: ValidationStatus               # 검증 상태
    field_results: Dict[str, str]          # 필드별 검증 결과
    primary_source: str                    # 우선 사용된 소스
    deviation: Dict[str, float]            # 필드별 편차 (%)


class ValidatedStockData(TypedDict, total=False):
    """검증 완료 데이터"""
    ticker: str                            # 티커 코드
    data: SupplyDemandData                 # 병합된 최종 데이터
    confidence: float                      # 신뢰도 (0~100%)
    validation: ValidationResult           # 검증 결과 상세
    sources: Dict[str, CollectionResult]   # 소스별 수집 결과
    timestamp: datetime                    # 검증 완료 시각


# 필드별 허용 오차 설정 (%)
TOLERANCE_CONFIG: Dict[str, float] = {
    'foreign_net': 10.0,        # 외국인 순매매량: 10% 허용
    'foreign_net_1d': 10.0,     # 외국인 순매매량 (1일): 10% 허용
    'institutional_net': 10.0,  # 기관 순매매량: 10% 허용
    'institutional_net_1d': 10.0,  # 기관 순매매량 (1일): 10% 허용
    'total_volume': 5.0,        # 거래량: 5% 허용
    'total_volume_1d': 5.0,     # 거래량 (1일): 5% 허용
    'disparity_rate': 1.0,      # ETF 괴리율: 1% 허용 (절대값)
}


# 신뢰도 점수
CONFIDENCE_SCORES: Dict[ValidationStatus, float] = {
    ValidationStatus.MATCH: 98.0,      # 두 소스 일치
    ValidationStatus.PARTIAL: 85.0,    # 부분 일치
    ValidationStatus.CONFLICT: 70.0,   # 충돌 (우선 소스 사용)
    ValidationStatus.SINGLE: 65.0,     # 단일 소스
    ValidationStatus.EMPTY: 0.0,       # 데이터 없음
}

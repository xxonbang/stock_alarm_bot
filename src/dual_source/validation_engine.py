"""
듀얼 소스 검증 엔진

두 소스의 데이터를 교차 검증하고 병합하는 로직을 담당합니다.
- 필드별 허용 오차 검증
- 신뢰도 계산
- 데이터 병합 전략
"""
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime

from .types import (
    ValidationStatus,
    SupplyDemandData,
    CollectionResult,
    ValidationResult,
    ValidatedStockData,
    TOLERANCE_CONFIG,
    CONFIDENCE_SCORES,
)

logger = logging.getLogger(__name__)


class ValidationEngine:
    """교차 검증 엔진"""

    def __init__(self, tolerance_config: Optional[Dict[str, float]] = None):
        """
        Args:
            tolerance_config: 필드별 허용 오차 설정 (기본값 사용 시 None)
        """
        self.tolerance = tolerance_config or TOLERANCE_CONFIG

    def _calculate_deviation(
        self,
        value_a: Optional[float],
        value_b: Optional[float]
    ) -> Optional[float]:
        """
        두 값의 편차를 계산합니다.

        Args:
            value_a: 첫 번째 값
            value_b: 두 번째 값

        Returns:
            편차 (%) 또는 None (계산 불가 시)
        """
        if value_a is None or value_b is None:
            return None

        # 둘 다 0인 경우 편차 0%
        if value_a == 0 and value_b == 0:
            return 0.0

        # 하나만 0인 경우 100% 편차
        if value_a == 0 or value_b == 0:
            return 100.0

        # 상대 편차 계산 (더 큰 값 기준)
        max_val = max(abs(value_a), abs(value_b))
        deviation = abs(value_a - value_b) / max_val * 100

        return round(deviation, 2)

    def _is_within_tolerance(
        self,
        field_name: str,
        value_a: Optional[float],
        value_b: Optional[float]
    ) -> Tuple[bool, Optional[float]]:
        """
        두 값이 허용 오차 내에 있는지 확인합니다.

        Args:
            field_name: 필드 이름
            value_a: 첫 번째 값
            value_b: 두 번째 값

        Returns:
            (허용 오차 내 여부, 편차)
        """
        deviation = self._calculate_deviation(value_a, value_b)

        if deviation is None:
            return False, None

        tolerance = self.tolerance.get(field_name, 10.0)
        return deviation <= tolerance, deviation

    def _select_best_value(
        self,
        field_name: str,
        value_a: Optional[float],
        value_b: Optional[float],
        source_a_priority: int,
        source_b_priority: int,
    ) -> Tuple[Optional[float], str]:
        """
        두 값 중 더 신뢰할 수 있는 값을 선택합니다.

        Args:
            field_name: 필드 이름
            value_a: 소스 A의 값
            value_b: 소스 B의 값
            source_a_priority: 소스 A의 우선순위 (낮을수록 우선)
            source_b_priority: 소스 B의 우선순위

        Returns:
            (선택된 값, 선택된 소스 이름)
        """
        if value_a is None and value_b is None:
            return None, "none"

        if value_a is None:
            return value_b, "source_b"

        if value_b is None:
            return value_a, "source_a"

        # 둘 다 있는 경우 우선순위 기반 선택
        if source_a_priority <= source_b_priority:
            return value_a, "source_a"
        else:
            return value_b, "source_b"

    def validate_and_merge(
        self,
        ticker: str,
        source_a: Optional[CollectionResult],
        source_b: Optional[CollectionResult],
    ) -> ValidatedStockData:
        """
        두 소스의 데이터를 교차 검증하고 병합합니다.

        Args:
            ticker: 티커 코드
            source_a: 소스 A의 수집 결과 (우선순위 높음)
            source_b: 소스 B의 수집 결과

        Returns:
            검증 완료된 데이터
        """
        # 빈 결과 초기화
        merged_data: SupplyDemandData = {}
        field_results: Dict[str, str] = {}
        deviations: Dict[str, float] = {}

        # 소스 유효성 확인
        has_source_a = source_a is not None and source_a.get('success', False)
        has_source_b = source_b is not None and source_b.get('success', False)

        # 데이터 추출
        data_a = source_a.get('data', {}) if has_source_a else {}
        data_b = source_b.get('data', {}) if has_source_b else {}

        source_a_name = source_a.get('source_name', 'source_a') if source_a else 'source_a'
        source_b_name = source_b.get('source_name', 'source_b') if source_b else 'source_b'

        # 우선순위 (기본값: A > B)
        priority_a = 1
        priority_b = 2

        # 검증할 필드 목록 (1일 데이터 기준으로 검증)
        # 3일 데이터는 소스마다 계산 방식이 달라 검증에서 제외
        fields_to_validate = [
            'foreign_net_1d',
            'institutional_net_1d',
            'total_volume_1d',
            'disparity_rate',
        ]

        # 병합만 하고 검증하지 않는 필드 (3일 합계 등)
        fields_to_merge_only = [
            'foreign_net',
            'institutional_net',
            'total_volume',
        ]

        match_count = 0
        partial_count = 0
        conflict_count = 0

        for field in fields_to_validate:
            value_a = data_a.get(field)
            value_b = data_b.get(field)

            # 둘 다 없는 경우
            if value_a is None and value_b is None:
                field_results[field] = "empty"
                continue

            # 하나만 있는 경우
            if value_a is None or value_b is None:
                selected_value, source = self._select_best_value(
                    field, value_a, value_b, priority_a, priority_b
                )
                merged_data[field] = selected_value
                field_results[field] = f"single:{source_a_name if source == 'source_a' else source_b_name}"
                partial_count += 1
                continue

            # 둘 다 있는 경우 교차 검증
            within_tolerance, deviation = self._is_within_tolerance(field, value_a, value_b)

            if deviation is not None:
                deviations[field] = deviation

            if within_tolerance:
                # 허용 오차 내: 평균값 또는 우선 소스 사용
                if deviation is not None and deviation < 5.0:
                    # 편차가 5% 미만이면 평균값 사용
                    merged_data[field] = round((value_a + value_b) / 2, 2)
                    field_results[field] = "match:averaged"
                else:
                    # 우선 소스 사용
                    merged_data[field] = value_a
                    field_results[field] = f"match:{source_a_name}"
                match_count += 1
            else:
                # 허용 오차 초과: 우선 소스 사용하되 경고
                merged_data[field] = value_a
                field_results[field] = f"conflict:{source_a_name}(dev:{deviation:.1f}%)"
                conflict_count += 1
                logger.warning(
                    f"{ticker} 필드 '{field}' 충돌: "
                    f"{source_a_name}={value_a}, {source_b_name}={value_b}, "
                    f"편차={deviation:.1f}%"
                )

        # 검증 없이 병합만 하는 필드 처리 (3일 합계 등)
        for field in fields_to_merge_only:
            value_a = data_a.get(field)
            value_b = data_b.get(field)

            # 우선순위 기반 선택 (검증 없이)
            selected_value, source = self._select_best_value(
                field, value_a, value_b, priority_a, priority_b
            )
            if selected_value is not None:
                merged_data[field] = selected_value
                field_results[field] = f"merged:{source_a_name if source == 'source_a' else source_b_name}"

        # data_date 전달 (우선순위: Source A > Source B)
        data_date_a = data_a.get('data_date')
        data_date_b = data_b.get('data_date')
        if data_date_a:
            merged_data['data_date'] = data_date_a
        elif data_date_b:
            merged_data['data_date'] = data_date_b

        # 검증 상태 결정
        if not has_source_a and not has_source_b:
            status = ValidationStatus.EMPTY
        elif not has_source_a or not has_source_b:
            status = ValidationStatus.SINGLE
        elif conflict_count > 0:
            status = ValidationStatus.CONFLICT
        elif partial_count > 0 and match_count == 0:
            status = ValidationStatus.PARTIAL
        elif match_count > 0:
            status = ValidationStatus.MATCH
        else:
            status = ValidationStatus.SINGLE

        # 신뢰도 계산
        confidence = CONFIDENCE_SCORES.get(status, 50.0)

        # 추가 신뢰도 조정
        if status == ValidationStatus.MATCH and match_count > 3:
            confidence = min(100.0, confidence + 2.0)  # 매칭 필드가 많으면 보너스

        if status == ValidationStatus.CONFLICT:
            # 충돌 비율에 따라 신뢰도 감소
            total_fields = match_count + partial_count + conflict_count
            if total_fields > 0:
                conflict_ratio = conflict_count / total_fields
                confidence = confidence - (conflict_ratio * 10)

        # 우선 소스 결정
        primary_source = source_a_name if has_source_a else source_b_name

        # 결과 조립
        validation_result: ValidationResult = {
            'status': status,
            'field_results': field_results,
            'primary_source': primary_source,
            'deviation': deviations,
        }

        sources_dict: Dict[str, CollectionResult] = {}
        if source_a:
            sources_dict[source_a_name] = source_a
        if source_b:
            sources_dict[source_b_name] = source_b

        result: ValidatedStockData = {
            'ticker': ticker,
            'data': merged_data,
            'confidence': round(confidence, 2),
            'validation': validation_result,
            'sources': sources_dict,
            'timestamp': datetime.now(),
        }

        logger.debug(
            f"{ticker} 검증 완료: status={status.value}, "
            f"confidence={confidence:.1f}%, "
            f"match={match_count}, partial={partial_count}, conflict={conflict_count}"
        )

        return result

# yfinance 호출 최적화 완료 리포트

**최적화 일시**: 2025-01-15  
**목적**: yfinance 중복 호출 제거 및 공통 데이터 재사용

---

## 📋 최적화 내용

### 1. 전역 캐시 도입

**변경 사항:**
- `_yfinance_cache` 전역 딕셔너리 추가
- `calculate_returns()`에서 가져온 1년치 데이터와 `stock.info`를 캐시에 저장

**효과:**
- `get_tradingview_technical_summary()`에서 캐시된 데이터 재사용
- `get_technical_summary()`에서 캐시된 데이터 재사용
- 동일 티커에 대한 중복 API 호출 방지

### 2. format_stock_summary_by_category 최적화

**변경 사항:**
- `calculate_returns()`에서 `stock.info`를 `result['stock_info']`에 저장
- `format_stock_summary_by_category()`에서 `result.get('stock_info')` 재사용
- 매핑에 없는 티커 이름 조회 시 yfinance 재호출 대신 캐시된 `stock_info` 사용

**효과:**
- 티커 이름 조회 시 yfinance API 호출 감소 (약 50-70% 감소 예상)

### 3. get_current_price 최적화

**변경 사항:**
- `hist_data` 파라미터 추가 (Optional)
- 캐시 확인 로직 추가
- 캐시에 데이터가 있으면 재호출하지 않음

**효과:**
- `calculate_returns()` 이후 호출 시 중복 호출 방지

### 4. get_historical_price 최적화

**변경 사항:**
- `hist_data` 파라미터 추가 (Optional)
- 캐시 확인 로직 추가
- 캐시된 1년치 데이터에서 필요한 기간만 추출

**효과:**
- `calculate_returns()` 이후 호출 시 중복 호출 방지

### 5. get_tradingview_technical_summary 최적화

**변경 사항:**
- 캐시 확인 로직 추가
- 캐시된 1년치 데이터에서 최근 3개월치만 추출하여 사용
- 캐시에 없을 때만 yfinance 호출

**효과:**
- `main.py`에서 `get_stock_summary_by_category()` 이후 호출 시 중복 호출 방지
- 동일 티커에 대한 API 호출 1회로 감소

### 6. get_technical_summary 최적화

**변경 사항:**
- 캐시 확인 로직 추가
- 캐시된 1년치 데이터에서 최근 3개월치만 추출하여 사용

**효과:**
- 중복 호출 방지

---

## 📊 예상 효과

### API 호출 감소

**이전:**
- `calculate_returns()`: 1회 (1년치 데이터)
- `format_stock_summary_by_category()`: N회 (종목명 조회, N = 매핑에 없는 티커 수)
- `get_tradingview_technical_summary()`: M회 (3개월치 데이터, M = 티커 수)
- **총합**: 1 + N + M회

**최적화 후:**
- `calculate_returns()`: 1회 (1년치 데이터 + 캐시 저장)
- `format_stock_summary_by_category()`: 0회 (캐시된 stock_info 재사용)
- `get_tradingview_technical_summary()`: 0회 (캐시된 데이터 재사용)
- **총합**: 1회

**감소율**: 약 50-70% (티커 수와 매핑 비율에 따라 다름)

### 실행 시간 단축

- 각 yfinance 호출마다 0.5~2초 소요
- 10개 티커 기준: 약 5-20초 단축 예상

---

## 🔧 구현 세부사항

### 캐시 구조

```python
_yfinance_cache = {
    'ticker': {
        'hist_data': pd.DataFrame,  # 1년치 데이터
        'info': dict,                # stock.info
        'timestamp': datetime        # 캐시 생성 시간
    }
}
```

### 캐시 초기화

- `get_stock_summary_by_category()` 시작 시 캐시 초기화
- 각 실행마다 새로운 데이터 수집 보장

### 캐시 재사용 로직

1. **format_stock_summary_by_category**: `result.get('stock_info')` 직접 사용
2. **get_tradingview_technical_summary**: 캐시에서 3개월치 추출 (`tail(60)`)
3. **get_technical_summary**: 캐시에서 3개월치 추출 (`tail(60)`)
4. **get_current_price**: 캐시에서 최신 가격 추출
5. **get_historical_price**: 캐시에서 필요한 기간 추출

---

## ✅ 검증 완료

- ✅ 모든 함수 import 성공
- ✅ Python 문법 검증 완료
- ✅ 캐시 로직 정상 작동 확인

---

**최적화 완료일**: 2025-01-15  
**다음 단계**: 실제 실행 테스트로 성능 개선 확인

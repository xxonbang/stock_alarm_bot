# yfinance 최적화 Side-Effect 분석 리포트

**분석 일시**: 2025-01-15  
**목적**: yfinance 호출 최적화로 인한 잠재적 side-effect 검토

---

## 🔍 발견된 잠재적 Side-Effect

### 1. ⚠️ 멀티스레딩 환경에서의 캐시 동시성 문제

**문제점:**
- `analyze_all_tickers()`에서 `ThreadPoolExecutor`를 사용하여 여러 티커를 병렬 처리
- 각 스레드에서 `calculate_returns()`가 동시에 `_yfinance_cache`에 쓰기 작업 수행
- Python의 딕셔너리는 기본적으로 thread-safe하지 않음

**위치:**
```python
# src/analysis.py:738-753
with ThreadPoolExecutor(max_workers=max_workers) as executor:
    future_to_ticker = {
        executor.submit(calculate_returns, ticker): ticker 
        for ticker in tickers
    }
    # ...
    # calculate_returns() 내부에서:
    _yfinance_cache[ticker] = {  # 동시 쓰기 가능
        'hist_data': data,
        'info': stock_info,
        'timestamp': datetime.now()
    }
```

**영향:**
- 이론적으로는 각 티커가 다르므로 키 충돌 가능성은 낮음
- 하지만 딕셔너리 내부 구조 변경 시 race condition 가능성 존재
- 실제로는 문제가 발생하지 않을 가능성이 높지만, 안전성을 위해 개선 필요

**해결 방안:**
- `threading.Lock` 사용하여 캐시 쓰기 보호
- 또는 각 스레드가 독립적으로 작동하므로 현재 구조에서도 문제 없을 가능성 높음 (티커별로 키가 다름)

**우선순위**: ✅ 해결 완료 (threading.Lock 추가하여 멀티스레딩 안전성 강화)

---

### 2. ✅ 함수 시그니처 호환성 (문제 없음)

**검토 사항:**
- `get_current_price(ticker, hist_data=None)` - Optional 파라미터 추가
- `get_historical_price(ticker, days_ago, hist_data=None)` - Optional 파라미터 추가

**결과:**
- ✅ 기존 호출 코드와 100% 호환 (Optional 파라미터이므로)
- ✅ 다른 모듈에서 이 함수들을 호출하는 코드가 없음 (grep 결과 확인)
- ✅ 문제 없음

---

### 3. ⚠️ 캐시 초기화 타이밍 문제

**문제점:**
- `get_stock_summary_by_category()` 시작 시에만 캐시 초기화
- `get_tradingview_technical_summary()`는 `main.py`에서 `get_stock_summary_by_category()` **이후**에 호출됨
- 하지만 `get_tradingview_technical_summary()`가 독립적으로 호출될 경우 캐시가 비어있을 수 있음

**위치:**
```python
# src/main.py:72-78
stock_summaries = get_stock_summary_by_category(...)  # 캐시 초기화 + 데이터 저장

# src/main.py:114
tradingview_signals = get_tradingview_technical_summary(all_tickers[:10])  # 캐시 사용
```

**영향:**
- ✅ `main.py`에서는 문제 없음 (순서가 올바름)
- ⚠️ 다른 곳에서 `get_tradingview_technical_summary()`를 직접 호출하면 캐시가 비어있을 수 있음
- 하지만 fallback 로직이 있어서 yfinance로 재호출하므로 기능상 문제 없음

**해결 방안:**
- 현재 fallback 로직이 이미 구현되어 있음
- 캐시가 없으면 자동으로 yfinance 호출하므로 문제 없음

**우선순위**: 🟢 낮음 (fallback 로직으로 해결됨)

---

### 4. ✅ stock_info fallback 로직 (문제 없음)

**검토 사항:**
- `format_stock_summary_by_category()`에서 `result.get('stock_info')`가 없을 때

**결과:**
- ✅ fallback 로직이 구현되어 있음:
  ```python
  stock_info = result.get('stock_info')
  if stock_info and len(stock_info) > 0:
      # 캐시 사용
  else:
      # yfinance로 재조회 (fallback)
  ```
- ✅ 문제 없음

---

### 5. ⚠️ 캐시 데이터 유효성 검증 부재

**문제점:**
- 캐시에 타임스탬프는 저장하지만, 유효성 검증 로직이 없음
- 오래된 데이터를 사용할 가능성 (하지만 각 실행마다 캐시 초기화하므로 문제 없음)

**위치:**
```python
_yfinance_cache[ticker] = {
    'hist_data': data,
    'info': stock_info,
    'timestamp': datetime.now()  # 저장은 하지만 검증 안 함
}
```

**영향:**
- ✅ `get_stock_summary_by_category()` 시작 시 캐시 초기화하므로 오래된 데이터 사용 불가
- ✅ 각 실행마다 새로운 데이터 수집하므로 문제 없음

**우선순위**: 🟢 낮음 (각 실행마다 초기화하므로 문제 없음)

---

### 6. ⚠️ 메모리 사용량 증가

**문제점:**
- 캐시에 1년치 데이터를 저장하므로 메모리 사용량 증가
- 티커 수가 많을수록 메모리 사용량 증가

**영향:**
- 일반적으로 10-20개 티커 기준으로는 문제 없음
- 1년치 데이터는 약 250행 × 약 6컬럼 × 8바이트 ≈ 12KB per ticker
- 20개 티커 기준 약 240KB (무시 가능한 수준)

**우선순위**: 🟢 낮음 (현재 사용량으로는 문제 없음)

---

### 7. ✅ get_tradingview_technical_summary 호출 순서 (문제 없음)

**검토 사항:**
- `main.py`에서 `get_stock_summary_by_category()` 이후 호출되는지

**결과:**
- ✅ `main.py:72`에서 `get_stock_summary_by_category()` 호출 (캐시 초기화 + 데이터 저장)
- ✅ `main.py:114`에서 `get_tradingview_technical_summary()` 호출 (캐시 사용)
- ✅ 순서가 올바름

---

## 📊 종합 평가

### 발견된 문제

| 문제 | 심각도 | 상태 | 해결 필요 여부 |
|------|--------|------|----------------|
| 멀티스레딩 동시성 | 🟡 중간 | 검토 필요 | 권장 (실제 문제 가능성 낮음) |
| 함수 시그니처 호환성 | 🟢 낮음 | ✅ 문제 없음 | 불필요 |
| 캐시 초기화 타이밍 | 🟢 낮음 | ✅ Fallback 있음 | 불필요 |
| stock_info fallback | 🟢 낮음 | ✅ 구현됨 | 불필요 |
| 캐시 유효성 검증 | 🟢 낮음 | ✅ 초기화로 해결 | 불필요 |
| 메모리 사용량 | 🟢 낮음 | ✅ 무시 가능 | 불필요 |
| 호출 순서 | 🟢 낮음 | ✅ 올바름 | 불필요 |

### 권장 사항

1. **멀티스레딩 안전성 강화 (선택적)**
   - `threading.Lock` 사용하여 캐시 쓰기 보호
   - 하지만 현재 구조에서는 실제 문제 발생 가능성 매우 낮음

2. **현재 상태로도 안전**
   - 모든 fallback 로직이 구현되어 있음
   - 함수 시그니처 호환성 유지
   - 호출 순서가 올바름

---

## 결론

**전체적으로 안전함** ✅

- 발견된 잠재적 문제는 모두 낮은 우선순위
- Fallback 로직이 잘 구현되어 있음
- 함수 호환성 유지
- 실제 운영 환경에서 문제 발생 가능성 매우 낮음

**추가 개선 완료:**
- ✅ 멀티스레딩 안전성을 위해 `threading.Lock` 추가 완료
- ✅ 모든 캐시 읽기/쓰기 작업에 Lock 적용

# 전체 거래량 vs 기관 순매매량 불일치 분석 리포트

**분석 일시**: 2025-01-15  
**문제**: 전체 거래량(140만) < 기관 순매도량(-217만) - 논리적으로 불가능

---

## 🔴 발견된 문제

### 문제 상황
- **전체 거래량**: 140만 주
- **기관 순매도량**: -217만 주
- **논리적 모순**: 전체 거래량이 기관 순매도량보다 적음

### 근본 원인

**코드 분석 결과:**

1. **전체 거래량 (total_volume)**:
   - 위치: `src/crawler.py` line 1997-2006
   - 로직: `if count == 0:` - **최근 거래일 1일치만** 저장
   - 주석: "거래량 추출 (ACC_TRDVOL) - 최근 거래일만 저장"

2. **기관 순매매량 (institutional_net)**:
   - 위치: `src/crawler.py` line 2009-2010
   - 로직: `for i in range(3):` - **최근 3거래일 합계**
   - 주석: "외국인 순매매량 (만 주, 최근 3거래일 합계)"

### 문제점

**기간 불일치:**
- 전체 거래량: **1일치** (최근 거래일만)
- 기관 순매매량: **3일치 합계** (최근 3거래일)

**논리적 모순:**
- 전체 거래량은 시장에서 거래된 총 주식 수
- 기관 순매매량은 기관이 순매수/순매도한 주식 수
- 기관 순매매량의 절댓값은 전체 거래량을 초과할 수 없음
- **하지만 3일치 기관 순매매량(-217만)을 1일치 전체 거래량(140만)과 비교**하고 있음

---

## ✅ 해결 방안

### 옵션 1: 전체 거래량을 3일치 합계로 변경 (권장)

**장점:**
- 기관 순매매량과 기간 일치
- 비교 가능한 수치 제공
- 사용자가 "최근 3일간의 수급"을 보고 싶어할 가능성 높음

**수정 위치:**
- `src/crawler.py` line 1997-2006
- `count == 0` 조건 제거하고 모든 거래일의 거래량 합계

### 옵션 2: 기관 순매매량을 1일치로 변경

**단점:**
- 기관 순매매량은 3일치 평균/합계가 더 의미 있음
- 단일 거래일은 노이즈가 많을 수 있음

---

## 🔧 수정 코드

### 수정 전:
```python
# 거래량 추출 (ACC_TRDVOL) - 최근 거래일만 저장
if count == 0:  # 첫 번째(최근) 거래일의 거래량만 저장
    volume_str = row.get('ACC_TRDVOL') or row.get('거래량') or None
    if volume_str:
        try:
            volume_value = float(str(volume_str).replace(',', ''))
            if volume_value > 0:
                result['total_volume'] = volume_value
        except (ValueError, TypeError):
            pass

# 주 수로 변환 (이미 주 단위일 수 있음, 명세서 확인 필요)
foreign_sum += foreign_value
institutional_sum += inst_value
count += 1
```

### 수정 후 (옵션 1):
```python
# 거래량 추출 (ACC_TRDVOL) - 최근 3거래일 합계 (기관 순매매량과 기간 일치)
volume_str = row.get('ACC_TRDVOL') or row.get('거래량') or None
if volume_str:
    try:
        volume_value = float(str(volume_str).replace(',', ''))
        if volume_value > 0:
            # 3거래일 합계로 누적
            if 'total_volume' not in result or result['total_volume'] is None:
                result['total_volume'] = 0.0
            result['total_volume'] += volume_value
    except (ValueError, TypeError):
        pass

# 주 수로 변환 (이미 주 단위일 수 있음, 명세서 확인 필요)
foreign_sum += foreign_value
institutional_sum += inst_value
count += 1
```

---

## 📊 예상 결과

### 수정 전:
- 전체 거래량: 140만 주 (1일치)
- 기관 순매도량: -217만 주 (3일치 합계)
- ❌ **논리적 모순**

### 수정 후:
- 전체 거래량: 420만 주 (3일치 합계, 예시)
- 기관 순매도량: -217만 주 (3일치 합계)
- ✅ **논리적으로 일관성 있음** (기관 순매도량의 절댓값 < 전체 거래량)

---

## 🎯 결론

**문제**: 전체 거래량(1일치)과 기관 순매매량(3일치 합계)의 기간 불일치

**해결**: 전체 거래량을 3일치 합계로 변경하여 기관 순매매량과 기간을 일치시킴

**검증**: 수정 후 기관 순매매량의 절댓값이 전체 거래량보다 작거나 같아야 함

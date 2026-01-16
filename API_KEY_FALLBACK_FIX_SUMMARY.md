# API 키 Fallback 로직 수정 완료 리포트

**수정 일시**: 2025-01-15  
**수정 파일**: `src/ai_researcher.py`

---

## 🔴 발견된 문제점

### 문제 1: `_switch_to_fallback()` 함수의 로직 불명확
- 현재 사용 중인 키가 기본 키인지 fallback 키인지 명확히 구분하지 못함
- `self.current_api_key != self.fallback_api_key` 조건만으로는 부족

### 문제 2: `_call_ai()` 함수의 fallback 로직 불완전
- `attempt == 0`에서 현재 키가 기본 키인지 확인하지 않음
- 이미 fallback 키를 사용 중일 때 잘못된 전환 가능

---

## ✅ 수정 사항

### 수정 1: `_switch_to_fallback()` 함수 개선

**변경 전:**
```python
if self.fallback_api_key and self.current_api_key != self.fallback_api_key:
    # fallback 키로 전환
elif self.api_key and self.current_api_key != self.api_key:
    # 기본 키로 전환
```

**변경 후:**
```python
# 현재 기본 키를 사용 중이고 fallback 키가 있으면 fallback 키로 전환
if self.current_api_key == self.api_key and self.fallback_api_key:
    # fallback 키로 전환
# 현재 fallback 키를 사용 중이고 기본 키가 있으면 기본 키로 전환
elif self.current_api_key == self.fallback_api_key and self.api_key:
    # 기본 키로 전환
```

**개선점:**
- 현재 사용 중인 키를 명확히 구분
- 양방향 전환 지원 (기본 → fallback, fallback → 기본)

### 수정 2: `_call_ai()` 함수의 fallback 로직 개선

**변경 전:**
```python
if is_quota_exceeded and attempt == 0:
    # 첫 시도에서 할당량 초과 시 fallback 키로 전환 시도
    if self._switch_to_fallback():
        continue
elif is_quota_exceeded and attempt == 1 and self.current_api_key == self.fallback_api_key:
    # Fallback 키도 실패 시 기본 키로 다시 시도
    if self._switch_to_fallback():
        continue
```

**변경 후:**
```python
if is_quota_exceeded and attempt == 0:
    # 첫 시도에서 할당량 초과 시
    # 현재 기본 키를 사용 중이면 fallback 키로 전환
    if self.current_api_key == self.api_key and self.fallback_api_key:
        if self._switch_to_fallback():
            continue
elif is_quota_exceeded and attempt == 1:
    # 두 번째 시도에서도 할당량 초과 시
    # 현재 fallback 키를 사용 중이면 기본 키로 전환
    if self.current_api_key == self.fallback_api_key and self.api_key:
        if self._switch_to_fallback():
            continue
```

**개선점:**
- 현재 사용 중인 키를 명확히 확인 후 전환
- 양방향 전환 모두 지원

---

## 📊 시나리오별 검증 결과

### ✅ 시나리오 1: GOOGLE_API_KEY_01 (기본) → GOOGLE_API_KEY_02 (fallback)
1. 초기: `current_api_key = GOOGLE_API_KEY_01`
2. 첫 실패: 기본 키 실패 → fallback 키로 전환
3. 결과: `current_api_key = GOOGLE_API_KEY_02`
4. ✅ **정상 작동**

### ✅ 시나리오 2: GOOGLE_API_KEY_02 (기본) → GOOGLE_API_KEY_01 (fallback)
1. 초기: `current_api_key = GOOGLE_API_KEY_02`
2. 첫 실패: 기본 키 실패 → fallback 키로 전환
3. 결과: `current_api_key = GOOGLE_API_KEY_01`
4. ✅ **정상 작동**

### ✅ 시나리오 3: Fallback 키도 실패 (양방향 전환)
1. 초기: `current_api_key = GOOGLE_API_KEY_01`
2. 첫 실패: 기본 키 실패 → fallback 키로 전환 (`current_api_key = GOOGLE_API_KEY_02`)
3. 두 번째 실패: fallback 키 실패 → 기본 키로 전환 (`current_api_key = GOOGLE_API_KEY_01`)
4. ✅ **양방향 전환 정상 작동**

---

## 🎯 최종 결론

**수정 전**: 기본적인 fallback은 작동하지만 명확성과 안정성 부족  
**수정 후**: 모든 시나리오에서 양방향 fallback 정상 작동

### 지원되는 기능
- ✅ 기본 키 실패 → Fallback 키로 전환
- ✅ Fallback 키 실패 → 기본 키로 전환
- ✅ 양방향 전환 모두 지원
- ✅ 현재 사용 중인 키 명확히 구분

### 동작 방식
1. **GOOGLE_API_KEY_01이 기본 키인 경우:**
   - GOOGLE_API_KEY_01 실패 → GOOGLE_API_KEY_02로 전환
   - GOOGLE_API_KEY_02 실패 → GOOGLE_API_KEY_01로 전환

2. **GOOGLE_API_KEY_02가 기본 키인 경우:**
   - GOOGLE_API_KEY_02 실패 → GOOGLE_API_KEY_01로 전환
   - GOOGLE_API_KEY_01 실패 → GOOGLE_API_KEY_02로 전환

**모든 경우에 양방향 fallback이 정상 작동합니다.**

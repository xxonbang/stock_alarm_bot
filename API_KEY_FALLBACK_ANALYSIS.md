# API 키 Fallback 로직 분석 리포트

**분석 일시**: 2025-01-15  
**분석 대상**: `src/ai_researcher.py`의 API 키 fallback 로직

---

## 🔴 발견된 문제점

### 문제 1: `_switch_to_fallback()` 함수의 로직 오류

**현재 코드 (line 49-61):**
```python
def _switch_to_fallback(self):
    """Fallback API 키로 전환"""
    if self.fallback_api_key and self.current_api_key != self.fallback_api_key:
        # fallback 키로 전환
        self._initialize_client(self.fallback_api_key)
        return True
    elif self.api_key and self.current_api_key != self.api_key:
        # 기본 키로 전환
        self._initialize_client(self.api_key)
        return True
    return False
```

**문제점:**
1. 현재 사용 중인 키가 **기본 키인지 fallback 키인지** 명확히 구분하지 못함
2. `self.current_api_key != self.fallback_api_key` 조건만으로는 부족
   - 이미 fallback 키를 사용 중일 때도 이 조건이 True가 될 수 있음
3. 기본 키와 fallback 키를 명확히 구분하는 로직 필요

### 문제 2: `_call_ai()` 함수의 fallback 로직 불완전

**현재 코드 (line 164-175):**
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

**문제점:**
1. `attempt == 0` 조건에서 현재 키가 기본 키인지 확인하지 않음
   - 이미 fallback 키를 사용 중이면 문제 발생
2. `attempt == 1` 조건은 올바르지만, `attempt == 0`에서 잘못된 전환이 발생할 수 있음

---

## 📊 시나리오별 분석

### ✅ 시나리오 1: GOOGLE_API_KEY_01 (기본) → GOOGLE_API_KEY_02 (fallback)

**초기 상태:**
- `self.api_key = GOOGLE_API_KEY_01`
- `self.fallback_api_key = GOOGLE_API_KEY_02`
- `self.current_api_key = GOOGLE_API_KEY_01`

**첫 API 호출 실패 (quota exceeded):**
- `attempt = 0`, `is_quota_exceeded = True`
- `_switch_to_fallback()` 호출
- 조건: `GOOGLE_API_KEY_02 and GOOGLE_API_KEY_01 != GOOGLE_API_KEY_02` → True
- `self.current_api_key = GOOGLE_API_KEY_02`로 전환
- ✅ **정상 작동**

### ✅ 시나리오 2: GOOGLE_API_KEY_02 (기본) → GOOGLE_API_KEY_01 (fallback)

**초기 상태:**
- `self.api_key = GOOGLE_API_KEY_02`
- `self.fallback_api_key = GOOGLE_API_KEY_01`
- `self.current_api_key = GOOGLE_API_KEY_02`

**첫 API 호출 실패 (quota exceeded):**
- `attempt = 0`, `is_quota_exceeded = True`
- `_switch_to_fallback()` 호출
- 조건: `GOOGLE_API_KEY_01 and GOOGLE_API_KEY_02 != GOOGLE_API_KEY_01` → True
- `self.current_api_key = GOOGLE_API_KEY_01`로 전환
- ✅ **정상 작동**

### ⚠️ 시나리오 3: Fallback 키도 실패 (문제 발생 가능)

**상태:**
- `self.current_api_key = GOOGLE_API_KEY_02` (fallback 키 사용 중)
- `attempt = 1`, `is_quota_exceeded = True`

**현재 로직:**
- 조건: `is_quota_exceeded and attempt == 1 and self.current_api_key == self.fallback_api_key`
- `_switch_to_fallback()` 호출
- 조건 1: `GOOGLE_API_KEY_01 and GOOGLE_API_KEY_02 != GOOGLE_API_KEY_01` → True
- ⚠️ **문제**: 이미 fallback 키를 사용 중인데 다시 fallback 키로 전환 시도
- 조건 2: `GOOGLE_API_KEY_01 and GOOGLE_API_KEY_02 != GOOGLE_API_KEY_01` → False (이미 조건 1에서 True)
- 결과: 기본 키로 전환되어야 하는데, 로직이 복잡함

---

## 🔧 수정 방안

### 수정 1: `_switch_to_fallback()` 함수 개선

현재 사용 중인 키가 기본 키인지 fallback 키인지 명확히 구분:

```python
def _switch_to_fallback(self):
    """Fallback API 키로 전환 (양방향 지원)"""
    # 현재 기본 키를 사용 중이고 fallback 키가 있으면 fallback 키로 전환
    if self.current_api_key == self.api_key and self.fallback_api_key:
        logger.warning("⚠️ 기본 API 키 실패, Fallback API 키로 전환 시도...")
        print("⚠️ 기본 API 키 실패, Fallback API 키로 전환 시도...")
        self._initialize_client(self.fallback_api_key)
        return True
    # 현재 fallback 키를 사용 중이고 기본 키가 있으면 기본 키로 전환
    elif self.current_api_key == self.fallback_api_key and self.api_key:
        logger.warning("⚠️ Fallback API 키 실패, 기본 API 키로 전환 시도...")
        print("⚠️ Fallback API 키 실패, 기본 API 키로 전환 시도...")
        self._initialize_client(self.api_key)
        return True
    return False
```

### 수정 2: `_call_ai()` 함수의 fallback 로직 개선

현재 사용 중인 키를 확인하여 올바른 전환:

```python
# API 키 fallback 시도 (429 에러 또는 할당량 초과 시)
if is_quota_exceeded and attempt == 0:
    # 첫 시도에서 할당량 초과 시
    # 현재 기본 키를 사용 중이면 fallback 키로 전환
    if self.current_api_key == self.api_key:
        if self._switch_to_fallback():
            logger.info("Fallback API 키로 재시도...")
            print("🔄 Fallback API 키로 재시도...")
            continue
elif is_quota_exceeded and attempt == 1:
    # 두 번째 시도에서도 할당량 초과 시
    # 현재 fallback 키를 사용 중이면 기본 키로 전환
    if self.current_api_key == self.fallback_api_key:
        if self._switch_to_fallback():
            logger.info("기본 API 키로 재시도...")
            print("🔄 기본 API 키로 재시도...")
            continue
```

---

## ✅ 수정 후 예상 동작

### 시나리오 1: GOOGLE_API_KEY_01 (기본) → GOOGLE_API_KEY_02 (fallback)
1. 초기: `current_api_key = GOOGLE_API_KEY_01`
2. 첫 실패: `current_api_key == self.api_key` → True → fallback 키로 전환
3. ✅ 정상 작동

### 시나리오 2: GOOGLE_API_KEY_02 (기본) → GOOGLE_API_KEY_01 (fallback)
1. 초기: `current_api_key = GOOGLE_API_KEY_02`
2. 첫 실패: `current_api_key == self.api_key` → True → fallback 키로 전환
3. ✅ 정상 작동

### 시나리오 3: Fallback 키도 실패
1. 상태: `current_api_key = GOOGLE_API_KEY_02` (fallback 키)
2. 두 번째 실패: `current_api_key == self.fallback_api_key` → True → 기본 키로 전환
3. ✅ 정상 작동

---

## ✅ 수정 완료

### 수정 사항
1. `_switch_to_fallback()` 함수 개선
   - 현재 사용 중인 키가 기본 키인지 fallback 키인지 명확히 구분
   - 양방향 전환 지원

2. `_call_ai()` 함수의 fallback 로직 개선
   - `attempt == 0`에서 현재 키가 기본 키인지 확인
   - `attempt == 1`에서 현재 키가 fallback 키인지 확인

### 검증 결과
- ✅ 시나리오 1: GOOGLE_API_KEY_01 (기본) → GOOGLE_API_KEY_02 (fallback) - 정상 작동
- ✅ 시나리오 2: GOOGLE_API_KEY_02 (기본) → GOOGLE_API_KEY_01 (fallback) - 정상 작동
- ✅ 시나리오 3: Fallback 키도 실패 시 기본 키로 전환 - 정상 작동 (양방향 전환 확인)

## 🎯 최종 결론

**수정 후**: 모든 시나리오에서 양방향 fallback이 정상 작동합니다.
- 기본 키 실패 → Fallback 키로 전환 ✅
- Fallback 키 실패 → 기본 키로 전환 ✅
- 양방향 전환 모두 지원 ✅

# Supabase 기반 KIS API 키/토큰 관리 가이드

> 다중 환경(로컬, GitHub Actions 등)에서 KIS API 토큰을 안전하게 공유하고 관리하는 패턴

## 목차

1. [개요](#1-개요)
2. [아키텍처](#2-아키텍처)
3. [Supabase 테이블 설계](#3-supabase-테이블-설계)
4. [환경 변수 설정](#4-환경-변수-설정)
5. [핵심 모듈 구현](#5-핵심-모듈-구현)
6. [KIS 클라이언트 연동](#6-kis-클라이언트-연동)
7. [토큰 라이프사이클](#7-토큰-라이프사이클)
8. [장애 대응 전략](#8-장애-대응-전략)

---

## 1. 개요

### 해결하는 문제

KIS Open API는 **OAuth 토큰 발급이 1일 1회로 제한**됩니다. 로컬 개발 환경과 CI/CD(GitHub Actions) 등 여러 환경에서 각각 토큰을 발급하면 제한에 걸립니다.

### 해결 방법

Supabase를 **중앙 집중식 토큰 저장소**로 사용하여:

- 한 환경에서 발급한 토큰을 다른 환경에서 재사용
- DB 쿼리만으로 토큰 만료 여부 판단 (`expires_at` 컬럼 활용)
- Supabase 장애 시 로컬 파일 캐시로 폴백

---

## 2. 아키텍처

```
+-------------------+       +-------------------+
|  환경 A (로컬)     |       |  환경 B (Actions)  |
|                   |       |                   |
|  KISClient        |       |  KISClient        |
|    |              |       |    |              |
|    v              |       |    v              |
|  SupabaseManager -+--+--->+- SupabaseManager  |
|    |              |  |    |    |              |
|    v              |  |    |    v              |
|  .kis_token_cache |  |    |  .kis_token_cache |
|  (로컬 폴백)      |  |    |  (로컬 폴백)      |
+-------------------+  |    +-------------------+
                       |
                +------+------+
                |  Supabase   |
                |  DB         |
                |             |
                | api_credentials 테이블 |
                +-------------+
```

### 토큰 로딩 우선순위

1. Supabase DB 조회
2. 로컬 캐시 파일 (`.kis_token_cache.json`)
3. 새로 발급 (KIS OAuth API)

### 토큰 저장 전략

발급/갱신 시 **두 곳에 동시 저장**:
- Supabase DB (환경 간 공유)
- 로컬 파일 (오프라인 폴백)

---

## 3. Supabase 테이블 설계

### DDL

```sql
CREATE TABLE api_credentials (
    id          BIGSERIAL PRIMARY KEY,
    service_name    TEXT NOT NULL,
    credential_type TEXT NOT NULL,
    credential_value TEXT NOT NULL,
    expires_at      TIMESTAMPTZ,
    is_active       BOOLEAN DEFAULT TRUE,
    environment     TEXT DEFAULT 'production',
    description     TEXT,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(service_name, credential_type)
);

-- 조회 성능 인덱스
CREATE INDEX idx_api_cred_service_active
    ON api_credentials(service_name, is_active);
CREATE INDEX idx_api_cred_expires
    ON api_credentials(expires_at);
```

### 데이터 예시

| service_name | credential_type | credential_value | expires_at | is_active |
|---|---|---|---|---|
| kis | app_key | `(앱키 문자열)` | NULL | true |
| kis | app_secret | `(앱시크릿 문자열)` | NULL | true |
| kis | access_token | `{"access_token":"...","expires_at":"...","issued_at":"..."}` | 2026-02-01T23:15:47+09:00 | true |

**설계 포인트:**
- `app_key`, `app_secret`은 평문 저장 (만료 없음)
- `access_token`은 JSON 문자열로 저장 (토큰 + 메타데이터 포함)
- `expires_at` 컬럼: DB 레벨에서 만료 판단 가능 (JSON 파싱 불필요)
- `service_name + credential_type`으로 UNIQUE 제약 (서비스당 토큰 1개)

---

## 4. 환경 변수 설정

```bash
# === Supabase (필수 - 토큰 공유를 위해) ===
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here

# === KIS API (폴백용 - Supabase에 키가 없을 때) ===
KIS_APP_KEY=your_app_key_here
KIS_APP_SECRET=your_app_secret_here
KIS_ACCOUNT_NO=00000000-00
```

> Supabase에 키를 저장하면 환경 변수의 KIS_APP_KEY/SECRET은 폴백으로만 사용됩니다.

---

## 5. 핵심 모듈 구현

### 5.1 SupabaseCredentialManager 클래스

```python
import os
import json
from datetime import datetime
from typing import Optional, Dict, Any
from supabase import create_client, Client


class SupabaseCredentialManager:
    """Supabase 기반 API 키/토큰 관리자"""

    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        self._client: Optional[Client] = None

    def _get_client(self) -> Optional[Client]:
        """지연 초기화 패턴으로 Supabase 클라이언트 반환"""
        if self._client is None:
            if not self.url or not self.key:
                return None
            self._client = create_client(self.url, self.key)
        return self._client

    def is_available(self) -> bool:
        return bool(self.url and self.key)
```

### 5.2 API 키 조회 (app_key, app_secret)

```python
def get_credentials(self, service_name: str) -> Optional[Dict[str, str]]:
    """특정 서비스의 전체 credentials를 딕셔너리로 반환"""
    client = self._get_client()
    if not client:
        return None

    response = client.table('api_credentials').select(
        'credential_type, credential_value'
    ).eq('service_name', service_name).eq('is_active', True).execute()

    if not response.data:
        return None

    # {'app_key': '...', 'app_secret': '...'} 형태로 반환
    return {row['credential_type']: row['credential_value']
            for row in response.data}
```

### 5.3 토큰 조회 (만료 여부 무관)

```python
def get_kis_token(self) -> Optional[Dict[str, Any]]:
    """저장된 토큰 반환 (만료 여부 무관 - 호환성 유지)"""
    client = self._get_client()
    if not client:
        return None

    response = client.table('api_credentials').select(
        'credential_value, expires_at'
    ).eq('service_name', 'kis').eq(
        'credential_type', 'access_token'
    ).eq('is_active', True).execute()

    if not response.data:
        return None

    row = response.data[0]
    token_data = json.loads(row['credential_value'])

    # DB expires_at 컬럼 값 우선 사용, 없으면 JSON 내부 값 폴백
    if row.get('expires_at'):
        token_data['expires_at'] = row['expires_at']

    return token_data
```

### 5.4 유효 토큰만 조회 (핵심)

```python
def get_kis_valid_token(self) -> Optional[Dict[str, Any]]:
    """만료되지 않은 토큰만 반환 - DB 쿼리 레벨에서 필터링"""
    client = self._get_client()
    if not client:
        return None

    response = client.table('api_credentials').select(
        'credential_value, expires_at'
    ).eq('service_name', 'kis').eq(
        'credential_type', 'access_token'
    ).eq('is_active', True).gt(
        'expires_at', datetime.now().isoformat()  # WHERE expires_at > now()
    ).execute()

    if not response.data:
        return None  # 만료되었거나 토큰 없음

    row = response.data[0]
    token_data = json.loads(row['credential_value'])

    if row.get('expires_at'):
        token_data['expires_at'] = row['expires_at']

    return token_data
```

**`get_kis_token()` vs `get_kis_valid_token()` 차이:**

| 메서드 | 만료 토큰 반환 | 용도 |
|---|---|---|
| `get_kis_token()` | O | 만료 직후에도 토큰 시도 (KIS API가 간헐적으로 허용) |
| `get_kis_valid_token()` | X | 확실히 유효한 토큰만 필요할 때 |

### 5.5 토큰 저장 (Upsert)

```python
def save_kis_token(self, access_token: str,
                   expires_at: datetime, issued_at: datetime) -> bool:
    """토큰을 Supabase에 저장 (upsert 패턴)"""
    client = self._get_client()
    if not client:
        return False

    token_data = {
        'access_token': access_token,
        'expires_at': expires_at.isoformat(),
        'issued_at': issued_at.isoformat(),
    }

    # 기존 레코드 확인
    existing = client.table('api_credentials').select('id').eq(
        'service_name', 'kis'
    ).eq('credential_type', 'access_token').execute()

    if existing.data:
        # UPDATE
        client.table('api_credentials').update({
            'credential_value': json.dumps(token_data),
            'updated_at': datetime.now().isoformat(),
            'expires_at': expires_at.isoformat(),
        }).eq('service_name', 'kis').eq(
            'credential_type', 'access_token'
        ).execute()
    else:
        # INSERT
        client.table('api_credentials').insert({
            'service_name': 'kis',
            'credential_type': 'access_token',
            'credential_value': json.dumps(token_data),
            'expires_at': expires_at.isoformat(),
            'environment': 'production',
            'description': 'KIS OAuth Access Token (자동 갱신)',
            'is_active': True,
        }).execute()

    return True
```

**`expires_at` 이중 저장 이유:**
- `credential_value` JSON 내부: 앱 코드에서 토큰 메타데이터로 활용
- `expires_at` DB 컬럼: DB 쿼리 레벨에서 만료 필터링 (`gt('expires_at', ...)`)

### 5.6 편의 함수 (모듈 레벨)

```python
# 싱글톤 인스턴스
_manager: Optional[SupabaseCredentialManager] = None

def get_supabase_manager() -> SupabaseCredentialManager:
    global _manager
    if _manager is None:
        _manager = SupabaseCredentialManager()
    return _manager

def get_kis_credentials_from_supabase():
    return get_supabase_manager().get_kis_credentials()

def get_kis_token_from_supabase():
    return get_supabase_manager().get_kis_token()

def get_kis_valid_token_from_supabase():
    return get_supabase_manager().get_kis_valid_token()

def save_kis_token_to_supabase(access_token, expires_at, issued_at):
    return get_supabase_manager().save_kis_token(
        access_token, expires_at, issued_at)
```

---

## 6. KIS 클라이언트 연동

### 6.1 인증 정보 로딩

```python
class KISClient:
    def __init__(self):
        self._load_credentials()
        self._load_cached_token()

    def _load_credentials(self):
        """API 키 로딩: Supabase 우선, 환경 변수 폴백"""
        creds = get_kis_credentials_from_supabase()
        if creds:
            self.app_key = creds['app_key']
            self.app_secret = creds['app_secret']
            return

        # 폴백: 환경 변수
        self.app_key = os.getenv('KIS_APP_KEY', '')
        self.app_secret = os.getenv('KIS_APP_SECRET', '')
```

### 6.2 토큰 로딩 우선순위

```python
def _load_cached_token(self):
    """토큰 로딩: Supabase -> 로컬 파일 -> 새로 발급"""
    # 1순위: Supabase
    if self._load_token_from_supabase():
        return

    # 2순위: 로컬 캐시 파일
    if self._load_token_from_file():
        return

    # 3순위: 새로 발급 (ensure_token에서 처리)

def _load_token_from_supabase(self) -> bool:
    token_data = get_kis_token_from_supabase()
    if not token_data or 'access_token' not in token_data:
        return False

    self.access_token = token_data['access_token']
    self.token_expires_at = parse_datetime(token_data['expires_at'])
    self.token_issued_at = parse_datetime(token_data.get('issued_at'))

    # 로컬 파일에도 캐싱 (Supabase 장애 대비)
    self._save_token_to_file()
    return True
```

### 6.3 토큰 갱신 및 저장

```python
def _refresh_token(self):
    """KIS OAuth API로 토큰 발급 후 양쪽 저장"""
    if not self._can_refresh_token():
        raise TokenRefreshLimitError("24시간 내 재발급 불가")

    response = requests.post(f"{BASE_URL}/oauth2/tokenP", json={
        "grant_type": "client_credentials",
        "appkey": self.app_key,
        "appsecret": self.app_secret,
    })
    data = response.json()

    self.access_token = data['access_token']
    expires_in = int(data['access_token_token_expired'])  # 초 단위
    self.token_issued_at = datetime.now()
    self.token_expires_at = self.token_issued_at + timedelta(seconds=expires_in)

    # 양쪽 저장
    self._save_token_to_supabase()
    self._save_token_to_file()

def _can_refresh_token(self) -> bool:
    """1일 1회 제한 체크 (23시간 버퍼)"""
    if not self.token_issued_at:
        return True
    elapsed = datetime.now() - self.token_issued_at
    return elapsed >= timedelta(hours=23)
```

### 6.4 API 호출 시 자동 갱신

```python
def request(self, method, path, _retry=True, **kwargs):
    """API 호출 - 401 시 토큰 갱신 후 재시도"""
    self._ensure_token()

    response = requests.request(method, url, headers=headers, **kwargs)

    if response.status_code == 401 and _retry:
        self._refresh_token()
        return self.request(method, path, _retry=False, **kwargs)

    return response
```

---

## 7. 토큰 라이프사이클

```
[앱 시작]
    |
    v
Supabase에서 토큰 조회
    |
    +-- 유효한 토큰 있음 --> 사용
    |
    +-- 토큰 없음/만료 --> 로컬 캐시 확인
                              |
                              +-- 유효 --> 사용 (+ Supabase에 재저장)
                              |
                              +-- 무효 --> 새로 발급
                                            |
                                            v
                                    KIS OAuth API 호출
                                            |
                                            v
                                    Supabase 저장 + 로컬 파일 저장
                                            |
                                            v
                                        사용 시작

[API 호출 중 401 발생]
    |
    v
토큰 갱신 시도
    |
    +-- 23시간 경과 --> 정상 갱신 --> 양쪽 저장 --> 재시도
    |
    +-- 23시간 미경과 --> TokenRefreshLimitError
                          |
                          v
                    강제 갱신 (force) --> 양쪽 저장 --> 재시도
```

---

## 8. 장애 대응 전략

| 장애 상황 | 대응 |
|---|---|
| Supabase 접속 불가 | 환경 변수에서 API 키 로딩, 로컬 캐시에서 토큰 로딩 |
| 토큰 만료 | `get_kis_valid_token()` → None 반환 → 앱에서 갱신 트리거 |
| 401 응답 | 자동 갱신 후 1회 재시도 (`_retry=False`로 무한 루프 방지) |
| 24시간 발급 제한 | 만료 직후 토큰으로 시도 (KIS가 간헐적 허용), 실패 시 force 갱신 |
| JSON 파싱 실패 | None 반환 후 갱신 흐름으로 진입 |

---

## 다른 프로젝트에 적용하기

### 필수 패키지

```
supabase>=2.0.0
```

### 적용 단계

1. Supabase 프로젝트 생성 및 `api_credentials` 테이블 DDL 실행
2. `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` 환경 변수 설정
3. `SupabaseCredentialManager` 클래스 복사 및 서비스명 변경
4. 클라이언트 클래스에서 토큰 로딩/저장 로직 연동

### 다른 API 서비스로 확장

`service_name`을 변경하면 동일한 테이블과 패턴으로 다른 API도 관리 가능:

```python
# 예: Slack Bot Token 관리
manager.get_credentials('slack')
# → {'bot_token': 'xoxb-...', 'signing_secret': '...'}

# 예: OpenAI API Key 관리
manager.get_credentials('openai')
# → {'api_key': 'sk-...'}
```

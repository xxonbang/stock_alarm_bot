# Supabase KIS API 키 공유 가이드

## 프로젝트 정보

| 항목 | 값 |
|------|-----|
| **Project ID** | `fyklcplybyfrfryopzvx` |
| **Region** | `ap-south-1` (Mumbai) |
| **Dashboard URL** | https://supabase.com/dashboard/project/fyklcplybyfrfryopzvx |

---

## 환경변수 설정

타 프로젝트에서 사용 시 `.env.local`에 추가:

```env
SUPABASE_URL=https://fyklcplybyfrfryopzvx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZ5a2xjcGx5YnlmcmZyeW9wenZ4Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2OTYwMjEzMiwiZXhwIjoyMDg1MTc4MTMyfQ.vNey9X8htUoS-Xb_my-QJpRSZE6y4Sb7VEjNAtdAgEY
```

---

## 테이블 구조

### `api_credentials` - API 키 저장소

```sql
CREATE TABLE api_credentials (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  service_name VARCHAR(50) NOT NULL,        -- kis
  credential_type VARCHAR(50) NOT NULL,     -- app_key, app_secret
  credential_value TEXT NOT NULL,
  environment VARCHAR(20) DEFAULT 'production',
  description TEXT,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(service_name, credential_type, environment)
);
```

### 현재 저장된 KIS 키

| service_name | credential_type | 설명 |
|--------------|-----------------|------|
| `kis` | `app_key` | 한국투자증권 앱 키 |
| `kis` | `app_secret` | 한국투자증권 앱 시크릿 |

---

## 사용 방법

### 방법 1: Supabase JS Client (권장)

```bash
npm install @supabase/supabase-js
```

```typescript
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  process.env.SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
);

// KIS API 키 조회
async function getKISCredentials() {
  const { data, error } = await supabase
    .from('api_credentials')
    .select('credential_type, credential_value')
    .eq('service_name', 'kis')
    .eq('is_active', true);

  if (error || !data) return null;

  const result: Record<string, string> = {};
  for (const row of data) {
    result[row.credential_type] = row.credential_value;
  }

  return {
    appKey: result.app_key,
    appSecret: result.app_secret,
  };
}

// 사용 예시
const kis = await getKISCredentials();
if (kis) {
  console.log('KIS App Key:', kis.appKey);
  console.log('KIS App Secret:', kis.appSecret);
}
```

### 방법 2: REST API 직접 호출

```typescript
async function getKISCredentials() {
  const response = await fetch(
    `${process.env.SUPABASE_URL}/rest/v1/api_credentials?service_name=eq.kis&is_active=eq.true&select=credential_type,credential_value`,
    {
      headers: {
        'apikey': process.env.SUPABASE_SERVICE_ROLE_KEY!,
        'Authorization': `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY}`,
      },
    }
  );

  const data = await response.json();

  return {
    appKey: data.find((d: any) => d.credential_type === 'app_key')?.credential_value,
    appSecret: data.find((d: any) => d.credential_type === 'app_secret')?.credential_value,
  };
}
```

---

## 보안 주의사항

1. **`SUPABASE_SERVICE_ROLE_KEY`는 서버 사이드에서만 사용**
   - 클라이언트에 절대 노출 금지
   - 환경변수로만 관리

2. **RLS 정책**
   - `api_credentials` 테이블은 Service Role만 접근 가능
   - Anon Key로는 조회 불가

---

## SQL 쿼리 예시

```sql
-- KIS 키 조회
SELECT credential_type, credential_value
FROM api_credentials
WHERE service_name = 'kis' AND is_active = true;

-- KIS 키 업데이트
UPDATE api_credentials
SET credential_value = 'NEW_VALUE', updated_at = NOW()
WHERE service_name = 'kis' AND credential_type = 'app_key';
```

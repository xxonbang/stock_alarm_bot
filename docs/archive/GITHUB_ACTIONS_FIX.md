# GitHub Actions Workflow 오류 수정

## 🔴 문제 원인

GitHub Actions에서 `workflow_dispatch` 실행 시 다음 오류 발생:
```
ValueError: 환경변수 GOOGLE_API_KEY_01가 설정되지 않았습니다.
```

**원인:**
- `config/settings.py`는 `GOOGLE_API_KEY_01`과 `GOOGLE_API_KEY_02`를 요구
- `.github/workflows/daily_report.yml`은 `GOOGLE_API_KEY`만 설정
- 환경변수 이름 불일치로 인한 오류

## ✅ 수정 사항

### 1. Workflow 파일 수정 (`.github/workflows/daily_report.yml`)

**변경 전:**
```yaml
env:
  GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
```

**변경 후:**
```yaml
env:
  GOOGLE_API_KEY_01: ${{ secrets.GOOGLE_API_KEY_01 }}
  GOOGLE_API_KEY_02: ${{ secrets.GOOGLE_API_KEY_02 }}
  KRX_API_KEY: ${{ secrets.KRX_API_KEY }}
  KRX_API_KEY_EXPIRY: ${{ secrets.KRX_API_KEY_EXPIRY }}
```

### 2. Settings 파일 수정 (`config/settings.py`)

**변경 전:**
```python
self.google_api_key_02 = get_env_var('GOOGLE_API_KEY_02')  # 필수
```

**변경 후:**
```python
self.google_api_key_02 = os.getenv('GOOGLE_API_KEY_02', None)  # 선택적
```

**이유:** `GOOGLE_API_KEY_02`는 fallback용이므로 필수가 아님

## 📋 GitHub Secrets 설정 가이드

다음 Secrets를 GitHub 저장소에 설정해야 합니다:

### 필수 Secrets
1. `TELEGRAM_TOKEN` - 텔레그램 봇 토큰
2. `CHAT_ID` - 텔레그램 채팅 ID
3. `GOOGLE_API_KEY_01` - Google Gemini API 키 (필수)
4. `FRED_API_KEY` - FRED API 키

### 선택적 Secrets
5. `GOOGLE_API_KEY_02` - Google Gemini API 키 (fallback용, 선택적)
6. `KRX_API_KEY` - KRX OpenAPI 인증키 (선택적, 없어도 네이버 크롤링으로 동작)
7. `KRX_API_KEY_EXPIRY` - KRX API 키 만료일 (선택적, 형식: YYYY-MM-DD)

## 🔧 설정 방법

1. GitHub 저장소로 이동
2. **Settings** → **Secrets and variables** → **Actions** 클릭
3. **New repository secret** 클릭
4. 위의 각 Secret을 추가

## ⚠️ 중요 사항

- `GOOGLE_API_KEY_01`은 **필수**입니다
- `GOOGLE_API_KEY_02`는 **선택적**입니다 (fallback용)
- 기존에 `GOOGLE_API_KEY`로 설정되어 있다면 `GOOGLE_API_KEY_01`로 변경 필요

## ✅ 검증

수정 후 workflow가 정상 작동하는지 확인:
1. GitHub Actions 탭에서 workflow 실행
2. `workflow_dispatch`로 수동 실행 테스트
3. 오류 없이 완료되는지 확인

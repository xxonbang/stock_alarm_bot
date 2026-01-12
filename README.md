# 📊 Stock Insight Bot (AI 기반 주식 인사이트 봇)

사용자가 지정한 주식 종목의 기간별 수익률 분석 및 Google Gemini AI를 활용한 심층 시장 분석 정보를 텔레그램으로 자동 발송하는 봇입니다.

## 🎯 주요 기능

- **기술적 분석**: yfinance를 사용한 실시간 주가 데이터 수집 및 기간별 수익률 계산
- **AI 심층 분석**: Google Gemini Pro를 활용한 전문가 수준의 시장 분석 (10회 반복 검증)
- **자동 알림**: 텔레그램을 통한 일일 리포트 자동 발송
- **Serverless 실행**: GitHub Actions를 통한 스케줄 기반 자동 실행

## 📋 사전 준비 (Prerequisites)

### 1. Telegram Bot Token 발급

1. 텔레그램에서 [@BotFather](https://t.me/BotFather) 검색
2. `/newbot` 명령어로 새 봇 생성
3. 봇 이름과 사용자명 설정
4. 발급받은 토큰을 저장 (예: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 2. Chat ID 확인

**중요: 먼저 봇에게 메시지를 보내야 합니다!**

1. 텔레그램 앱에서 생성한 봇을 검색 (예: `@your_bot_name`)
2. 봇과 대화 시작: `/start` 명령어나 아무 메시지나 전송
3. 브라우저에서 다음 URL 접속 (토큰 부분을 실제 토큰으로 변경):
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   ```
4. 응답 JSON에서 `"chat":{"id":123456789}` 부분의 숫자가 Chat ID입니다.

**문제 해결:**

- `{"ok":true,"result":[]}` 빈 결과가 나오면 → 봇에게 먼저 메시지를 보내지 않았습니다
- 봇에게 `/start` 또는 아무 메시지나 보낸 후 다시 `getUpdates`를 호출하세요
- 정상 응답 예시:
  ```json
  {
    "ok": true,
    "result": [
      {
        "update_id": 123456789,
        "message": {
          "message_id": 1,
          "from": {...},
          "chat": {
            "id": 123456789,  ← 이 숫자가 Chat ID입니다!
            "type": "private"
          },
          "text": "/start"
        }
      }
    ]
  }
  ```

### 3. Google AI API Key 발급

1. [Google AI Studio](https://makersuite.google.com/app/apikey) 접속
2. "Create API Key" 클릭
3. 발급받은 API Key를 저장

**또는 제공된 키 사용:**

- 제공된 키: `AIzaSyAhz6iY4UFOw3xyTSoGQUoc2fHSEBAWPoA`
- 이 키를 사용하거나 새로 발급받은 키를 사용할 수 있습니다.

### 4. GitHub Repository 생성

1. GitHub에 Private 리포지토리 생성
2. 이 코드를 리포지토리에 푸시

## ⚙️ 설정 방법 (Configuration)

### 1. 종목 설정

`config/config.yaml` 파일을 열어 감시할 주식 종목을 수정하세요:

```yaml
tickers:
  - "005930.KS" # 삼성전자 (코스피)
  - "360200.KS" # ACE 미국S&P500
  - "TSLA" # 테슬라
  - "NVDA" # 엔비디아
  - "AAPL" # 애플
  - "BTC-USD" # 비트코인
```

**한국 주식 티커 형식:**

- 코스피: `종목코드.KS` (예: `005930.KS` - 삼성전자)
- 코스닥: `종목코드.KQ` (예: `035720.KQ` - 카카오)

**한국 ETF 티커 형식:**

- 코스피 상장 ETF: `종목코드.KS` (예: `360200.KS` - KODEX 레버리지)
- 코스닥 상장 ETF: `종목코드.KQ`
- ETF도 주식과 동일하게 `.KS` 또는 `.KQ` 접미사를 사용합니다

**해외 주식:**

- 미국 주식은 그대로 사용 (예: `AAPL`, `TSLA`, `NVDA`)
- 미국 ETF도 그대로 사용 (예: `SPY`, `QQQ`, `VTI`)

### 2. GitHub Secrets 등록 (보안 필수)

GitHub 리포지토리에서 다음 경로로 이동:

```
Settings -> Secrets and variables -> Actions -> New repository secret
```

다음 3개의 Secret을 등록하세요:

| Secret 이름      | 설명              | 예시                                      |
| ---------------- | ----------------- | ----------------------------------------- |
| `TELEGRAM_TOKEN` | 텔레그램 봇 토큰  | `123456789:ABCdef...`                     |
| `CHAT_ID`        | 텔레그램 채팅 ID  | `123456789`                               |
| `GOOGLE_API_KEY` | Google AI API Key | `AIzaSyAhz6iY4UFOw3xyTSoGQUoc2fHSEBAWPoA` |

### 3. 실행 스케줄 수정 (선택사항)

`.github/workflows/daily_report.yml` 파일의 `cron` 부분을 수정하여 실행 시간을 변경할 수 있습니다.

현재 설정:

- 09:00 KST (UTC 00:00)
- 13:00 KST (UTC 04:00)
- 18:00 KST (UTC 09:00)
- 22:00 KST (UTC 13:00)

## 🚀 로컬 개발 환경 설정

### 1. 가상환경 생성 및 활성화

```bash
python3.11 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 2. 의존성 설치

```bash
pip install -r requirements.txt
```

### 3. 환경변수 설정

`.env` 파일을 생성하고 다음 내용을 입력:

```bash
TELEGRAM_TOKEN=your_telegram_bot_token_here
CHAT_ID=your_chat_id_here
GOOGLE_API_KEY=AIzaSyAhz6iY4UFOw3xyTSoGQUoc2fHSEBAWPoA
```

또는 환경변수로 직접 설정:

```bash
export TELEGRAM_TOKEN="your_token"
export CHAT_ID="your_chat_id"
export GOOGLE_API_KEY="your_api_key"
```

### 4. 로컬 실행

```bash
python src/main.py
```

## 📁 프로젝트 구조

```
stock-insight-bot/
├── .github/
│   └── workflows/
│       └── daily_report.yml  # GitHub Actions 스케줄러
├── config/
│   ├── config.yaml           # 사용자 설정 (종목, 시간)
│   └── settings.py           # 설정 로더
├── src/
│   ├── __init__.py
│   ├── main.py               # 프로그램 진입점
│   ├── analysis.py           # 기술적 분석 (수익률 계산)
│   ├── ai_researcher.py      # Google AI 연동 (심층 분석)
│   └── notifier.py           # 텔레그램 메시지 발송
├── requirements.txt          # 의존성 패키지
├── README.md                 # 사용 설명서
└── .env                      # 환경변수 (로컬 개발용)
```

## 🔍 주요 모듈 설명

### `src/analysis.py`

- yfinance를 사용한 주가 데이터 수집
- 기간별 수익률 계산 (1일, 1주, 1개월, 3개월, 6개월, 1년 등)
- 휴장일 등 데이터 부재 시 Backfill 처리

### `src/ai_researcher.py`

- **무료 티어 최적화**: Google Gemini Flash 모델 사용 (gemini-2.5-flash'우선)
- **단 1회 API 호출**: 10회 반복 로직 제거, 통합 프롬프트로 모든 분석 수행
- **429 에러 처리**: Quota exceeded 시 60초 대기 후 자동 재시도 (최대 3회)
- **자체 검증**: AI가 엄격한 비평가 역할로 정보를 검증한 뒤 출력

### `src/notifier.py`

- 텔레그램 메시지 포맷팅 및 발송
- HTML 파싱 모드 지원
- 4096자 초과 시 자동 분할 발송

## 📊 리포트 구성

### 1부: 나의 보유 종목 현황

```
📊 나의 보유 종목 현황

AAPL: $150.25
  📈 +2.5% (1D) / 📈 +10.2% (1W) / 📈 +15.3% (1M) / 📈 +25.8% (3M) / 📈 +45.2% (1Y)

TSLA: $250.50
  📉 -1.2% (1D) / 📈 +5.5% (1W) / 📈 +12.1% (1M) / 📈 +30.5% (3M) / 📈 +60.3% (1Y)
```

### 2부: AI 일일 리포트

- Market Sentiment: 현재 시장 분위기 및 주요 뉴스 3가지
- Promising Sectors: 국내/해외 유망 섹터 및 우량주 추천
- Risk Factors: 주의해야 할 리스크

## ⚠️ 주의사항

1. **무료 티어 최적화**:

   - 코드는 무료 티어 환경에 최적화되어 있습니다
   - Gemini Flash 모델을 우선 사용하여 쿼터를 절약합니다
   - 단 1회 API 호출로 모든 분석을 수행합니다

2. **429 Quota Exceeded 에러**:

   - 무료 티어 할당량 초과 시 60초 대기 후 자동 재시도합니다 (최대 3회)
   - 할당량이 부족한 경우 Google AI Studio에서 할당량을 확인하세요

3. **데이터 가용성**: yfinance는 실시간 데이터 제공에 제한이 있을 수 있으며, 휴장일에는 데이터가 없을 수 있습니다. 코드는 이를 처리하도록 설계되었습니다.

4. **보안**: API Key는 절대 코드에 하드코딩하지 마세요. GitHub Secrets 또는 `.env` 파일을 사용하세요.

5. **비용**: Google AI API 무료 티어는 제한이 있습니다. Flash 모델 사용으로 쿼터를 최대한 절약하도록 설계되었습니다.

## 🐛 문제 해결

### 텔레그램 메시지가 발송되지 않을 때

- 봇 토큰과 Chat ID가 올바른지 확인
- 봇에게 메시지를 먼저 보냈는지 확인

### 주가 데이터를 가져오지 못할 때

- 티커 심볼이 올바른지 확인 (한국 주식은 `.KS` 또는 `.KQ` 필요)
- 인터넷 연결 확인
- yfinance 서버 상태 확인

### AI 리포트 생성 실패 시

- Google API Key가 유효한지 확인
- API 할당량 확인
- 로그를 확인하여 구체적인 오류 메시지 확인

## 📝 라이선스

이 프로젝트는 개인 사용 목적으로 제작되었습니다.

## 🤝 기여

버그 리포트나 기능 제안은 이슈로 등록해주세요.

---

**만든이**: Stock Insight Bot  
**버전**: 1.0.0  
**최종 업데이트**: 2024

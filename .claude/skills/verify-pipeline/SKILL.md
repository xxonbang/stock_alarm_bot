---
name: verify-pipeline
description: 트렌드 스캐너 파이프라인의 모든 외부 의존성(Gemini, Telegram, YouTube, Naver 검색, Supabase, cron-job.org) 정상성 점검. 사용 — 작업 시작 전 환경 검증, 또는 의도치 않은 실패 후 진단.
---

trade_info_sender 파이프라인의 외부 의존성을 빠르게 점검합니다.

## 점검 항목 (병렬 실행 가능)

### 1. Gemini API (5개 키 모두)
```bash
./venv/bin/python -c "
import os, time
from dotenv import load_dotenv
load_dotenv('/Users/sonbyeongcheol/DEV/trade_info_sender/.env')
from google import genai
from google.genai import types
for n in range(1, 6):
    key = os.getenv(f'GOOGLE_API_KEY_{n:02d}')
    if not key:
        print(f'  키 #{n:02d}: (없음)')
        continue
    try:
        client = genai.Client(api_key=key)
        resp = client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents='ping',
            config=types.GenerateContentConfig(maxOutputTokens=5),
        )
        print(f'  키 #{n:02d}: ✅')
    except Exception as e:
        print(f'  키 #{n:02d}: ❌ {str(e)[:120]}')
    time.sleep(1)
"
```

### 2. Telegram
```bash
./venv/bin/python -c "
import os
from dotenv import load_dotenv
load_dotenv('/Users/sonbyeongcheol/DEV/trade_info_sender/.env')
from src.notifier import create_notifier
n = create_notifier(os.getenv('TELEGRAM_TOKEN'), os.getenv('CHAT_ID'))
ok = n.send_message('🔧 verify-pipeline 점검 메시지')
print(f'Telegram: {\"✅\" if ok else \"❌\"}')
"
```

### 3. YouTube Data API
```bash
./venv/bin/python -c "
import os
from dotenv import load_dotenv
load_dotenv('/Users/sonbyeongcheol/DEV/trade_info_sender/.env')
from googleapiclient.discovery import build
youtube = build('youtube', 'v3', developerKey=os.getenv('YOUTUBE_API_KEY'))
resp = youtube.search().list(q='주식', type='video', part='id', maxResults=1).execute()
print(f'YouTube API: {\"✅\" if resp.get(\"items\") else \"❌\"}')
"
```

### 4. Naver Search API (있으면)
- `NAVER_CLIENT_ID` 있을 때만 점검
- 없으면 스킵 (현재 사용 안 함)

### 5. Supabase (포트폴리오)
```bash
./venv/bin/python -c "
from config import settings
from src.portfolio_manager import PortfolioManager
pm = PortfolioManager()
items = pm.list_all() if pm.is_available else []
print(f'Supabase: {\"✅\" if pm.is_available else \"❌\"} ({len(items)}개 종목)')
"
```

### 6. cron-job.org
```bash
./venv/bin/python /Users/sonbyeongcheol/DEV/trade_info_sender/scripts/register_cron.py --list 2>&1 \
  | grep -E "트렌드 스캐너|작업 [0-9]+개"
```

### 7. GitHub Actions secrets
```bash
gh secret list --repo xxonbang/stock_alarm_bot 2>&1 \
  | grep -E "GOOGLE_API_KEY|TELEGRAM|CHAT_ID|YOUTUBE|CRONJOB|SUPABASE" \
  | awk '{print $1}'
```

## 보고 양식

```
🔧 파이프라인 점검 결과:

| 의존성 | 상태 |
|---|---|
| Gemini #01 | ✅/❌ |
| Gemini #02 | ✅/❌ |
| ... |
| Telegram  | ✅/❌ |
| YouTube API | ✅/❌ |
| Supabase | ✅/❌ N개 |
| cron-job.org | ✅/❌ N개 등록 |
| GH secrets | <리스트> |
```

## 주의

- 키 값을 그대로 출력하지 마세요 (마스킹된 결과만).
- ❌ 발생 시 어떤 환경변수를 어디에 추가/수정해야 할지 구체 안내.
- 사용자에게 점검 메시지가 텔레그램에 발송되는 점 미리 알리기 (verify Telegram 단계).
- API quota 사용 ≈ 5~10 requests/run. 자주 호출하지 말 것 (하루 몇 번이면 충분).

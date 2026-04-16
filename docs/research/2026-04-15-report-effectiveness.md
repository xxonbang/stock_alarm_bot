# 리포트 실효성 개선 리서치

**작성일**: 2026-04-15
**주제**: 텔레그램 리포트 메시지의 천편일률화 문제 진단 및 개선안
**범위**: `src/alert_engine.py`, `src/main.py`, `config/settings.py`, Supabase `portfolio` 연동

---

## 1. 현상 (Observation)

사용자 제공 스크린샷(2026-04-14 ~ 2026-04-15)에서 관찰된 반복 패턴:

| 시각 | 첫 줄 | 상단 본문(1~2줄 미리보기) |
|---|---|---|
| 04-14 13:28 | 📅 2026.04.14 (화) 13:28 KST | 오전 리포트 — 시장 약세 경계 / 특이사항 없는 하루입니다. 편안하게 지켜봐도 됩니다. |
| 04-14 15:23 | 📅 2026.04.14 (화) 15:23 KST | (동일) |
| 04-14 23:31 | 📅 … 23:31 KST | 장 마감 리포트 — 오늘 하루 수고하셨습니다. 내일도 좋은 장이 되길 바랍니다. |
| 04-15 08:35 | 📅 2026.04.15 (수) 08:35 KST | (동일: 특이사항 없는 하루) |
| 04-15 13:28 | (동일) | (동일) |
| 04-15 15:25 | (동일) | (동일) |

**결과**: 텔레그램 알림창에 보이는 peek-preview(첫 1~2줄)가 항상 동일. 사용자가 읽기 전에 "또 특이사항 없음"으로 인지 → 알림을 무시하게 되는 학습.

---

## 2. 구조적 원인 (Root Cause)

### 2.1 고정 카피 (자기부정적 마무리 문구)

`src/alert_engine.py:352`

```python
if not is_evening:
    lines.append("💡 특이사항 없는 하루입니다. 편안하게 지켜보셔도 됩니다.")
else:
    lines.append("💡 오늘 하루 수고하셨습니다. 내일도 좋은 장이 되길 바랍니다.")
```

- 평시(normal) 모드의 마지막 줄이 **무조건** 두 문구 중 하나.
- 본문에 기술지표/수급 데이터가 있어도 마무리가 "없는 하루"로 끝나 전체 메시지 가치를 스스로 부정.

### 2.2 보수적 임계값 → 평시 모드 지배

`src/alert_engine.py:30-45` THRESHOLDS

| 지표 | 임계값 | 실제 시장 빈도 |
|---|---|---|
| `vix_red` | 25 | 연중 5~15일 수준 |
| `vix_daily_change_pct` | 20% | 연 1~3회 |
| `usdkrw_daily_change` | 15원 | 월 2~4회 |
| `us10y_red` | 4.5% | 특정 매크로 시즌만 |
| `rsi_overbought_red` | 80 | 극단 과열(드묾) |
| `fear_greed_extreme_fear` | 20 | 약세장 국면만 |
| `stock_daily_change_pct` | 3.0% | 월 5~10회 |

- 대부분의 거래일에 alert 조건 미달 → `mode == 'normal'`
- `determine_mode()`가 이원(normal/alert)이라 "어중간한 주의"가 표현될 슬롯이 없음.

### 2.3 **[신규 발견] 분석 대상 종목 공백 — 실질적으로 본문이 비어 있음**

**이것이 가장 심각한 원인**:

현재 `Supabase portfolio` 테이블 상태 (2026-04-15 시점):
```
[possession] SK hynix (000660.KS)    buy_price=1026000 qty=4
[possession] 삼성전자 (005930.KS)    buy_price=206500  qty=20
[possession] 셀트리온 (068270.KS)    buy_price=202500  qty=9
```

`config/settings.py:49-53` → Supabase primary 로드 결과:
```
tickers_possession_domestic = ['000660.KS', '005930.KS', '068270.KS']
tickers_interest_domestic   = []  ← 비어 있음
```

그런데 `src/main.py:125-131`:
```python
def _extract_stock_analysis_results() -> list:
    """관심 종목(SK하이닉스)의 분석 결과를 추출"""
    tickers = settings.tickers_interest_domestic  # ← 빈 리스트
    if not tickers:
        return []  # ← 항상 여기로 빠짐
    results = analyze_all_tickers(tickers)
    return results
```

그리고 `src/main.py:228`:
```python
all_tickers = settings.tickers_interest_domestic.copy()  # ← 빈 리스트
```

**현재 효과**:
- `stock_results`가 항상 빈 리스트
- `determine_mode()`에서 RSI/변동률 체크 루프가 빈 리스트 순회 → 종목 경보가 원천적으로 발동 불가
- `generate_normal_message()`가 종목 상세 섹션을 전혀 생성하지 않음 (`alert_engine.py:220-347`의 for 루프가 빈 순회)
- 결과적으로 매크로 한 줄 + "특이사항 없음" 한 줄만 남음 → 매일 동일

**과거 맥락**: task_history에 따르면 2026-03-14 v3 재설계 시 "보유 종목 전체 제거, 관심종목 SK하이닉스 1개로 집중" 했는데, 이후 2026-04-06 텔레그램 봇 CRUD가 추가되면서 SK하이닉스가 possession으로 이동 등록됨. 코드는 여전히 `interest_domestic`만 바라보고 있어 단절.

### 2.4 종목 필터 하드코딩

`src/alert_engine.py:220-222`

```python
for result in stock_results:
    ticker = result.get('ticker', '')
    if '000660' not in ticker:
        continue
```

- 설사 2.3이 고쳐져도 SK하이닉스 외 종목은 표시 안 됨.
- 삼성전자/셀트리온 같은 신규 보유 종목이 상세 섹션에 나오지 않음.

### 2.5 첫 줄(헤드라인) 고정 패턴

`src/alert_engine.py:191-197`

```python
lines.append(f"📅 {date_str} ({weekday}) {time_str} KST")
lines.append("")
if is_evening:
    lines.append(f"{regime_emoji} <b>장 마감 리포트</b>")
else:
    lines.append(f"{regime_emoji} <b>오전 리포트</b> — 시장 {regime_name}")
```

- 첫 줄은 항상 날짜, 둘째 줄은 "오전/마감 리포트 — 시장 [체제명]".
- 체제명(`regime_name`)은 4종(적극 공격/선별 매수/약세 경계/방어 모드) — 며칠 연속 같은 값이기 쉬움.
- 텔레그램 알림 미리보기가 이 두 줄이라, 실질적으로 매번 동일하게 보임.

---

## 3. 행동재무학 관점

원래 v3 재설계 취지(2026-03-14 task_history)는 "행동재무학 기반 — 정보 과부하 방지, 비행동 우선". 이 의도 자체는 타당했으나 실행 단계에서:

- **과부하 방지 → 정보량 제로화로 과도 교정**: "특이사항 없음"은 정보를 "없는 것"으로 프레이밍 → 메시지의 **정보성 가치를 발신자가 스스로 부정**.
- **비행동 우선 → 수동적 관찰자 포지션 고착**: 관찰자에게는 `관찰할 거리`가 필요하다. "특이사항 없음"은 관찰할 대상을 제거해버림.
- **알림 피로 누적**: 반복된 "별일 없음" 메시지는 Pavlov 조건화로 "이 채널 = 볼 필요 없음"을 강화. 정작 진짜 alert가 올 때도 무시될 위험.

바람직한 톤: **"별일 없지만, 오늘의 변수는 이것"** — 행동 유도 없이 기억할 변수 하나를 심음.

---

## 4. 개선안 (4축 병렬 적용)

### 4.1 축 1: 분석 대상 누락 버그 해소 (최우선)

**변경 지점**:

`src/main.py:125-131`
```python
def _extract_stock_analysis_results() -> list:
    from src.analysis import analyze_all_tickers
    tickers = (
        settings.tickers_possession_domestic +
        settings.tickers_interest_domestic
    )
    tickers = list(dict.fromkeys(tickers))  # 중복 제거, 순서 유지
    if not tickers:
        return []
    return analyze_all_tickers(tickers)
```

`src/main.py:228`
```python
all_tickers = (
    settings.tickers_possession_domestic +
    settings.tickers_interest_domestic
)
```

`src/alert_engine.py:220-222` — `'000660' not in ticker` 하드코딩 제거.
- 대신 `stock_results`를 그대로 순회. 단, 섹션이 너무 길어지면 보유/관심 상위 N개로 제한하는 옵션.

### 4.2 축 2: 모드 세분화 (normal → normal / yellow / alert)

**목적**: 평시 지배도를 깨고 "약한 변화" 슬롯 추가.

**Yellow 모드 진입 조건** (임계값 완화판 — alert보다는 낮지만 normal보다는 흥미로움):

| 지표 | Yellow 범위 | Alert 범위 (기존 유지) |
|---|---|---|
| VIX | 18 ≤ VIX < 25 | ≥ 25 |
| USD/KRW 변동 | 7 ≤ Δ < 15원 | ≥ 15원 |
| 미 10Y 금리 | 4.2 ≤ y < 4.5 | ≥ 4.5 |
| Fear & Greed | 20 < FG ≤ 30 또는 70 ≤ FG < 80 | ≤ 20 또는 ≥ 80 |
| 종목 RSI | 65~80 또는 25~35 | ≥ 80 또는 ≤ 25 |
| 종목 일간 변동 | 1.5 ≤ Δ < 3.0% | ≥ 3.0% |
| **(신규) 수급 연속성** | 외인 or 기관 3일 연속 동일 방향 | — |
| **(신규) 거래량** | 20일 평균 대비 1.5~2.0배 | ≥ 2.0배 |
| **(신규) 골든/데드크로스** | 5일선이 20일선 2% 이내 접근 | 교차 발생 |

**Yellow 메시지 특성**:
- AI 호출 **없음** (비용 보존)
- 첫 줄이 "오늘의 주목 포인트: [구체 사건]"으로 대체
- 본문은 normal과 유사하되 해당 시그널을 강조 마크업(⭐)

**구현**: `determine_mode()`의 리턴에 `'yellow'` 추가. `generate_yellow_message()` 신규 (normal과 대부분 공유, 헤드라인/강조만 차등).

### 4.3 축 3: 동적 헤드라인 (첫 줄 변화)

**알고리즘** — 시그널 우선순위 스코어링:

```
candidates = []
# 1) 매크로 급변
if |usdkrw_Δ| ≥ 7: candidates.append( (score: |Δ|*2, "환율 {usdkrw}원 ({Δ:+.0f}원)") )
if |us10y_Δ| ≥ 0.05: candidates.append( (score: |Δ|*40, "미 10Y {y:.2f}% ({Δ:+.2f})") )
if vix ≥ 18: candidates.append( (score: vix-15, "VIX {v:.1f}") )
if |fear_greed - 50| ≥ 15: candidates.append( ... )

# 2) 포트폴리오 시그널
for stock in stock_results:
  if rsi ≥ 65 or rsi ≤ 35: candidates.append( (score, "{name} RSI {r}") )
  if |daily_change| ≥ 1.5: candidates.append( (score, "{name} {±p}%") )
  if 수급 연속성: candidates.append( (score, "{name} 외인 N일 연속 순{매수/매도}") )
  if 골든/데드크로스 근접: candidates.append( ... )
  if 거래량 스파이크: candidates.append( ... )

# 3) 후보 없으면 (완전한 무풍일)
  fallback: "{종목명} 현재가 {price}원 (체제: {regime_name})"
```

`candidates`에서 최고 스코어 1개를 뽑아 첫 줄에 배치. 동률이면 다양성(최근 24시간 내 같은 문구가 안 나오도록) 가중.

**구조 변화**:

현재 헤드라인:
```
📅 2026.04.15 (수) 08:35 KST

🔵 오전 리포트 — 시장 선별 매수
```

개선 후:
```
🔵 SK하이닉스 외인 3일 연속 순매수 (+12만주 → +18만주 → +9만주)

📅 2026.04.15 (수) 08:35 — 시장 선별 매수
```

→ 텔레그램 peek에 변화하는 정보가 먼저 보임.

### 4.4 축 4: 톤 전환 (데이터 요약형 + 관찰·행동형 혼용)

마무리 문구 `alert_engine.py:352` 개편:

**현재** (항상 고정):
```
💡 특이사항 없는 하루입니다. 편안하게 지켜보셔도 됩니다.
```

**개선안** — 두 줄로 분리:

1) **데이터 요약 한 줄** (생성 자동):
   ```
   📌 오늘의 한 줄: SK하닉 RSI 58(중립)·수급 약보합, 삼전 거래량 평소 수준.
   ```
   - 종목별로 `(이름 지표 상태)`를 콤마로 연결.
   - 지표는 RSI/수급/거래량 중 "중립이 아닌" 혹은 "가장 최신인" 것 우선.

2) **관찰·행동 한 줄** (템플릿 + 조건):
   ```
   🔎 관찰: 단기 과열 낮음. 기준 철회 매도세 없으면 보유 유지.
   ```
   - 템플릿 풀에서 **체제(regime) × 평균 RSI 레벨**로 조회:
     - regime="선별 매수" & RSI 중립: "관찰: 단기 과열 낮음. 기준 철회 매도세 없으면 보유 유지."
     - regime="선별 매수" & RSI 과열: "관찰: 단기 과열 신호. 급등 시 분할 익절 검토."
     - regime="약세 경계" & RSI 중립: "관찰: 방어 우선. 추가 진입은 공포 지수 반등 후."
     - (이하 4×3 = 12개 템플릿)

- 결코 "특이사항 없음"으로 끝나지 않음.
- 템플릿 풀에 12개 존재 → 같은 문구가 연속되지 않음.

---

## 5. 영향 범위 / 구현 우선순위

| 순위 | 작업 | 파일 | 영향 |
|---|---|---|---|
| **P0** | 축 1 (분석 대상 버그) | main.py, alert_engine.py | 본문이 비어있는 근본 원인 해소. 단독으로도 체감 개선 큼 |
| **P1** | 축 4 (톤 전환 템플릿) | alert_engine.py | 10~20줄 변경, 효과 즉시 |
| **P1** | 축 3 (동적 헤드라인) | alert_engine.py 신규 함수 + normal/yellow 적용 | peek 차별화 핵심 |
| **P2** | 축 2 (yellow 모드) | alert_engine.py 구조 변경 | 가장 규모 큼. 3단계 임계값·메시지 분기 추가 |

**분리 구현 권장**: P0(축1) 먼저 단독 커밋 → 효과 관찰 (1~2일) → P1 두 축 동시 적용 → 이후 P2.

---

## 6. 측정 지표 (효과 검증)

텔레그램은 열람 로그가 없어 직접 측정 불가. 대리 지표:

1. **메시지 첫 줄 엔트로피**: 최근 30건 메시지의 첫 줄을 수집, 중복률 측정. 현재는 ~83% 중복(7/30 유니크) → 목표 <40% (18+/30 유니크).
2. **normal:yellow:alert:weekly 비율**: 현재 ~80:0:15:5, 목표 ~50:25:20:5.
3. **본문 길이(줄 수) 평균**: 현재 매크로 1줄 + 고정 1줄 = 3줄 → 목표 10줄 이상 (종목 3개 상세 포함).
4. **정성 평가**: 사용자에게 주 1회 "이번 주 리포트 중 가장 유용했던 메시지" 회고 요청 (별도 저장소).

---

## 7. 리스크 / 주의

- **Yellow 모드 남발 위험**: 임계값을 너무 낮추면 다시 피로 발생. 초기 2주간 빈도 로그로 튜닝 필요.
- **헤드라인 오도**: 단일 시그널을 첫 줄에 박으면 전체 상황과 불일치해 보일 수 있음. 우선순위 스코어에 체제(regime) 가중 반영.
- **템플릿 고갈**: 관찰·행동 템플릿 12개도 몇 달이면 반복. 분기별로 풀 확장 루틴 필요.
- **하드코딩 종목(`'000660'`) 제거 시 UI 길이**: 종목이 3~5개로 늘면 메시지 길어짐. 종목별 상세를 토글 방식 대신 1종목 3~4줄로 압축 규칙 필요 (밸류에이션/리스크는 weekly에서만 노출 등).

---

## 8. 다음 단계

1. 본 리서치 사용자 검토 및 우선순위 확정
2. 승인 후 `docs/superpowers/specs/`에 spec 문서화 (구현 단위별)
3. 각 spec에 대해 writing-plans 스킬로 구현 계획 수립
4. P0 → P1 → P2 순 구현 및 관찰

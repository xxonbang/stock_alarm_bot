# 포트폴리오 Update UX 리서치

**작성일**: 2026-04-15
**주제**: 보유·관심 종목의 매수정보 수정(Update) 기능 부재 진단 및 추가 설계
**범위**: `src/portfolio_manager.py`, `src/telegram_bot.py`, Supabase `portfolio` 테이블

---

## 1. 현상 (Observation)

현재 텔레그램 봇 `/pf` 명령어는 **Create + Read + Delete만** 제공. Update 불가.

**실사용 시나리오에서 발생하는 불편**:

| 시나리오 | 현재 해결 방법 | 문제 |
|---|---|---|
| 매수가 오타 (206,500 → 216,500) | 삭제 후 재등록 | 7단계 플로우를 다시 밟아야 함, 종목 검색부터 재수행 |
| 추가 매수 후 평단가 조정 | 삭제 후 재등록 (신규 평단으로) | 원 매수일자 이력 손실 |
| 수량 변경 (배당/분할 매수) | 동일 | 동일 |
| 매수일자 나중에 채우기 | 삭제 후 재등록 | — |
| 오타 난 이름 수정 | 삭제 후 재등록 | — |

**영향**: 포트폴리오 관리 빈도가 높아질수록(추가 매수·분할 매도) 불편이 선형 증가. 오늘(2026-04-15) 셀트리온 추가 매수 기록 시에도 매수일자/수량 변경이 필요하면 전체 삭제·재입력해야 함.

---

## 2. 구조적 원인 (Root Cause)

### 2.1 `PortfolioManager` API 공백

`src/portfolio_manager.py:42-99`에 존재하는 메서드:

| 메서드 | 목적 |
|---|---|
| `add(ticker, name, category, buy_price, buy_quantity, buy_date)` | Create |
| `delete(portfolio_id)` | Delete |
| `list_by_category(category)` | Read (카테고리별) |
| `list_all()` | Read (전체) |
| `get_tickers_by_category()` | Read (settings 연동용) |

**`update()` 메서드 부재**. Supabase `.update().eq('id', ...)` 호출 래퍼가 없음.

### 2.2 `telegram_bot.py` ConversationHandler 상태 공백

`src/telegram_bot.py:45-55` 상태 정의:

```python
(
    MAIN_MENU,
    ADD_CATEGORY,
    ADD_SEARCH_NAME,
    ADD_SELECT_STOCK,
    ADD_BUY_PRICE,
    ADD_BUY_QUANTITY,
    ADD_BUY_DATE,
    DELETE_SELECT,
    DELETE_CONFIRM,
) = range(9)
```

- Add 5개 상태, Delete 2개 상태, 진입 1개 = 9개.
- **Update 관련 상태가 전혀 없음.**

`_main_menu_keyboard()` (`telegram_bot.py:73-83`)도 버튼 4개(조회2/추가/삭제)로 수정 진입구 없음.

---

## 3. 대안 비교 (Alternatives)

사용자 질의 결과 **기존 대화형 UX 유지 + 수정 흐름 추가**를 선택. 다른 대안도 참고 목적으로 기록.

| 대안 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| **A. 기존 대화형 + 수정 흐름 추가** (채택) | 기존 UX 일관성, 버튼 클릭만으로 완결, 신규 학습 없음 | 상태 4~5개 추가로 코드 약간 증가 | ✅ |
| B. 한 줄 명령 (`/update AAPL price=230`) | 타이핑 1번으로 빠름 | 문법 학습 필요, 실수 시 덮어쓰기 위험, 종목명/티커 표기 모호 | ❌ |
| C. 종목 상세 인라인 편집 (각 필드 버튼 탭) | UX 가장 최신형, 현재가·손익 동시 노출 가능 | 구현 복잡(카드+필드별 콜백), 현재가 조회 추가 필요 | ❌ (차후 과제로 기록) |

---

## 4. 설계안 — 대화형 Update 플로우

### 4.1 진입 흐름 (State Machine)

```
/pf → MAIN_MENU
         ├─ "조회" (기존)
         ├─ "추가" (기존)
         ├─ "수정" (신규)
         │    ↓
         │    UPDATE_SELECT_STOCK   ← 보유 종목 목록 (관심종목은 매수정보 없어 대상 제외)
         │        종목 선택
         │        ↓
         │    UPDATE_SELECT_FIELD   ← 필드 버튼 [매수가 / 수량 / 매수일자 / 취소]
         │        필드 선택
         │        ↓
         │    UPDATE_INPUT_VALUE    ← 새 값 텍스트 입력
         │        입력 검증 통과
         │        ↓
         │    UPDATE_CONFIRM        ← "기존: X → 신규: Y. 확인하시겠습니까?" (확인/취소)
         │        확인
         │        ↓
         │    pm.update() 호출 → 성공/실패 메시지 → MAIN_MENU
         └─ "삭제" (기존)
```

### 4.2 신규 상태 정의

`src/telegram_bot.py:45-55` 확장:

```python
(
    MAIN_MENU,
    ADD_CATEGORY,
    ADD_SEARCH_NAME,
    ADD_SELECT_STOCK,
    ADD_BUY_PRICE,
    ADD_BUY_QUANTITY,
    ADD_BUY_DATE,
    DELETE_SELECT,
    DELETE_CONFIRM,
    UPDATE_SELECT_STOCK,   # 신규
    UPDATE_SELECT_FIELD,   # 신규
    UPDATE_INPUT_VALUE,    # 신규
    UPDATE_CONFIRM,        # 신규
) = range(13)
```

### 4.3 메인 메뉴 키보드 확장

`_main_menu_keyboard()` 2행 → 3행:

```python
return InlineKeyboardMarkup([
    [
        InlineKeyboardButton("보유종목 조회", callback_data="list_possession"),
        InlineKeyboardButton("관심종목 조회", callback_data="list_interest"),
    ],
    [
        InlineKeyboardButton("종목 추가", callback_data="add"),
        InlineKeyboardButton("종목 수정", callback_data="update"),   # 신규
    ],
    [
        InlineKeyboardButton("종목 삭제", callback_data="delete"),
    ],
])
```

### 4.4 핸들러 스케치

```python
# main_menu_handler에 분기 추가
elif data == "update":
    items = pm.list_by_category("possession")  # 관심종목 제외
    if not items:
        # 빈 목록 처리
        return MAIN_MENU
    buttons = [
        [InlineKeyboardButton(
            f"{it['name']} ({it['ticker']})",
            callback_data=f"upd_{it['id']}"
        )] for it in items
    ]
    buttons.append([InlineKeyboardButton("< 메인메뉴", callback_data="cancel")])
    await query.edit_message_text(
        "수정할 종목을 선택하세요", reply_markup=InlineKeyboardMarkup(buttons)
    )
    return UPDATE_SELECT_STOCK


async def update_select_stock_handler(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        # MAIN_MENU 복귀
        return MAIN_MENU

    portfolio_id = query.data.replace("upd_", "")
    context.user_data['update_id'] = portfolio_id

    # 현재 값을 보여주며 필드 선택
    target = next((i for i in pm.list_all() if i['id'] == portfolio_id), None)
    if not target:
        # 오류 처리
        return MAIN_MENU

    context.user_data['update_target'] = target
    text = (
        f"<b>{target['name']}</b> ({target['ticker']})\n"
        f"매수가: {_format_number(target.get('buy_price'))}\n"
        f"수량: {_format_number(target.get('buy_quantity'))}\n"
        f"매수일자: {target.get('buy_date') or '-'}\n\n"
        f"수정할 필드를 선택하세요"
    )
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("매수가", callback_data="field_buy_price"),
            InlineKeyboardButton("수량", callback_data="field_buy_quantity"),
        ],
        [
            InlineKeyboardButton("매수일자", callback_data="field_buy_date"),
            InlineKeyboardButton("< 취소", callback_data="cancel"),
        ],
    ])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=buttons)
    return UPDATE_SELECT_FIELD


async def update_select_field_handler(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        # MAIN_MENU 복귀
        return MAIN_MENU

    field = query.data.replace("field_", "")
    context.user_data['update_field'] = field

    prompts = {
        'buy_price': "새 매수가를 입력하세요 (숫자만)",
        'buy_quantity': "새 수량을 입력하세요 (정수만)",
        'buy_date': "새 매수일자를 입력하세요 (YYYY-MM-DD, 지우려면 n)",
    }
    await query.edit_message_text(prompts[field])
    return UPDATE_INPUT_VALUE


async def update_input_value_handler(update, context):
    text = update.message.text.strip()
    field = context.user_data['update_field']

    # 필드별 파서 재사용 (add 플로우와 동일 검증)
    try:
        if field == 'buy_price':
            new_value = float(text.replace(',', ''))
        elif field == 'buy_quantity':
            new_value = int(text.replace(',', ''))
        elif field == 'buy_date':
            if text.lower() == 'n':
                new_value = None
            else:
                new_value = datetime.strptime(text, '%Y-%m-%d').date()
        else:
            raise ValueError(f"알 수 없는 필드: {field}")
    except ValueError:
        # 에러 메시지 후 동일 상태 유지 → 재입력 요청
        return UPDATE_INPUT_VALUE

    context.user_data['update_new_value'] = new_value

    # 확인 단계
    target = context.user_data['update_target']
    old_value = target.get(field)
    label_map = {'buy_price': '매수가', 'buy_quantity': '수량', 'buy_date': '매수일자'}
    text = (
        f"<b>{target['name']}</b> ({target['ticker']})\n"
        f"{label_map[field]}: {old_value} → <b>{new_value}</b>\n\n"
        f"수정할까요?"
    )
    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("확인", callback_data="confirm"),
        InlineKeyboardButton("취소", callback_data="cancel"),
    ]])
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=buttons)
    return UPDATE_CONFIRM


async def update_confirm_handler(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        # MAIN_MENU 복귀
        return MAIN_MENU

    portfolio_id = context.user_data['update_id']
    field = context.user_data['update_field']
    new_value = context.user_data['update_new_value']

    success = pm.update(portfolio_id, field, new_value)
    text = "수정 완료!" if success else "수정 실패."
    # MAIN_MENU 복귀
    return MAIN_MENU
```

### 4.5 ConversationHandler 등록

`telegram_bot.py:510-542` `conv_handler` states dict에 추가:

```python
UPDATE_SELECT_STOCK: [CallbackQueryHandler(update_select_stock_handler)],
UPDATE_SELECT_FIELD: [CallbackQueryHandler(update_select_field_handler)],
UPDATE_INPUT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_input_value_handler)],
UPDATE_CONFIRM: [CallbackQueryHandler(update_confirm_handler)],
```

---

## 5. `PortfolioManager.update()` API 확장 스펙

### 5.1 시그니처

```python
def update(self, portfolio_id: str, field: str, value) -> bool:
    """
    포트폴리오 단일 필드 업데이트

    Args:
        portfolio_id: Supabase id (uuid)
        field: 'buy_price' | 'buy_quantity' | 'buy_date' | 'name'
        value: 새 값
            - buy_price: float
            - buy_quantity: int
            - buy_date: datetime.date or None (None이면 NULL 저장)
            - name: str

    Returns:
        True on success
    """
```

### 5.2 구현 초안

```python
ALLOWED_UPDATE_FIELDS = {'buy_price', 'buy_quantity', 'buy_date', 'name'}

def update(self, portfolio_id: str, field: str, value) -> bool:
    if not self._available:
        return False
    if field not in ALLOWED_UPDATE_FIELDS:
        logger.error(f"허용되지 않은 필드: {field}")
        return False
    try:
        payload = {}
        if field == 'buy_date':
            payload[field] = value.isoformat() if value is not None else None
        else:
            payload[field] = value
        self._client.table('portfolio') \
            .update(payload) \
            .eq('id', portfolio_id) \
            .execute()
        return True
    except Exception as e:
        logger.error(f"업데이트 실패: {e}")
        return False
```

### 5.3 허용 필드 제한 이유

- `ticker`, `category`, `market`: 변경 시 의미가 완전히 달라짐 → 삭제·재등록이 의도에 더 맞음.
- `id`, `created_at`: 시스템 필드.
- 향후 `category` 이동(관심→보유)이 필요하면 별도 메서드 `promote_to_possession()` 형태로 분리.

---

## 6. 구현 체크리스트

- [ ] `PortfolioManager.update()` 메서드 추가 + `ALLOWED_UPDATE_FIELDS` 상수
- [ ] 단위 테스트: 허용 필드 각각 / 비허용 필드 거부 / Supabase 미연결 시 False
- [ ] `telegram_bot.py`에 상태 4개 추가 (`UPDATE_SELECT_STOCK` 등)
- [ ] `_main_menu_keyboard()` 에 "수정" 버튼 추가 + main_menu_handler 분기
- [ ] 핸들러 함수 4개 추가 (`@_authorized` 데코레이터 포함)
- [ ] 입력 파서: 기존 `add_buy_price_handler` 등과 공통 로직 추출 후 재사용
- [ ] ConversationHandler states dict에 신규 상태 등록
- [ ] 실사용 검증: 삼성전자 매수가 수정 → 셀트리온 매수일 수정 → 에러 입력 시 재입력 유도 확인
- [ ] task_history 기록

---

## 7. 범위 밖 (Out of Scope) — 별도 연구 대상

- **추가매수 시 평단가 자동 계산**: 사용자 응답에서 "매수정보 직접 수정"만 선택. 평단 재계산은 별도 기능으로 분리.
- **카테고리 이동(관심 ↔ 보유)**: 현재는 삭제·재등록. 추후 `promote_to_possession(id, buy_price, buy_quantity, buy_date)` 메서드로.
- **인라인 카드형 UX (대안 C)**: 현재가·손익 함께 보는 종목 상세 카드. 현재가 실시간 조회 의존 → 봇 부하 증가 검토 필요.
- **종목명 변경**: `name` 필드는 API에 포함했으나 UI 플로우엔 미포함(빈도 낮음). 필요 시 필드 버튼에 "이름" 추가.

---

## 8. 다음 단계

1. 본 리서치 사용자 검토
2. 승인 후 `docs/superpowers/specs/`에 spec 문서화
3. writing-plans 스킬로 구현 계획 수립
4. 단위 구현 → 실사용 검증 → 커밋

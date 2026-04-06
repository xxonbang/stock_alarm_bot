"""
포트폴리오 관리 텔레그램 봇
/pf 명령어로 보유/관심 종목 CRUD (인라인 버튼 방식)
"""
import logging
import os
import sys
from pathlib import Path
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.portfolio_manager import PortfolioManager
from src.stock_search import search_stock

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# .env 로드 (모듈 import 시점에 바로 적용)
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent.parent / '.env'
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass

# Conversation states
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

# 포트폴리오 매니저 (전역)
pm = PortfolioManager()


def _authorized(func):
    """CHAT_ID 기반 접근 제어 데코레이터"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        allowed_chat_id = os.getenv('CHAT_ID', '')
        actual_chat_id = str(update.effective_chat.id)
        if actual_chat_id != allowed_chat_id:
            logger.warning(f"비인가 접근: {actual_chat_id}")
            return ConversationHandler.END
        return await func(update, context)
    return wrapper


def _main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("보유종목 조회", callback_data="list_possession"),
            InlineKeyboardButton("관심종목 조회", callback_data="list_interest"),
        ],
        [
            InlineKeyboardButton("종목 추가", callback_data="add"),
            InlineKeyboardButton("종목 삭제", callback_data="delete"),
        ],
    ])


def _format_number(value) -> str:
    """숫자 포맷 (천 단위 콤마)"""
    if value is None:
        return "-"
    try:
        num = float(value)
        if num == int(num):
            return f"{int(num):,}"
        return f"{num:,.2f}"
    except (ValueError, TypeError):
        return str(value)


def _format_portfolio_list(items: list, category_label: str) -> str:
    """포트폴리오 목록 텍스트 포맷"""
    if not items:
        return f"등록된 {category_label}이 없습니다."

    lines = [f"<b>{category_label} ({len(items)}개)</b>\n"]
    for i, item in enumerate(items, 1):
        name = item.get('name', '?')
        ticker = item.get('ticker', '?')
        line = f"{i}. <b>{name}</b> ({ticker})"

        details = []
        if item.get('buy_price') is not None:
            details.append(f"매수가: {_format_number(item['buy_price'])}")
        if item.get('buy_quantity') is not None:
            details.append(f"{_format_number(item['buy_quantity'])}주")
        if item.get('buy_date'):
            details.append(str(item['buy_date']))

        if details:
            line += f"\n   {' | '.join(details)}"

        lines.append(line)

    return "\n".join(lines)


# === 핸들러 ===

@_authorized
async def pf_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """진입점: /pf"""
    context.user_data.clear()
    await update.message.reply_text(
        "<b>포트폴리오 관리</b>",
        parse_mode="HTML",
        reply_markup=_main_menu_keyboard(),
    )
    return MAIN_MENU


@_authorized
async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """메인 메뉴 버튼 처리"""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "list_possession":
        items = pm.list_by_category("possession")
        text = _format_portfolio_list(items, "보유종목")
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("< 메인메뉴", callback_data="back_main"),
            ]]),
        )
        return MAIN_MENU

    elif data == "list_interest":
        items = pm.list_by_category("interest")
        text = _format_portfolio_list(items, "관심종목")
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("< 메인메뉴", callback_data="back_main"),
            ]]),
        )
        return MAIN_MENU

    elif data == "back_main":
        await query.edit_message_text(
            "<b>포트폴리오 관리</b>",
            parse_mode="HTML",
            reply_markup=_main_menu_keyboard(),
        )
        return MAIN_MENU

    elif data == "add":
        await query.edit_message_text(
            "카테고리를 선택하세요",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("보유종목", callback_data="cat_possession"),
                    InlineKeyboardButton("관심종목", callback_data="cat_interest"),
                ],
                [InlineKeyboardButton("< 메인메뉴", callback_data="cancel")],
            ]),
        )
        return ADD_CATEGORY

    elif data == "delete":
        items = pm.list_all()
        if not items:
            await query.edit_message_text(
                "등록된 종목이 없습니다.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("< 메인메뉴", callback_data="back_main"),
                ]]),
            )
            return MAIN_MENU

        buttons = []
        for item in items:
            label = f"{item['name']} ({'보유' if item['category'] == 'possession' else '관심'})"
            buttons.append([InlineKeyboardButton(label, callback_data=f"del_{item['id']}")])
        buttons.append([InlineKeyboardButton("< 메인메뉴", callback_data="cancel")])

        await query.edit_message_text(
            "삭제할 종목을 선택하세요",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return DELETE_SELECT

    return MAIN_MENU


# === 종목 추가 플로우 ===

@_authorized
async def add_category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """카테고리 선택"""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text(
            "<b>포트폴리오 관리</b>",
            parse_mode="HTML",
            reply_markup=_main_menu_keyboard(),
        )
        return MAIN_MENU

    category = query.data.replace("cat_", "")
    context.user_data['add_category'] = category
    label = "보유종목" if category == "possession" else "관심종목"

    await query.edit_message_text(
        f"[{label}] 종목명을 입력하세요\n(예: SK하이닉스, Apple, AAPL)",
    )
    return ADD_SEARCH_NAME


@_authorized
async def add_search_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """종목명 입력 → 검색"""
    name = update.message.text.strip()

    await update.message.reply_text(f"'{name}' 검색 중...")

    results = search_stock(name)

    if not results:
        await update.message.reply_text(
            f"'{name}'에 대한 검색 결과가 없습니다.\n다시 입력하세요.",
        )
        return ADD_SEARCH_NAME

    context.user_data['search_results'] = results

    buttons = []
    for stock_name, ticker in results:
        buttons.append([InlineKeyboardButton(
            f"{stock_name} ({ticker})",
            callback_data=f"pick_{ticker}",
        )])
    buttons.append([InlineKeyboardButton("< 다시 검색", callback_data="retry_search")])

    await update.message.reply_text(
        "종목을 선택하세요",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return ADD_SELECT_STOCK


@_authorized
async def add_select_stock_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """검색 결과에서 종목 선택"""
    query = update.callback_query
    await query.answer()

    if query.data == "retry_search":
        await query.edit_message_text("종목명을 입력하세요")
        return ADD_SEARCH_NAME

    ticker = query.data.replace("pick_", "")
    context.user_data['add_ticker'] = ticker

    # 검색 결과에서 종목명 찾기
    results = context.user_data.get('search_results', [])
    stock_name = ticker
    for sn, st in results:
        if st == ticker:
            stock_name = sn
            break
    context.user_data['add_name'] = stock_name

    category = context.user_data.get('add_category', '')
    if category == "interest":
        # 관심종목은 매수정보 불필요 → 바로 저장
        success = pm.add(
            ticker=ticker,
            name=stock_name,
            category="interest",
        )
        if success:
            text = f"등록 완료!\n<b>{stock_name}</b> ({ticker}) - 관심"
        else:
            text = "등록 실패. Supabase 연결을 확인하세요."

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("< 메인메뉴", callback_data="back_main"),
            ]]),
        )
        return MAIN_MENU

    # 보유종목은 매수정보 입력
    await query.edit_message_text(
        f"<b>{stock_name}</b> ({ticker})\n매수가를 입력하세요 (숫자만)",
        parse_mode="HTML",
    )
    return ADD_BUY_PRICE


@_authorized
async def add_buy_price_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """매수가 입력"""
    text = update.message.text.strip().replace(',', '')
    try:
        price = float(text)
        context.user_data['add_buy_price'] = price
        await update.message.reply_text("매수수량을 입력하세요 (숫자만)")
        return ADD_BUY_QUANTITY
    except ValueError:
        await update.message.reply_text("숫자만 입력하세요. 다시 입력:")
        return ADD_BUY_PRICE


@_authorized
async def add_buy_quantity_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """매수수량 입력"""
    text = update.message.text.strip().replace(',', '')
    try:
        qty = int(text)
        context.user_data['add_buy_quantity'] = qty
        await update.message.reply_text("매수일자를 입력하세요 (YYYY-MM-DD)\n생략: n")
        return ADD_BUY_DATE
    except ValueError:
        await update.message.reply_text("정수만 입력하세요. 다시 입력:")
        return ADD_BUY_QUANTITY


@_authorized
async def add_buy_date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """매수일자 입력 → 저장"""
    text = update.message.text.strip()

    buy_date = None
    if text.lower() != 'n':
        try:
            buy_date = datetime.strptime(text, '%Y-%m-%d').date()
        except ValueError:
            await update.message.reply_text("YYYY-MM-DD 형식으로 입력하세요 (예: 2026-01-15)\n생략: n")
            return ADD_BUY_DATE

    ticker = context.user_data['add_ticker']
    name = context.user_data['add_name']
    price = context.user_data['add_buy_price']
    qty = context.user_data['add_buy_quantity']

    success = pm.add(
        ticker=ticker,
        name=name,
        category="possession",
        buy_price=price,
        buy_quantity=qty,
        buy_date=buy_date,
    )

    if success:
        lines = [
            "등록 완료!",
            f"<b>{name}</b> ({ticker}) - 보유",
            f"매수가: {_format_number(price)} | {_format_number(qty)}주",
        ]
        if buy_date:
            lines.append(f"매수일: {buy_date}")
        text = "\n".join(lines)
    else:
        text = "등록 실패. Supabase 연결을 확인하세요."

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("< 메인메뉴", callback_data="back_main"),
        ]]),
    )
    return MAIN_MENU


# === 종목 삭제 플로우 ===

@_authorized
async def delete_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """삭제할 종목 선택"""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text(
            "<b>포트폴리오 관리</b>",
            parse_mode="HTML",
            reply_markup=_main_menu_keyboard(),
        )
        return MAIN_MENU

    portfolio_id = query.data.replace("del_", "")
    context.user_data['delete_id'] = portfolio_id

    # 종목 정보 조회
    items = pm.list_all()
    target = None
    for item in items:
        if item['id'] == portfolio_id:
            target = item
            break

    if not target:
        await query.edit_message_text(
            "종목을 찾을 수 없습니다.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("< 메인메뉴", callback_data="back_main"),
            ]]),
        )
        return MAIN_MENU

    name = target.get('name', '?')
    ticker = target.get('ticker', '?')

    await query.edit_message_text(
        f"<b>{name}</b> ({ticker})를 삭제할까요?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("삭제 확인", callback_data="confirm_delete"),
                InlineKeyboardButton("취소", callback_data="cancel_delete"),
            ],
        ]),
    )
    return DELETE_CONFIRM


@_authorized
async def delete_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """삭제 확인"""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_delete":
        await query.edit_message_text(
            "<b>포트폴리오 관리</b>",
            parse_mode="HTML",
            reply_markup=_main_menu_keyboard(),
        )
        return MAIN_MENU

    portfolio_id = context.user_data.get('delete_id')
    success = pm.delete(portfolio_id)

    text = "삭제 완료!" if success else "삭제 실패."

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("< 메인메뉴", callback_data="back_main"),
        ]]),
    )
    return MAIN_MENU


# === 대화 취소 ===

@_authorized
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """대화 취소"""
    context.user_data.clear()
    await update.message.reply_text("취소되었습니다.")
    return ConversationHandler.END


def main():
    """봇 실행"""
    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        logger.error("TELEGRAM_TOKEN 환경변수가 설정되지 않았습니다.")
        sys.exit(1)

    if not pm.is_available:
        logger.error("Supabase 연결 실패. SUPASECRET_KEY 환경변수를 확인하세요.")
        sys.exit(1)

    logger.info("포트폴리오 봇 시작 (polling)")

    app = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("pf", pf_command)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(main_menu_handler),
            ],
            ADD_CATEGORY: [
                CallbackQueryHandler(add_category_handler),
            ],
            ADD_SEARCH_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_search_name_handler),
            ],
            ADD_SELECT_STOCK: [
                CallbackQueryHandler(add_select_stock_handler),
            ],
            ADD_BUY_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_buy_price_handler),
            ],
            ADD_BUY_QUANTITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_buy_quantity_handler),
            ],
            ADD_BUY_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_buy_date_handler),
            ],
            DELETE_SELECT: [
                CallbackQueryHandler(delete_select_handler),
            ],
            DELETE_CONFIRM: [
                CallbackQueryHandler(delete_confirm_handler),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.run_polling()


if __name__ == "__main__":
    main()

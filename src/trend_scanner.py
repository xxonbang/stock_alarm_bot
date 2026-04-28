"""
트렌드 스캐너 — 매일 KST 07:30·20:00 실행

미국·한국 뉴스/커뮤니티 글을 각 30개씩 수집해 빈도순 종목·섹터 추출 →
TOP3 비판적 전망을 텔레그램 2메시지로 발송한다.

Usage:
    python -m src.trend_scanner          # 정상 실행
    python -m src.trend_scanner --test   # 텔레그램 발송 대신 콘솔 출력
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 프로젝트 루트 추가
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.trend_collectors import us_news, us_community, kr_news, kr_community
from src.trend_extractor import (
    extract_per_batch, select_top3, generate_outlook, verify_indices,
    AIUpstreamError,
)
from src.trend_formatter import format_us, format_kr
from src.ai_researcher import create_researcher
from src.notifier import create_notifier

KST = timezone(timedelta(hours=9))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def _collect_all(now_utc: datetime, now_kst: datetime) -> dict:
    """4배치 병렬 수집 — 일부 실패는 빈 배치로 처리"""
    batches = {}

    logger.info("[수집 1/4] 미국 뉴스...")
    try:
        batches["us_news"] = us_news.collect(now=now_utc, limit=30)
    except Exception as e:
        logger.warning(f"us_news 수집 실패: {e}")
        batches["us_news"] = []

    logger.info("[수집 2/4] 미국 커뮤니티...")
    try:
        batches["us_community"] = us_community.collect(now=now_utc, limit=30)
    except Exception as e:
        logger.warning(f"us_community 수집 실패: {e}")
        batches["us_community"] = []

    logger.info("[수집 3/4] 한국 뉴스...")
    try:
        batches["kr_news"] = kr_news.collect(now=now_utc, limit=30)
    except Exception as e:
        logger.warning(f"kr_news 수집 실패: {e}")
        batches["kr_news"] = []

    logger.info("[수집 4/4] 한국 커뮤니티...")
    try:
        batches["kr_community"] = kr_community.collect(now=now_kst, limit=30)
    except Exception as e:
        logger.warning(f"kr_community 수집 실패: {e}")
        batches["kr_community"] = []

    return batches


def _counts(batches: dict) -> dict:
    return {b: len(items) for b, items in batches.items()}


def main(test_mode: bool = False) -> int:
    logger.info("=" * 50)
    logger.info("트렌드 스캐너 시작")
    if test_mode:
        logger.info("🧪 TEST MODE — 텔레그램 발송 대신 콘솔 출력")

    now_utc = datetime.now(timezone.utc)
    now_kst = now_utc.astimezone(KST)
    logger.info(f"기준 시각: {now_kst.strftime('%Y-%m-%d %H:%M KST')}")

    # 1. 수집
    batches = _collect_all(now_utc, now_kst)
    counts = _counts(batches)
    logger.info(f"수집 결과: {counts}")

    # 1.5. 영역별 가용성 판단
    us_available = (counts["us_news"] + counts["us_community"]) > 0
    kr_available = (counts["kr_news"] + counts["kr_community"]) > 0

    if not us_available and not kr_available:
        logger.error("미국·한국 모든 배치 수집 실패 — abort")
        return 1

    # 2-4. AI 콜 (try/except로 감싸서 실패 시 Telegram 에러 알림)
    try:
        researcher = create_researcher()
        logger.info("[AI 1/3] 4배치 추출...")
        extraction = extract_per_batch(batches, researcher=researcher)

        logger.info("[AI 2/3] TOP3 종합...")
        top3 = select_top3(extraction, researcher=researcher)

        logger.info("[AI 3/3] 전망 생성 (Google Search grounding)...")
        outlook = generate_outlook(top3, researcher=researcher)
    except AIUpstreamError as e:
        logger.error(f"Gemini API 외부 장애: {e}")
        if not test_mode:
            token = os.getenv("TELEGRAM_TOKEN")
            chat_id = os.getenv("CHAT_ID")
            if token and chat_id:
                try:
                    notifier = create_notifier(token, chat_id)
                    notifier.send_message(
                        f"⚠️ 트렌드 스캐너 — Gemini API 외부 장애\n"
                        f"시각: {now_kst.strftime('%Y-%m-%d %H:%M KST')}\n"
                        f"수집: {counts}\n"
                        f"원인: {str(e)[:200]}\n"
                        f"※ 일일 할당량 소진 또는 503 카스케이드. "
                        f"다음 정기 실행(07:30/20:00)에서 자동 재시도됩니다."
                    )
                except Exception as notify_err:
                    logger.error(f"에러 알림 발송 실패: {notify_err}")
        return 1
    except Exception as e:
        logger.error(f"AI 처리 실패: {e}", exc_info=True)
        if not test_mode:
            token = os.getenv("TELEGRAM_TOKEN")
            chat_id = os.getenv("CHAT_ID")
            if token and chat_id:
                try:
                    notifier = create_notifier(token, chat_id)
                    notifier.send_message(
                        f"⚠️ 트렌드 스캐너 AI 처리 실패\n"
                        f"시각: {now_kst.strftime('%Y-%m-%d %H:%M KST')}\n"
                        f"수집: {counts}\n"
                        f"오류: {type(e).__name__}: {str(e)[:300]}"
                    )
                except Exception as notify_err:
                    logger.error(f"에러 알림 발송 실패: {notify_err}")
        return 1

    # 5. 검증
    full_text = str(top3) + str(outlook)
    verify_result = verify_indices(full_text, batches)
    if verify_result["ok"]:
        logger.info(f"✅ 인덱스 검증 통과 ({verify_result['total_refs']}개 인용)")
    else:
        logger.warning(f"⚠️ 인덱스 검증 실패 {len(verify_result['missing'])}건: {verify_result['missing'][:10]}")

    # 6. 포맷
    msg_us = format_us(now_kst, top3, outlook, counts, verify_result) if us_available else None
    msg_kr = format_kr(now_kst, top3, outlook, counts, verify_result) if kr_available else None

    # 7. 발송
    if test_mode:
        if msg_us:
            print("\n=== 미국 메시지 ===\n" + msg_us)
        else:
            print("\n=== 미국 메시지 === (수집 부족으로 생략)")
        if msg_kr:
            print("\n=== 한국 메시지 ===\n" + msg_kr)
        else:
            print("\n=== 한국 메시지 === (수집 부족으로 생략)")
        print(f"\n=== 검증 결과 ===\n{verify_result}")
        return 0

    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("CHAT_ID")
    if not token or not chat_id:
        logger.error("TELEGRAM_TOKEN 또는 CHAT_ID 미설정")
        return 1

    notifier = create_notifier(token, chat_id)
    results = []
    if msg_us:
        results.append(("us", notifier.send_message(msg_us)))
    if msg_kr:
        results.append(("kr", notifier.send_message(msg_kr)))
    for region, ok in results:
        logger.info(f"발송 결과: {region}={ok}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="트렌드 스캐너")
    parser.add_argument("--test", action="store_true", help="콘솔 출력 모드")
    args = parser.parse_args()
    sys.exit(main(test_mode=args.test))

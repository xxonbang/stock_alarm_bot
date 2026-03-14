"""
크로스 프로젝트 데이터 로더
theme_analysis, signal_analysis의 결과 데이터를 로드하여
리포트에 활용할 수 있는 형태로 변환

데이터 소스 우선순위:
1. 로컬 파일 (개발 환경)
2. None (데이터 없으면 해당 섹션 생략)
"""
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# 프로젝트 경로 (환경변수로 오버라이드 가능)
import os
_PROJECT_ROOT = Path(__file__).parent.parent

THEME_ANALYSIS_DATA_PATH = Path(os.getenv(
    'THEME_ANALYSIS_DATA_PATH',
    str(_PROJECT_ROOT.parent / 'theme_analysis' / 'frontend' / 'dist' / 'data')
))
SIGNAL_ANALYSIS_DATA_PATH = Path(os.getenv(
    'SIGNAL_ANALYSIS_DATA_PATH',
    str(_PROJECT_ROOT.parent / 'signal_analysis' / 'results')
))


def _load_json(path: Path) -> Optional[dict]:
    """JSON 파일 안전 로드"""
    try:
        if not path.exists():
            logger.debug(f"파일 없음: {path}")
            return None
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"JSON 로드 실패 ({path}): {e}")
        return None


def get_theme_forecast() -> Optional[List[Dict]]:
    """
    theme_analysis의 오늘 테마 예측 로드

    Returns:
        [{'theme_name', 'catalyst', 'confidence', 'leader_stocks': [...]}] 또는 None
    """
    data = _load_json(THEME_ANALYSIS_DATA_PATH / "theme-forecast.json")
    if not data:
        return None

    today_themes = data.get("today", [])
    if not today_themes:
        return None

    # 신뢰도 높음/중간만 필터
    filtered = [t for t in today_themes if t.get("confidence") in ("높음", "중간")]
    return filtered if filtered else None


def get_theme_forecast_text() -> str:
    """테마 예측을 AI 프롬프트용 텍스트로 변환"""
    themes = get_theme_forecast()
    if not themes:
        return ""

    lines = ["[THEME_FORECAST]"]
    for t in themes[:3]:  # 최대 3개
        lines.append(f"테마: {t.get('theme_name', 'N/A')} [신뢰: {t.get('confidence', 'N/A')}]")
        lines.append(f"  촉매: {t.get('catalyst', 'N/A')}")
        leaders = t.get("leader_stocks", [])
        if leaders:
            leader_names = [f"{l.get('name', '')}({l.get('code', '')})" for l in leaders[:3]]
            lines.append(f"  대장주: {' > '.join(leader_names)}")
        lines.append("")
    return "\n".join(lines)


def get_cross_validated_signals() -> Optional[List[Dict]]:
    """
    signal_analysis의 교차검증 시그널 (Vision+KIS 일치) 로드

    Returns:
        매수/매도 시그널 리스트 또는 None
    """
    data = _load_json(SIGNAL_ANALYSIS_DATA_PATH / "combined" / "combined_analysis.json")
    if not data:
        return None

    results = data.get("results", [])
    if not results:
        return None

    # match_status가 match이고 적극매수/적극매도인 종목만
    strong = [s for s in results
              if s.get("match_status") == "match"
              and s.get("signal") in ("적극매수", "적극매도")]

    if not strong:
        # match가 없으면 partial 중에서도 적극매수만
        strong = [s for s in results
                  if s.get("match_status") == "partial"
                  and s.get("signal") == "적극매수"]

    # 점수 내림차순 정렬
    strong.sort(key=lambda x: x.get("total_score", 0) or 0, reverse=True)
    return strong[:5] if strong else None


def get_cross_validated_signals_text() -> str:
    """교차검증 시그널을 AI 프롬프트용 텍스트로 변환"""
    signals = get_cross_validated_signals()
    if not signals:
        return ""

    lines = ["[AI_CROSS_VALIDATED_SIGNALS]"]
    for s in signals:
        signal_type = s.get("signal", "N/A")
        name = s.get("name", s.get("stock_name", "N/A"))
        code = s.get("code", s.get("stock_code", "N/A"))
        score = s.get("total_score", "N/A")
        confidence = s.get("confidence", "N/A")
        reason = s.get("reason", "")[:100]
        lines.append(f"{signal_type}: {name}({code}) 점수:{score} 신뢰:{confidence}")
        if reason:
            lines.append(f"  근거: {reason}")
    return "\n".join(lines)


def get_macro_indicators() -> Optional[Dict]:
    """theme_analysis의 매크로 지표 로드"""
    return _load_json(THEME_ANALYSIS_DATA_PATH / "macro-indicators.json")


def get_paper_trading_performance(days: int = 5) -> Optional[List[Dict]]:
    """
    최근 N일 페이퍼 트레이딩 성과 로드

    Returns:
        [{'date', 'total_profit_rate', 'win', 'loss', 'total'}] 또는 None
    """
    pt_dir = THEME_ANALYSIS_DATA_PATH / "paper-trading"
    if not pt_dir.exists():
        return None

    index_data = _load_json(pt_dir.parent / "paper-trading-index.json")
    if not index_data:
        # 인덱스 없으면 디렉토리 스캔
        try:
            files = sorted(pt_dir.glob("*.json"), reverse=True)
        except Exception:
            return None
    else:
        files = []

    results = []
    seen_dates = set()

    # 인덱스 기반 또는 파일 기반으로 최근 N일 로드
    source_files = files if files else [pt_dir / f for f in (index_data or [])]

    for f in source_files:
        if len(results) >= days:
            break
        data = _load_json(f) if isinstance(f, Path) else None
        if not data:
            continue
        date_str = data.get("date", "")
        if date_str in seen_dates:
            continue
        seen_dates.add(date_str)

        summary = data.get("summary", {})
        results.append({
            "date": date_str,
            "total_profit_rate": summary.get("total_profit_rate", 0),
            "win": summary.get("profit_count", 0),
            "loss": summary.get("loss_count", 0),
            "total": summary.get("total_count", 0),
        })

    return results if results else None


def get_paper_trading_text() -> str:
    """페이퍼 트레이딩 성과를 텍스트로 변환"""
    perf = get_paper_trading_performance()
    if not perf:
        return ""

    lines = ["[AI_RECOMMENDATION_PERFORMANCE]"]
    for p in perf:
        rate = p["total_profit_rate"]
        emoji = "🟢" if rate >= 0 else "🔴"
        lines.append(f"{p['date']}: {emoji}{rate:+.1f}% ({p['win']}승 {p['loss']}패)")
    return "\n".join(lines)


def get_enriched_data_for_ai() -> str:
    """
    AI 프롬프트에 주입할 추가 데이터 블록
    모든 크로스 프로젝트 데이터를 텍스트로 결합

    Returns:
        AI 프롬프트 주입용 텍스트 (데이터 없으면 빈 문자열)
    """
    blocks = []

    theme_text = get_theme_forecast_text()
    if theme_text:
        blocks.append(theme_text)

    signal_text = get_cross_validated_signals_text()
    if signal_text:
        blocks.append(signal_text)

    if not blocks:
        logger.info("크로스 프로젝트 데이터 없음 (정상 - 다른 프로젝트 미실행)")
        return ""

    result = "\n\n".join(blocks)
    logger.info(f"크로스 프로젝트 데이터 로드 완료: {len(result)}자")
    return result

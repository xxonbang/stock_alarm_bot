"""트렌드 스캐너 AI 추출 + 검증 모듈"""
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Tuple

from src.trend_collectors.base import CollectedItem, format_indexed_text

logger = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).parent.parent / "config" / "prompts"

LABEL_TO_BATCH = {
    "미뉴스": "us_news",
    "미커뮤": "us_community",
    "한뉴스": "kr_news",
    "한커뮤": "kr_community",
}

# 단일 또는 묶음 인덱스 모두 매칭: [미뉴스#3] 또는 [미뉴스#3,#7,#12]
BUNDLE_PATTERN = re.compile(r"\[(미뉴스|미커뮤|한뉴스|한커뮤)((?:#\d+,?)+)\]")
NUM_PATTERN = re.compile(r"#(\d+)")


def verify_indices(text: str, batches: Dict[str, List[CollectedItem]]) -> Dict:
    """
    출력 text에 등장한 [라벨#N] 또는 [라벨#a,#b,#c] 인덱스를
    실제 수집 데이터와 매핑 검증.

    Returns:
        {"ok": bool, "missing": [(batch, idx), ...], "total_refs": int}
    """
    cited = set()
    for label, body in BUNDLE_PATTERN.findall(text):
        for n in NUM_PATTERN.findall(body):
            cited.add((LABEL_TO_BATCH[label], int(n)))

    actual = {(b, item.idx) for b, items in batches.items() for item in items}
    missing = sorted(cited - actual)

    return {"ok": len(missing) == 0, "missing": missing, "total_refs": len(cited)}


def _load_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def _strip_codeblock(text: str) -> str:
    """LLM이 ```json ... ``` 으로 감싼 경우 안쪽 JSON만 반환"""
    s = text.strip()
    if s.startswith("```"):
        # 첫 줄(```json 등) 제거
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


# `_call_ai`가 모든 재시도 실패 시 반환하는 sentinel 문자열들.
# 이를 JSON 파싱 시도하면 의미없는 재시도로 quota만 소진되므로 즉시 raise.
_AI_ERROR_SENTINELS = (
    "API 할당량 초과",
    "오류:",
)


class AIUpstreamError(RuntimeError):
    """Gemini API 외부 장애 (할당량 초과·503 카스케이드 등). JSON 파싱 재시도 무의미."""


def _parse_json_with_retry(
    researcher,
    prompt: str,
    max_retries: int = 3,
    temperature: float = 0.2,
    enable_search: bool = False,
    max_output_tokens: int = 32000,
) -> Tuple[Dict, Dict]:
    """LLM 응답을 JSON 파싱. 실패 시 재시도 (최초 1회 + 추가 max_retries-1회).

    `_call_ai`가 sentinel 문자열을 반환하면(외부 API 장애) 즉시 AIUpstreamError raise.
    재시도해도 같은 sentinel이 돌아오며 quota만 소진되기 때문.

    enable_search=True 시 Google Search grounding 활성화.
    max_output_tokens는 추출 콜의 80개 entry × refs 출력에 충분한 32000 기본값.
    Gemini 2.5 Flash는 출력 64K까지 지원하므로 안전.
    """
    last_err = None
    for attempt in range(max_retries):
        attempt_prompt = prompt
        if attempt > 0:
            attempt_prompt = (
                prompt
                + "\n\n[중요] 이전 응답이 JSON 파싱에 실패했습니다. "
                "반드시 유효한 JSON 객체만 출력하고, "
                "마크다운 코드블록·설명 텍스트를 포함하지 마세요."
            )
        try:
            text, usage = researcher.call(
                prompt=attempt_prompt,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                enable_search=enable_search,
            )
            stripped = (text or "").strip()
            # 외부 API 장애 sentinel 즉시 감지 → 재시도 무의미
            for sentinel in _AI_ERROR_SENTINELS:
                if stripped.startswith(sentinel):
                    raise AIUpstreamError(stripped[:300])
            cleaned = _strip_codeblock(text)
            return json.loads(cleaned), usage
        except json.JSONDecodeError as e:
            last_err = e
            logger.warning(f"AI JSON 파싱 실패 (시도 {attempt + 1}/{max_retries}): {e}")
    raise RuntimeError(f"AI JSON 파싱 {max_retries}회 실패: {last_err}")


# 동의어 정규화 사전 — 같은 종목/섹터의 다양한 표기를 대표 표기로 통합.
# LLM이 별칭으로 분리해 출력해도 후처리에서 합산.
_NAME_ALIASES: Dict[str, str] = {
    # 미국 종목
    "엔비디아": "Nvidia", "NVDA": "Nvidia", "nvidia corp": "Nvidia", "NVIDIA": "Nvidia",
    "애플": "Apple", "AAPL": "Apple",
    "마이크로소프트": "Microsoft", "MSFT": "Microsoft", "MS": "Microsoft",
    "알파벳": "Alphabet", "GOOGL": "Alphabet", "GOOG": "Alphabet", "구글": "Alphabet", "Google": "Alphabet",
    "아마존": "Amazon", "AMZN": "Amazon",
    "메타": "Meta", "META": "Meta", "Facebook": "Meta", "페이스북": "Meta",
    "테슬라": "Tesla", "TSLA": "Tesla",
    "AMD": "AMD", "에이엠디": "AMD",
    "TSMC": "TSMC", "타이완 반도체": "TSMC", "Taiwan Semiconductor": "TSMC",
    "인텔": "Intel", "INTC": "Intel",
    "브로드컴": "Broadcom", "AVGO": "Broadcom",
    "팔란티어": "Palantir", "PLTR": "Palantir",
    # 한국 종목
    "삼성전자우": "삼성전자", "005930": "삼성전자",
    "SK하이닉스": "SK하이닉스", "000660": "SK하이닉스", "하이닉스": "SK하이닉스",
    "LG에너지솔루션": "LG에너지솔루션", "LG엔솔": "LG에너지솔루션", "엘지에너지솔루션": "LG에너지솔루션",
    "현대차": "현대자동차", "현대자동차": "현대자동차",
    "네이버": "NAVER", "Naver": "NAVER",
    "카카오": "Kakao", "KAKAO": "Kakao",
    "셀트리온": "셀트리온",
    "한화에어로스페이스": "한화에어로스페이스", "한화에어로": "한화에어로스페이스",
    # 섹터 동의어
    "AI": "AI", "인공지능": "AI", "artificial intelligence": "AI", "Artificial Intelligence": "AI",
    "반도체": "반도체", "semiconductor": "반도체", "Semiconductor": "반도체", "Semiconductors": "반도체",
    "2차전지": "2차전지", "이차전지": "2차전지", "Battery": "2차전지", "EV battery": "2차전지",
    "바이오": "바이오", "biotech": "바이오", "Biotech": "바이오", "제약": "바이오", "Pharmaceuticals": "바이오",
    "방산": "방산", "Defense": "방산", "Defence": "방산",
    "원자력": "원자력", "Nuclear": "원자력", "원전": "원자력",
    "Cloud": "클라우드", "클라우드": "클라우드",
    "Fintech": "핀테크", "핀테크": "핀테크",
    "Healthcare": "Healthcare", "헬스케어": "Healthcare",
    "Energy": "Energy", "에너지": "Energy",
}


def _canonical_name(name: str) -> str:
    """별칭 → 대표 표기. 매칭 안되면 원래 이름 그대로."""
    if not name:
        return name
    return _NAME_ALIASES.get(name.strip(), name.strip())


def _normalize_aliases_in_extraction(extraction: Dict) -> Dict:
    """배치별 stocks·sectors의 name을 canonical 표기로 통합 + freq 합산"""
    for batch_key in ("us_news", "us_community", "kr_news", "kr_community"):
        batch = extraction.get(batch_key)
        if not isinstance(batch, dict):
            continue
        for field in ("stocks", "sectors"):
            entries = batch.get(field, [])
            merged: Dict[str, Dict] = {}
            for e in entries:
                canon = _canonical_name(e.get("name", ""))
                if not canon:
                    continue
                if canon not in merged:
                    merged[canon] = {"name": canon, "freq": 0, "refs": []}
                merged[canon]["freq"] += e.get("freq", 0)
                merged[canon]["refs"].extend(e.get("refs", []) or [])
            # refs 중복 제거 + 정렬, freq 내림차순
            for v in merged.values():
                v["refs"] = sorted(set(v["refs"]))
            sorted_entries = sorted(merged.values(), key=lambda x: x["freq"], reverse=True)
            batch[field] = sorted_entries
    return extraction


# 종목·섹터 양쪽에서 모두 배제할 인덱스/시장명/ETF/펀드 토큰 (대소문자 무관, 부분 매칭).
# LLM이 prompt 지시를 무시하고 stocks에 인덱스를 넣을 경우의 안전망.
_INDEX_TOKENS = {
    # 한국 인덱스/시장명
    "코스피", "코스닥", "kospi", "kospi200", "kospi 200", "코스피200",
    "kosdaq", "krx", "k200", "k-otc", "한국 증시", "한국증시",
    # 미국 인덱스/시장명
    "s&p 500", "s&p500", "s&p", "snp500",
    "nasdaq", "nasdaq composite", "nasdaq-100", "nasdaq 100",
    "dow", "dow jones", "djia", "dow industrial",
    "russell", "russell 2000", "russell 1000",
    "vix", "wall street", "월스트리트", "미국 증시", "미국증시",
    # 흔한 ETF
    "spy", "qqq", "arkk", "vti", "voo", "iwm", "tqqq", "sqqq", "soxl", "soxs",
}


def _is_index_or_market(name: str) -> bool:
    """종목명이 지수·시장명·ETF인지 판정 (대소문자 무관)."""
    if not name:
        return False
    n = name.strip().lower()
    # 정확 일치 또는 단어 단위 포함
    for token in _INDEX_TOKENS:
        if n == token or token in n.split():
            return True
        # 예: "S&P 500" 같이 공백 포함 토큰의 경우 substring 검사
        if " " in token and token in n:
            return True
    return False


def _filter_indices_from_extraction(extraction: Dict) -> Dict:
    """배치별 stocks·sectors에서 지수·시장명·ETF 제거 (안전망)."""
    for batch_key in ("us_news", "us_community", "kr_news", "kr_community"):
        batch = extraction.get(batch_key)
        if not isinstance(batch, dict):
            continue
        for field in ("stocks", "sectors"):
            entries = batch.get(field, [])
            filtered = [e for e in entries if not _is_index_or_market(e.get("name", ""))]
            removed = len(entries) - len(filtered)
            if removed:
                logger.info(f"  필터: {batch_key}.{field}에서 인덱스/시장명 {removed}건 제거")
            batch[field] = filtered
    return extraction


def _filter_indices_from_top3(top3: Dict) -> Dict:
    """TOP3 결과에서도 인덱스 제거 (LLM이 또 슬립할 때 대비)."""
    for key in ("us_top3_sectors", "us_top3_stocks", "kr_top3_sectors", "kr_top3_stocks"):
        entries = top3.get(key, [])
        filtered = [e for e in entries if not _is_index_or_market(e.get("name", ""))]
        removed = len(entries) - len(filtered)
        if removed:
            logger.info(f"  필터: {key}에서 인덱스/시장명 {removed}건 제거")
        top3[key] = filtered
    return top3


def extract_per_batch(
    batches: Dict[str, List[CollectedItem]],
    researcher,
) -> Dict:
    """
    AI 콜 #1 — 4배치 일괄 추출.
    각 배치에서 종목 10 + 섹터 10을 빈도순으로 추출.
    """
    template = _load_prompt("trend_extract.txt")

    # 모든 배치를 인덱스 부착해 직렬화
    all_items: List[CollectedItem] = []
    for b in ("us_news", "us_community", "kr_news", "kr_community"):
        all_items.extend(batches.get(b, []))
    collected_text = format_indexed_text(all_items)

    prompt = template.replace("{COLLECTED_TEXT}", collected_text)

    result, _usage = _parse_json_with_retry(researcher, prompt)
    # 후처리: 별칭 통합 → 인덱스/시장명 제거
    result = _normalize_aliases_in_extraction(result)
    return _filter_indices_from_extraction(result)


def select_top3(extraction: Dict, researcher) -> Dict:
    """
    AI 콜 #2 — 영역별 TOP3 섹터·종목 + 선정 이유.
    """
    template = _load_prompt("trend_top3.txt")
    prompt = template.replace("{EXTRACTION_RESULT}", json.dumps(extraction, ensure_ascii=False, indent=2))
    result, _usage = _parse_json_with_retry(researcher, prompt)
    return _filter_indices_from_top3(result)


def _has_any_top3_entry(top3: Dict) -> bool:
    """TOP3 결과에 적어도 하나의 항목이 있는지"""
    for key in ("us_top3_sectors", "us_top3_stocks", "kr_top3_sectors", "kr_top3_stocks"):
        if top3.get(key):
            return True
    return False


def analyze_youtube(videos, researcher) -> Dict:
    """
    유튜브 영상 10개에서 TOP3 종목·섹터 추출 + 영상 내용 요약.
    videos: List[YoutubeVideo]
    """
    if not videos:
        return {"top3_sectors": [], "top3_stocks": []}

    template = _load_prompt("youtube_trend.txt")
    parts = []
    for i, v in enumerate(videos, start=1):
        ts = v.published_at.strftime("%Y-%m-%d")
        body = v.transcript or v.description or "(자막·설명 없음)"
        parts.append(f"[영상#{i}] [{v.channel_name}] {ts} — {v.title}\n{body[:3000]}")
    videos_text = "\n\n".join(parts)
    prompt = template.replace("{VIDEOS_TEXT}", videos_text)

    result, _usage = _parse_json_with_retry(researcher, prompt)
    # 인덱스/시장명 안전망
    for key in ("top3_sectors", "top3_stocks"):
        entries = result.get(key, [])
        result[key] = [e for e in entries if not _is_index_or_market(e.get("name", ""))]
    return result


def generate_outlook(
    top3: Dict,
    researcher,
) -> Dict:
    """
    AI 콜 #3 — 12개 항목의 향후 1주일 전망.
    Gemini Google Search grounding을 활성화하여 모델이 직접 최신 정보를 검색·조사한 뒤
    보수적·객관적 톤으로 작성한다. TOP3 결과만 입력으로 사용.
    """
    if not _has_any_top3_entry(top3):
        raise RuntimeError(
            "TOP3 결과가 비어있어 outlook 생성 불가 — abort"
        )

    template = _load_prompt("trend_outlook.txt")
    prompt = template.replace(
        "{TOP3_RESULT}",
        json.dumps(top3, ensure_ascii=False, indent=2),
    )

    result, _usage = _parse_json_with_retry(
        researcher, prompt, enable_search=True
    )
    return result

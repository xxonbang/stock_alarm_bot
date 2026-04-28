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
    return result


def select_top3(extraction: Dict, researcher) -> Dict:
    """
    AI 콜 #2 — 영역별 TOP3 섹터·종목 + 선정 이유.
    """
    template = _load_prompt("trend_top3.txt")
    prompt = template.replace("{EXTRACTION_RESULT}", json.dumps(extraction, ensure_ascii=False, indent=2))
    result, _usage = _parse_json_with_retry(researcher, prompt)
    return result


def _has_any_top3_entry(top3: Dict) -> bool:
    """TOP3 결과에 적어도 하나의 항목이 있는지"""
    for key in ("us_top3_sectors", "us_top3_stocks", "kr_top3_sectors", "kr_top3_stocks"):
        if top3.get(key):
            return True
    return False


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

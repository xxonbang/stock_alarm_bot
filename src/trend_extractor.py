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

INDEX_PATTERN = re.compile(r"\[(미뉴스|미커뮤|한뉴스|한커뮤)#(\d+)\]")


def verify_indices(text: str, batches: Dict[str, List[CollectedItem]]) -> Dict:
    """
    출력 text에 등장한 [라벨#N] 인덱스를 실제 수집 데이터와 매핑 검증.

    Returns:
        {"ok": bool, "missing": [(batch, idx), ...], "total_refs": int}
    """
    found = INDEX_PATTERN.findall(text)
    cited = {(LABEL_TO_BATCH[lbl], int(n)) for lbl, n in found}

    actual = {(b, item.idx) for b, items in batches.items() for item in items}
    missing = sorted(cited - actual)

    return {"ok": len(missing) == 0, "missing": missing, "total_refs": len(found)}


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


def _parse_json_with_retry(
    researcher,
    prompt: str,
    max_retries: int = 3,
    temperature: float = 0.2,
) -> Tuple[Dict, Dict]:
    """LLM 응답을 JSON 파싱. 실패 시 재시도 (최초 1회 + 추가 max_retries-1회)."""
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
                max_output_tokens=8000,
            )
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


def _collect_referenced_indices(top3: Dict) -> Dict[str, set]:
    """TOP3 결과의 모든 *_refs 필드에서 인용된 인덱스를 batch별로 모음"""
    refs: Dict[str, set] = {b: set() for b in ("us_news", "us_community", "kr_news", "kr_community")}
    field_to_batch = [
        ("us_news_refs", "us_news"),
        ("us_community_refs", "us_community"),
        ("kr_news_refs", "kr_news"),
        ("kr_community_refs", "kr_community"),
    ]
    for key in ("us_top3_sectors", "us_top3_stocks", "kr_top3_sectors", "kr_top3_stocks"):
        for entry in top3.get(key, []):
            for field, batch in field_to_batch:
                for idx in entry.get(field, []) or []:
                    refs[batch].add(int(idx))
    return refs


def generate_outlook(
    top3: Dict,
    batches: Dict[str, List[CollectedItem]],
    researcher,
) -> Dict:
    """
    AI 콜 #3 — 12개 항목 전망. TOP3 reason에 인용된 글만 프롬프트에 포함.
    """
    template = _load_prompt("trend_outlook.txt")

    # 인용된 글만 필터
    referenced = _collect_referenced_indices(top3)
    referenced_items: List[CollectedItem] = []
    for batch, idx_set in referenced.items():
        for it in batches.get(batch, []):
            if it.idx in idx_set:
                referenced_items.append(it)

    if not referenced_items:
        raise RuntimeError(
            "TOP3 결과에 참조된 인덱스가 없어 outlook 생성 불가 — "
            "할루시네이션 방지를 위해 abort"
        )

    referenced_text = format_indexed_text(referenced_items)

    prompt = (
        template
        .replace("{TOP3_RESULT}", json.dumps(top3, ensure_ascii=False, indent=2))
        .replace("{REFERENCED_TEXTS}", referenced_text)
    )

    result, _usage = _parse_json_with_retry(researcher, prompt)
    return result

"""유튜브 영상 수집 — YouTube Data API v3 + youtube-transcript-api

최근 7일 내 업로드된 한국 주식 관련 유명 채널의 영상 10개 수집.
영상 메타데이터(제목, 설명, 채널)와 자막을 묶어 분석에 활용.

채널 ID 참고:
- 슈카월드     UCsJ6RuBiTVWRX156FVbeaGg
- 박곰희TV    UCkhxNAY1jYV9DYyP-IJVwfg
- 신사임당    UCXR4lsO_ABUd1bIuWiIjJzQ
- 한경와우TV  UCRGNS8VBtfqMnp9LGV4t-Yw
- 김작가TV    UCjdBoxoTqRpFqeC9Yv7BhCw
"""
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# 한국 주식 관련 유명 유튜브 채널 (channel_id, name) — 모두 검증 완료
KR_STOCK_CHANNELS = [
    ("UCsJ6RuBiTVWRX156FVbeaGg", "슈카월드"),
    ("UCr7XsrSrvAn_WcU4kF99bbQ", "박곰희TV"),
    ("UCaJdckl6MBdDPDf75Ec_bJA", "신사임당"),
    ("UCGCGxsbmG_9nincyI7xypow", "한경 코리아마켓"),
    ("UCvil4OAt-zShzkKHsg9EQAw", "김작가 TV"),
    ("UChlv4GSd7OQl3js-jkLOnFA", "삼프로TV 3PROTV"),
    ("UC_l2qrs1qRv_8Rs8utay-PQ", "메르의 세상읽기"),
]

# 키워드 검색으로 추가 영상 (백필)
SEARCH_KEYWORDS = ["코스피 전망", "주식 시황", "美 증시"]


@dataclass
class YoutubeVideo:
    """수집된 유튜브 영상 1건"""
    video_id: str
    title: str
    description: str
    channel_name: str
    published_at: datetime  # tz-aware (UTC 또는 KST)
    transcript: str = ""  # 자막 텍스트 (있으면)
    url: str = field(default="")

    def __post_init__(self):
        if not self.url:
            self.url = f"https://www.youtube.com/watch?v={self.video_id}"


def _get_client():
    """YouTube Data API client. 환경변수에서 API key 로드."""
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY 환경변수 미설정")
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


def _list_recent_videos_from_channel(youtube, channel_id: str, since: datetime, max_results: int = 5) -> List[dict]:
    """채널의 최근 영상 목록 (since 이후)"""
    try:
        # search.list로 채널의 최근 영상 가져오기 (publishedAfter 필터)
        published_after = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        request = youtube.search().list(
            channelId=channel_id,
            part="id,snippet",
            order="date",
            type="video",
            publishedAfter=published_after,
            maxResults=max_results,
        )
        response = request.execute()
        return response.get("items", [])
    except Exception as e:
        logger.warning(f"YouTube 채널 검색 실패 ({channel_id[:8]}...): {e}")
        return []


def _search_videos_by_keyword(youtube, keyword: str, since: datetime, max_results: int = 5) -> List[dict]:
    """키워드 검색으로 영상 가져오기"""
    try:
        published_after = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        request = youtube.search().list(
            q=keyword,
            part="id,snippet",
            order="relevance",
            type="video",
            publishedAfter=published_after,
            regionCode="KR",
            relevanceLanguage="ko",
            maxResults=max_results,
        )
        response = request.execute()
        return response.get("items", [])
    except Exception as e:
        logger.warning(f"YouTube 키워드 검색 실패 ({keyword}): {e}")
        return []


def _fetch_transcript(video_id: str) -> str:
    """영상 자막 추출. 한국어 우선, 영어 fallback. 실패 시 빈 문자열."""
    try:
        api = YouTubeTranscriptApi()
        # ko 우선, en fallback (자동 생성 포함)
        fetched = api.fetch(video_id, languages=["ko", "en"])
        # fetched는 FetchedTranscript 객체. iteration으로 segment 접근
        text_parts = []
        for seg in fetched:
            # seg는 FetchedTranscriptSnippet (text, start, duration 속성)
            t = getattr(seg, "text", None) or (seg.get("text") if isinstance(seg, dict) else None)
            if t:
                text_parts.append(t)
        text = " ".join(text_parts)
        return text[:5000]  # 5000자 제한 (LLM 토큰 절약)
    except (TranscriptsDisabled, NoTranscriptFound):
        return ""
    except Exception as e:
        logger.debug(f"transcript fetch 실패 ({video_id}): {e}")
        return ""


def _item_to_video(item: dict, channel_name_override: Optional[str] = None) -> Optional[YoutubeVideo]:
    """YouTube API 응답 항목 → YoutubeVideo"""
    snippet = item.get("snippet") or {}
    video_id = (item.get("id") or {}).get("videoId") if isinstance(item.get("id"), dict) else item.get("id")
    if not video_id:
        return None
    title = (snippet.get("title") or "").strip()
    description = (snippet.get("description") or "").strip()
    channel_name = channel_name_override or snippet.get("channelTitle", "")
    published_str = snippet.get("publishedAt", "")
    try:
        published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return YoutubeVideo(
        video_id=video_id,
        title=title,
        description=description,
        channel_name=channel_name,
        published_at=published,
    )


def collect(now: Optional[datetime] = None, limit: int = 10) -> List[YoutubeVideo]:
    """최근 7일 내 한국 주식 관련 유튜브 영상 수집. 채널 우선 + 키워드 보충."""
    if now is None:
        now = datetime.now(timezone.utc)
    since = now - timedelta(days=7)

    try:
        youtube = _get_client()
    except Exception as e:
        logger.error(f"YouTube client 초기화 실패: {e}")
        return []

    seen_video_ids = set()
    videos: List[YoutubeVideo] = []

    # 1. 지정 채널에서 최근 영상 가져오기
    for channel_id, channel_name in KR_STOCK_CHANNELS:
        items = _list_recent_videos_from_channel(youtube, channel_id, since, max_results=3)
        for item in items:
            v = _item_to_video(item, channel_name_override=channel_name)
            if not v or v.video_id in seen_video_ids:
                continue
            seen_video_ids.add(v.video_id)
            videos.append(v)

    # 2. 키워드 검색으로 보충 (limit 못 채우면)
    if len(videos) < limit:
        for kw in SEARCH_KEYWORDS:
            if len(videos) >= limit:
                break
            items = _search_videos_by_keyword(youtube, kw, since, max_results=5)
            for item in items:
                if len(videos) >= limit:
                    break
                v = _item_to_video(item)
                if not v or v.video_id in seen_video_ids:
                    continue
                seen_video_ids.add(v.video_id)
                videos.append(v)

    # 3. 발행 시간 내림차순 정렬, limit 적용
    videos.sort(key=lambda x: x.published_at, reverse=True)
    videos = videos[:limit]

    # 4. 자막 추출 (limit 영상에 한해)
    for v in videos:
        v.transcript = _fetch_transcript(v.video_id)

    logger.info(
        f"youtube 수집 완료: {len(videos)}개 (자막 있음 "
        f"{sum(1 for v in videos if v.transcript)}개)"
    )
    return videos


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # 로컬 실행 시 .env 로드 (GitHub Actions에서는 환경변수로 주입됨)
    try:
        from dotenv import load_dotenv
        from pathlib import Path
        load_dotenv(Path(__file__).parent.parent.parent / ".env")
    except ImportError:
        pass
    for v in collect():
        ts = v.published_at.astimezone(KST).strftime("%Y-%m-%d %H:%M")
        print(f"[{ts}] [{v.channel_name}] {v.title}")
        print(f"  자막: {len(v.transcript)}자")

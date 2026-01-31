"""
뉴스 및 시황 크롤링 모듈 (고도화 버전)
뉴스 제목+요약문 수집 및 매크로 경제 지표 수집

[중요: AI 금지 구역]
이 모듈은 데이터 수집 전용입니다. AI API 호출을 절대 하지 않습니다.
- google.generativeai 라이브러리 import 금지
- AI를 사용한 번역/요약 금지
- 모든 데이터는 원문 그대로 반환 (최종 리포트 단계에서 AI가 처리)
"""
# curl_cffi를 사용하여 TLS Fingerprint 차단 우회
try:
    from curl_cffi import requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    # curl_cffi가 없으면 일반 requests 사용 (fallback)
    try:
        import requests
    except ImportError:
        requests = None
    CURL_CFFI_AVAILABLE = False

from bs4 import BeautifulSoup
import logging
from typing import List, Dict, Optional
import time
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta, date
import os
import re
import warnings

# Settings import (포트폴리오 종목 정보용)
try:
    from config.settings import settings
except ImportError:
    # settings를 사용할 수 없는 경우를 위한 fallback
    settings = None
try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    feedparser = None
    FEEDPARSER_AVAILABLE = False
try:
    from fredapi import Fred
except ImportError:
    Fred = None

# SSL 경고 무시 (한경 컨센서스 등에서 verify=False 사용 시)
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

# AI 금지 검증: 이 파일에서 직접 import하지 않았는지 확인
# (다른 모듈에서 간접적으로 import되는 것은 허용)
import sys
if 'google.generativeai' in sys.modules:
    # 다른 모듈에서 이미 import된 경우, 이 파일에서 직접 import한 것은 아님
    pass
# 이 파일에서는 google.generativeai를 직접 import하지 않음 (정상)

logger = logging.getLogger(__name__)

# User-Agent 헤더 (봇 차단 방지) - 검증된 Chrome 브라우저 위장
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.google.com/"
}

# curl_cffi Session 생성 (브라우저 의태로 TLS 차단 우회)
def _create_session():
    """
    curl_cffi를 사용한 Session 객체 생성
    impersonate="chrome120" 옵션으로 Chrome 브라우저의 TLS 지문을 완벽하게 복제
    """
    if CURL_CFFI_AVAILABLE:
        try:
            # curl_cffi의 Session은 impersonate 파라미터를 지원
            session = requests.Session(impersonate="chrome120")
            logger.info("✅ curl_cffi Session 생성 완료 (TLS Fingerprint 우회 활성화)")
            return session
        except Exception as e:
            # curl_cffi Session 생성 실패 시 일반 requests 사용
            import requests as std_requests
            session = std_requests.Session()
            logger.warning(f"⚠️ curl_cffi Session 생성 실패: {e}, 일반 requests 사용")
            return session
    else:
        # curl_cffi가 없으면 일반 requests 사용
        session = requests.Session()
        logger.warning("⚠️ curl_cffi가 설치되지 않아 일반 requests를 사용합니다. TLS 차단 우회 기능이 없습니다.")
        return session

# 전역 세션 객체 생성
_session = _create_session()

# KRX API 상태 추적 (유효기간 종료 여부)
_krx_api_expired = False
_krx_api_expiry_checked = False

def get_krx_api_expired_status() -> bool:
    """
    KRX API 만료 상태 반환 (401 오류 기반)
    
    Returns:
        만료 여부 (bool)
    """
    global _krx_api_expired
    return _krx_api_expired


def get_yahoo_finance_news(max_items: int = 10) -> List[Dict]:
    """
    Yahoo Finance RSS 피드를 사용하여 일반 뉴스 수집
    티커 기반이 아닌 RSS 피드에서 수집하여 포트폴리오와 무관한 Hot 뉴스 수집
    
    Args:
        max_items: 최대 수집할 뉴스 개수
    
    Returns:
        [{"title": "...", "summary": "...", "link": "..."}, ...] 형태의 리스트
    """
    news_items = []
    
    if not FEEDPARSER_AVAILABLE:
        logger.warning("feedparser가 설치되지 않음, Yahoo Finance RSS 수집 불가")
        return []
    
    try:
        # Yahoo Finance RSS 피드 URL
        rss_urls = [
            "https://feeds.finance.yahoo.com/rss/2.0/headline",
            "https://finance.yahoo.com/news/rss/",
            "https://feeds.finance.yahoo.com/rss/2.0/headline?region=US&lang=en-US"
        ]
        
        all_news = []
        seen_titles = set()
        
        for rss_url in rss_urls:
            try:
                logger.info(f"Yahoo Finance RSS 피드 수집 중: {rss_url}")
                
                response = _session.get(rss_url, headers=HEADERS, timeout=15)
                response.raise_for_status()
                
                # feedparser로 RSS 파싱
                feed = feedparser.parse(response.content)
                
                if not feed.entries:
                    logger.debug(f"RSS 피드 항목 없음: {rss_url}")
                    continue
                
                logger.info(f"Yahoo Finance RSS 피드에서 {len(feed.entries)}개 항목 발견")
                
                for entry in feed.entries:
                    try:
                        title = entry.get('title', '').strip()
                        link = entry.get('link', '')
                        summary = entry.get('summary', '') or entry.get('description', '')
                        
                        if not title or len(title) < 20:
                            continue
                        
                        # 중복 제거
                        title_lower = title.lower().strip()
                        if title_lower in seen_titles:
                            continue
                        seen_titles.add(title_lower)
                        
                        all_news.append({
                            'title': title,
                            'summary': summary[:200] if summary else "",
                            'link': link
                        })
                        
                        if len(all_news) >= max_items:
                            break
                    except Exception as e:
                        logger.debug(f"RSS 항목 파싱 실패: {e}")
                        continue
                
                if len(all_news) >= max_items:
                    break
                    
            except Exception as e:
                logger.debug(f"RSS 피드 수집 실패 ({rss_url}): {e}")
                continue
        
        news_items = all_news[:max_items]
        logger.info(f"Yahoo Finance RSS 뉴스 수집 완료: {len(news_items)}개")
        
    except Exception as e:
        logger.warning(f"Yahoo Finance RSS 뉴스 수집 실패: {e}")
    
    return news_items


def get_naver_finance_news(max_items: int = 10) -> List[Dict]:
    """
    네이버 금융에서 뉴스 제목과 요약문 수집
    
    Args:
        max_items: 최대 수집할 뉴스 개수
    
    Returns:
        [{"title": "...", "summary": "...", "link": "..."}, ...] 형태의 리스트
    """
    news_items = []
    try:
        url = "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258"
        logger.info(f"네이버 금융 뉴스 수집 중: {url}")
        
        response = _session.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        # 네이버 금융은 euc-kr 인코딩을 사용하므로 명시적으로 디코딩
        try:
            content = response.content.decode('euc-kr', 'replace')
        except (UnicodeDecodeError, AttributeError):
            # 디코딩 실패 시 기본 방식 사용
            content = response.text
        
        soup = BeautifulSoup(content, 'html.parser')
        
        # 네이버 금융 뉴스 구조 파싱
        article_list = soup.select('.articleList li, .articleSubject')
        
        found_items = []
        for article in article_list:
            try:
                # 제목 추출
                title_elem = article.select_one('dt a, .articleSubject a, a')
                if not title_elem:
                    continue
                
                title = title_elem.get_text(strip=True)
                link = title_elem.get('href', '')
                if link and not link.startswith('http'):
                    link = f"https://finance.naver.com{link}"
                
                # 요약문 추출 (dd 태그 또는 p 태그)
                summary_elem = article.select_one('dd, p, .summary')
                summary = summary_elem.get_text(strip=True) if summary_elem else ""
                
                if title and len(title) > 10:
                    found_items.append({
                        'title': title,
                        'summary': summary[:200] if summary else "",
                        'link': link
                    })
                    if len(found_items) >= max_items:
                        break
            except Exception as e:
                logger.debug(f"뉴스 항목 파싱 실패: {e}")
                continue
        
        news_items = found_items[:max_items]
        logger.info(f"네이버 금융 뉴스 수집 완료: {len(news_items)}개")
        
    except Exception as e:
        logger.warning(f"네이버 금융 뉴스 수집 실패: {e}")
    
    return news_items


def filter_relevant_news(news_items: List[Dict], max_items: int = 7) -> List[Dict]:
    """
    포트폴리오 집중형 Smart Filter: 내 종목 우선 필터링
    내 포트폴리오 종목(티커/기업명) 매칭 시 +5점, 일반 시장 키워드는 +2점
    
    Args:
        news_items: 뉴스 아이템 리스트
        max_items: 최종 선택할 뉴스 개수 (기본값: 7개)
    
    Returns:
        필터링된 뉴스 아이템 리스트 (가중치 순으로 정렬, 상위 max_items개)
    """
    # 포트폴리오 종목 정보 가져오기
    portfolio_tickers = []
    portfolio_names = {}
    
    if settings and hasattr(settings, 'tickers'):
        portfolio_tickers = settings.tickers
        
        # 티커를 기업명으로 매핑 (기본 매핑)
        # 티커 이름 매핑은 공통 모듈에서 가져오기
        from config.ticker_names import get_ticker_keywords
        
        # 포트폴리오 티커에 대한 기업명 수집
        for ticker in portfolio_tickers:
            keywords = get_ticker_keywords(ticker)
            if keywords:
                portfolio_names[ticker] = keywords
            else:
                # 기본 티커명도 추가 (대소문자 구분 없이)
                ticker_clean = ticker.replace('.KS', '').replace('.KQ', '').replace('-USD', '')
                if ticker_clean not in portfolio_names:
                    portfolio_names[ticker] = [ticker_clean.lower()]
    
    # 일반 시장 키워드 (가중치 +2점)
    market_keywords = [
            'fed', 'federal reserve', 'interest rate', 'cpi', 'inflation', 'unemployment',
        'treasury', 'bond', 'yield', 'rate', 'gdp', 'employment',
        'gold', 'silver', 'oil', 'crude', 'energy',
        's&p', 'sp500', 'nasdaq', 'dow', 'kospi', 'kosdaq',
        'ai', 'artificial intelligence', 'tech', 'technology', 'semiconductor', 'chip'
    ]
    
    scored_news = []
    for news in news_items:
        title_lower = news['title'].lower()
        summary_lower = news.get('summary', '').lower()
        combined_text = f"{title_lower} {summary_lower}"
        
        # 가중치 계산
        score = 0
        matched_keywords = []
        
        # 1. 내 포트폴리오 종목 매칭 (+5점)
        portfolio_matched = False
        for ticker, names in portfolio_names.items():
            # 티커 자체 매칭 (단어 경계 고려)
            ticker_clean = ticker.replace('.KS', '').replace('.KQ', '').replace('-USD', '')
            if re.search(r'\b' + re.escape(ticker_clean) + r'\b', combined_text, re.IGNORECASE):
                score += 5
                matched_keywords.append(f"포트폴리오:{ticker_clean}")
                portfolio_matched = True
                break
            
            # 기업명 매칭
            for name in names:
                if name.lower() in combined_text:
                    score += 5
                    matched_keywords.append(f"포트폴리오:{name}")
                    portfolio_matched = True
                    break
            
            if portfolio_matched:
                break
        
        # 2. 일반 시장 키워드 매칭 (+2점)
        for keyword in market_keywords:
            if keyword.lower() in combined_text:
                score += 2
                matched_keywords.append(keyword)
                break  # 첫 매칭만 카운트
        
        # 최소 점수 이상만 포함
        if score >= 2:  # 최소 2점 이상
            scored_news.append({
                'news': news,
                'score': score,
                'keywords': matched_keywords
            })
        else:
            logger.debug(f"필터링됨 (점수 부족: {score}): {news['title'][:50]}")
    
    # 가중치 순으로 정렬 (높은 점수 우선)
    scored_news.sort(key=lambda x: x['score'], reverse=True)
    
    # 상위 max_items개만 선택
    filtered_news = [item['news'] for item in scored_news[:max_items]]
    
    logger.info(f"뉴스 필터링: {len(news_items)}개 -> {len(filtered_news)}개 (포트폴리오 집중형, 상위 {max_items}개)")
    if scored_news:
        logger.debug(f"상위 3개 뉴스 점수: {[item['score'] for item in scored_news[:3]]}")
        logger.debug(f"상위 3개 뉴스 키워드: {[item['keywords'] for item in scored_news[:3]]}")
    
    return filtered_news


def get_market_news_with_context(max_items: int = 10) -> str:
    """
    뉴스 제목과 요약문을 함께 수집하여 포맷팅된 텍스트로 반환
    포트폴리오 관련 뉴스만 필터링
    
    Args:
        max_items: 최대 수집할 뉴스 개수
    
    Returns:
        포맷팅된 뉴스 텍스트
    """
    logger.info("=== 시장 뉴스 수집 시작 (제목+요약, 필터링 적용) ===")
    
    all_news = []
    
    # Yahoo Finance 수집
    yahoo_news = get_yahoo_finance_news(max_items=max_items * 2)  # 필터링을 위해 더 많이 수집
    if yahoo_news:
        all_news.extend(yahoo_news)
    
    # 네이버 금융 수집
    naver_news = get_naver_finance_news(max_items=max_items * 2)
    if naver_news:
        all_news.extend(naver_news)
    
    # 포트폴리오 관련 뉴스만 필터링 (Smart Filter: 내 종목 우선)
    filtered_news = filter_relevant_news(all_news, max_items=max_items)
    
    # 중복 제거 (제목 기준)
    unique_news = []
    seen_titles = set()
    for news in filtered_news:
        title_lower = news['title'].lower().strip()
        if title_lower not in seen_titles and len(news['title']) > 10:
            seen_titles.add(title_lower)
            unique_news.append(news)
            if len(unique_news) >= max_items:
                break
    
    # 텍스트 포맷팅
    if unique_news:
        result = "**주요 시장 뉴스 (제목+요약):**\n\n"
        for i, news in enumerate(unique_news, 1):
            result += f"{i}. <b>{news['title']}</b>\n"
            if news['summary']:
                result += f"   요약: {news['summary']}\n"
            result += "\n"
        logger.info(f"뉴스 수집 완료: {len(unique_news)}개 (제목+요약, 필터링 적용)")
    else:
        result = "**주요 시장 뉴스:**\n뉴스 데이터 수집 불가 (크롤링 실패 또는 네트워크 오류)"
        logger.warning("뉴스 수집 실패: 모든 소스에서 데이터를 가져올 수 없음")
    
    return result


def get_hot_news(overseas_count: int = 10, domestic_count: int = 10) -> str:
    """
    해외시장과 국내시장에서 각각 Hot/인기 뉴스 수집 (포트폴리오 필터링 없음)
    포트폴리오와 무관하지만 현재 화두가 되고 있는 뉴스를 수집하여 분석의 폭과 시야를 넓히는 것이 목적
    
    Args:
        overseas_count: 해외시장 뉴스 개수 (기본값: 10개)
        domestic_count: 국내시장 뉴스 개수 (기본값: 10개)
    
    Returns:
        포맷팅된 Hot 뉴스 텍스트
    """
    logger.info("=== Hot/인기 뉴스 수집 시작 (포트폴리오 필터링 없음) ===")
    
    result_parts = []
    selected_overseas = []
    selected_domestic = []
    
    # 1. 해외시장 Hot 뉴스 수집 (RSS 피드 기반 또는 대안 방법)
    try:
        logger.info(f"해외시장 Hot 뉴스 수집 중 (목표: {overseas_count}개, 포트폴리오 무관)...")
        
        selected_overseas = []
        
        # 방법 1: RSS 피드를 사용한 해외 뉴스 수집 (Bloomberg, CNBC 등)
        if FEEDPARSER_AVAILABLE:
            # 글로벌 RSS 피드에서 수집
            rss_news_list = get_global_rss_news(max_items_per_source=overseas_count // 3 + 1)
            
            # RSS 뉴스를 Dict 형태로 변환
            for news_item in rss_news_list[:overseas_count]:
                # "[Bloomberg] 제목 | 요약" 또는 "[Bloomberg] 제목" 형식을 파싱
                if '] ' in news_item:
                    source_part, rest = news_item.split('] ', 1)
                    source = source_part.replace('[', '').strip()
                    
                    # summary가 있는지 확인 (| 구분자)
                    if ' | ' in rest:
                        title, summary = rest.split(' | ', 1)
                        selected_overseas.append({
                            'title': title.strip(),
                            'summary': summary.strip()[:200],  # 최대 200자
                            'link': '',
                            'publisher': source
                        })
                    else:
                        selected_overseas.append({
                            'title': rest.strip(),
                            'summary': '',
                            'link': '',
                            'publisher': source
                        })
                else:
                    selected_overseas.append({
                        'title': news_item.strip(),
                        'summary': '',
                        'link': '',
                        'publisher': 'RSS Feed'
                    })
        
        # 방법 2: feedparser가 없으면 Yahoo Finance RSS 시도
        if not selected_overseas:
            overseas_news = get_yahoo_finance_news(max_items=overseas_count)
            selected_overseas = overseas_news if overseas_news else []
        
        # 방법 3: 여전히 부족하면 yfinance로 일반 시장 뉴스 수집 (티커 기반이지만 다양한 티커 사용)
        if len(selected_overseas) < overseas_count:
            logger.info(f"RSS 수집 부족 ({len(selected_overseas)}개), yfinance로 보완 시도...")
            try:
                # 다양한 시장 지수와 섹터 티커 사용 (포트폴리오 무관)
                market_tickers = ['^GSPC', '^DJI', '^IXIC', '^VIX', '^TNX', 'GC=F', 'CL=F']
                seen_titles = {item['title'].lower() for item in selected_overseas}
                
                for ticker in market_tickers:
                    try:
                        ticker_obj = yf.Ticker(ticker)
                        news_list = ticker_obj.news
                        
                        if not news_list:
                            continue
                        
                        for news_item in news_list[:3]:  # 각 티커당 최대 3개
                            try:
                                content = news_item.get('content', {})
                                title = content.get('title', '') if isinstance(content, dict) else ''
                                summary = content.get('summary', '') if isinstance(content, dict) else ''
                                canonical_url = news_item.get('canonicalUrl', {})
                                link = canonical_url.get('url', '') if isinstance(canonical_url, dict) else ''
                                
                                if not title or len(title) < 20:
                                    continue
                                
                                title_lower = title.lower().strip()
                                if title_lower in seen_titles:
                                    continue
                                seen_titles.add(title_lower)
                                
                                selected_overseas.append({
                                    'title': title,
                                    'summary': summary[:200] if summary else "",
                                    'link': link
                                })
                                
                                if len(selected_overseas) >= overseas_count:
                                    break
                            except:
                                continue
                        
                        if len(selected_overseas) >= overseas_count:
                            break
                    except:
                        continue
            except Exception as e:
                logger.debug(f"yfinance 보완 수집 실패: {e}")
        
        if selected_overseas:
            result_parts.append("**🌎 해외시장 Hot 뉴스:**\n")
            for i, news in enumerate(selected_overseas, 1):
                result_parts.append(f"{i}. <b>{news['title']}</b>")
                if news.get('summary'):
                    result_parts.append(f"   요약: {news['summary']}")
                result_parts.append("")
            logger.info(f"해외시장 Hot 뉴스 수집 완료: {len(selected_overseas)}개")
        else:
            result_parts.append("**🌎 해외시장 Hot 뉴스:**\n뉴스 데이터 수집 불가")
            logger.warning("해외시장 Hot 뉴스 수집 실패")
    except Exception as e:
        logger.warning(f"해외시장 Hot 뉴스 수집 실패: {e}")
        result_parts.append("**🌎 해외시장 Hot 뉴스:**\n뉴스 데이터 수집 실패")
    
    result_parts.append("\n")
    
    # 2. 국내시장 Hot 뉴스 수집 (네이버 금융)
    try:
        logger.info(f"국내시장 Hot 뉴스 수집 중 (목표: {domestic_count}개, 포트폴리오 무관)...")
        # 네이버 금융에서 인기 뉴스 수집 (필터링 없이)
        domestic_news = get_naver_finance_news(max_items=domestic_count)
        
        # 수집된 뉴스 그대로 사용 (필터링 없이, 이미 상위 뉴스)
        selected_domestic = domestic_news if domestic_news else []
        
        if selected_domestic:
            result_parts.append("**🇰🇷 국내시장 Hot 뉴스:**\n")
            for i, news in enumerate(selected_domestic, 1):
                result_parts.append(f"{i}. <b>{news['title']}</b>")
                if news.get('summary'):
                    result_parts.append(f"   요약: {news['summary']}")
                result_parts.append("")
            logger.info(f"국내시장 Hot 뉴스 수집 완료: {len(selected_domestic)}개")
        else:
            result_parts.append("**🇰🇷 국내시장 Hot 뉴스:**\n뉴스 데이터 수집 불가")
            logger.warning("국내시장 Hot 뉴스 수집 실패")
    except Exception as e:
        logger.warning(f"국내시장 Hot 뉴스 수집 실패: {e}")
        result_parts.append("**🇰🇷 국내시장 Hot 뉴스:**\n뉴스 데이터 수집 실패")
    
    result = "\n".join(result_parts)
    total_count = len(selected_overseas) + len(selected_domestic)
    logger.info(f"Hot 뉴스 수집 완료: 총 {total_count}개 (해외 {len(selected_overseas)}개, 국내 {len(selected_domestic)}개)")
    
    return result


def get_fred_macro_data() -> str:
    """
    FRED API를 사용하여 연준 데이터 수집 (Macro Intelligence)
    
    Returns:
        포맷팅된 FRED 매크로 데이터 텍스트
    """
    logger.info("=== FRED API 매크로 데이터 수집 시작 ===")
    
    if Fred is None:
        logger.warning("fredapi 라이브러리가 없어 FRED 데이터를 수집할 수 없습니다.")
        logger.info("💡 FRED 데이터 수집을 원하시면 다음 명령어로 설치하세요: pip install fredapi")
        return "[MACRO DATA (Source: Federal Reserve FRED)]\n⚠️ FRED API 라이브러리(fredapi) 미설치 - yfinance 기반 지표로 대체됨"
    
    try:
        # FRED API Key (환경변수 또는 기본값)
        fred_api_key = os.getenv('FRED_API_KEY', '963732203fa6b98976f41d4b979c18e6')
        fred = Fred(api_key=fred_api_key)
        
        # 수집 대상 시리즈
        fred_series = {
            'DGS10': {
                'name': 'US 10Y Treasury',
                'description': 'Risk-Free Rate',
                'format': 'percent'
            },
            'T10Y2Y': {
                'name': 'Yield Curve (10Y-2Y)',
                'description': 'Recession Signal',
                'format': 'decimal'
            },
            'BAMLH0A0HYM2': {
                'name': 'High Yield Spread',
                'description': 'Credit Risk',
                'format': 'percent'
            },
            'T10YIE': {
                'name': 'Inflation Expectation',
                'description': 'Breakeven Inflation Rate',
                'format': 'percent'
            }
        }
        
        indicators = []
        
        for series_id, config in fred_series.items():
            try:
                # 최신 데이터 조회
                data = fred.get_series(series_id, limit=1)
                
                if data is not None and len(data) > 0:
                    latest_date = data.index[-1]
                    latest_value = float(data.iloc[-1])
                    
                    # 포맷팅
                    if config['format'] == 'percent':
                        if series_id == 'DGS10':
                            value_str = f"{latest_value:.2f}%"
                        elif series_id == 'BAMLH0A0HYM2':
                            value_str = f"{latest_value:.2f}%"
                        elif series_id == 'T10YIE':
                            value_str = f"{latest_value:.1f}%"
                        else:
                            value_str = f"{latest_value:.2f}%"
                    else:
                        value_str = f"{latest_value:.2f}"
                    
                    # 경고 메시지 추가
                    warning = ""
                    if series_id == 'T10Y2Y' and latest_value < 0:
                        warning = " (Recession Signal Warning!)"
                    elif series_id == 'BAMLH0A0HYM2' and latest_value > 4:
                        warning = " (Credit Risk High)"
                    
                    indicators.append(f"- {config['name']}: {value_str} ({config['description']}{warning})")
                    logger.info(f"FRED {config['name']} 수집 완료: {value_str}")
                else:
                    indicators.append(f"- {config['name']}: N/A")
                    logger.warning(f"FRED {series_id} 데이터 없음")
            except Exception as e:
                logger.warning(f"FRED {series_id} 수집 실패: {e}")
                indicators.append(f"- {config['name']}: N/A")
        
        if indicators:
            result = "[MACRO DATA (Source: Federal Reserve FRED)]\n" + "\n".join(indicators)
            logger.info(f"FRED 매크로 데이터 수집 완료: {len(indicators)}개")
            return result
        else:
            return "[MACRO DATA (Source: Federal Reserve FRED)]\n데이터 수집 실패"
            
    except Exception as e:
        logger.error(f"FRED API 수집 실패: {e}")
        return "[MACRO DATA (Source: Federal Reserve FRED)]\n데이터 수집 실패"


def get_market_indicators() -> str:
    """
    매크로 경제 지표 수집 (FRED API + yfinance + 공포/탐욕 지수)
    
    Returns:
        포맷팅된 매크로 지표 텍스트
    """
    logger.info("=== 매크로 경제 지표 수집 시작 ===")
    
    # Part A: FRED API 데이터 (우선)
    fred_data = get_fred_macro_data()
    
    indicators = []
    vix_value = None  # VIX 값을 저장하여 공포/탐욕 지수 계산에 사용
    
    # Part B: yfinance로 수집 가능한 지표들 (FRED 의존성 제거)
    macro_tickers = {
        '^TNX': 'US 10Y Treasury',  # FRED DGS10 대체
        'CL=F': 'WTI 원유',
        'GC=F': '금 선물',
        '^VIX': 'VIX 변동성 지수',
        'KRW=X': 'USD/KRW 환율',
    }
    
    for ticker, name in macro_tickers.items():
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # 현재가 조회
            current_price = None
            if 'regularMarketPrice' in info:
                current_price = info['regularMarketPrice']
            elif 'previousClose' in info:
                current_price = info['previousClose']
            else:
                # history로 최신 가격 가져오기
                hist = stock.history(period="1d")
                if not hist.empty:
                    current_price = float(hist['Close'].iloc[-1])
            
            # 등락률 계산 (전일 대비)
            change_pct = None
            if 'regularMarketChangePercent' in info:
                change_pct = info['regularMarketChangePercent']
            elif 'previousClose' in info and current_price:
                prev_close = info['previousClose']
                if prev_close and prev_close > 0:
                    change_pct = ((current_price - prev_close) / prev_close) * 100
            
            if current_price:
                # 포맷팅
                if ticker == 'KRW=X':
                    price_str = f"{current_price:,.0f}"
                elif ticker == '^TNX':
                    # 10년물 국채는 퍼센트로 표시 (yfinance는 이미 퍼센트 단위)
                    price_str = f"{current_price:.2f}%"
                elif ticker in ['CL=F', 'GC=F']:
                    price_str = f"${current_price:.2f}"
                else:
                    price_str = f"{current_price:.2f}"
                
                change_str = ""
                if change_pct is not None:
                    sign = "+" if change_pct >= 0 else ""
                    change_str = f" ({sign}{change_pct:.2f}%)"
                
                indicators.append(f"- {name}: {price_str}{change_str}")
                logger.info(f"{name} 수집 완료: {price_str}{change_str}")
                
                # VIX 값 저장 (공포/탐욕 지수 계산에 사용)
                if ticker == '^VIX' and current_price:
                    vix_value = current_price
        except Exception as e:
            logger.warning(f"{name} ({ticker}) 수집 실패: {e}")
            indicators.append(f"- {name}: N/A")
    
    # Part C: 공포/탐욕 지수 (Fear & Greed Index)
    fear_greed = get_fear_greed_index(vix_value)
    if fear_greed:
        indicators.append(fear_greed.replace("**", ""))
    
    # 결과 포맷팅 (FRED 데이터 + 추가 지표)
    if indicators:
        additional_indicators = "\n".join(indicators)
        result = f"{fred_data}\n\n{additional_indicators}"
        logger.info(f"매크로 지표 수집 완료: FRED + {len(indicators)}개 추가")
    else:
        result = fred_data
        logger.info("매크로 지표 수집 완료: FRED 데이터만")
    
    return result


def get_fear_greed_index(vix_value: Optional[float] = None) -> Optional[str]:
    """
    공포/탐욕 지수 (Fear & Greed Index) CNN API에서 직접 획득
    CNN API 실패 시 자체 계산으로 Fallback
    
    Args:
        vix_value: VIX 변동성 지수 값 (fallback 계산용)
    
    Returns:
        포맷팅된 공포/탐욕 지수 문자열
    """
    logger.info("공포/탐욕 지수 CNN API에서 직접 획득 시도...")
    
    # CNN API 직접 호출 시도
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'Referer': 'https://edition.cnn.com/markets/fear-and-greed',
            'Accept': 'application/json, text/plain, */*'
        }
        
        response = _session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # fear_and_greed 객체에서 score 추출
        if 'fear_and_greed' in data:
            fng_data = data['fear_and_greed']
            score = fng_data.get('score')
            rating = fng_data.get('rating', 'neutral')
            
            if score is not None:
                score = float(score)
                
                # 분류 및 이모지
                if score <= 25:
                    classification = "Extreme Fear"
                    emoji = "😨"
                elif score <= 45:
                    classification = "Fear"
                    emoji = "😟"
                elif score <= 55:
                    classification = "Neutral"
                    emoji = "😐"
                elif score <= 75:
                    classification = "Greed"
                    emoji = "😊"
                else:
                    classification = "Extreme Greed"
                    emoji = "🚀"
                
                result = f"- 공포/탐욕 지수: {int(score)} ({classification}) {emoji} (CNN 공식)"
                logger.info(f"✅ CNN API에서 공포/탐욕 지수 획득 성공: {int(score)} ({classification})")
            return result
    except Exception as e:
        logger.warning(f"CNN API 호출 실패, 자체 계산으로 Fallback: {e}")
    
    # Fallback: 자체 계산
    logger.info("공포/탐욕 지수 자체 계산 중...")
    
    # VIX 값이 없으면 yfinance로 조회
    if vix_value is None:
        try:
            vix_ticker = yf.Ticker('^VIX')
            vix_info = vix_ticker.info
            if 'regularMarketPrice' in vix_info:
                vix_value = vix_info['regularMarketPrice']
            else:
                vix_hist = vix_ticker.history(period="1d")
                if not vix_hist.empty:
                    vix_value = float(vix_hist['Close'].iloc[-1])
        except Exception as e:
            logger.warning(f"VIX 조회 실패: {e}")
            return None
    
    # 시장 대표 RSI 계산 (S&P500) - Wilder's Smoothing 방식 사용
    market_rsi = None
    try:
        spy_ticker = yf.Ticker('SPY')
        spy_hist = spy_ticker.history(period="3mo", auto_adjust=True)
        
        if not spy_hist.empty and len(spy_hist) > 14:
            # Wilder's Smoothing 방식으로 RSI 계산
            close = spy_hist['Close']
            delta = close.diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            
            # Wilder's Smoothing (RMA)
            period = 14
            avg_gain = pd.Series(index=close.index, dtype=float)
            avg_loss = pd.Series(index=close.index, dtype=float)
            avg_gain.iloc[period] = gain.iloc[1:period+1].mean()
            avg_loss.iloc[period] = loss.iloc[1:period+1].mean()
            
            for i in range(period + 1, len(close)):
                avg_gain.iloc[i] = (avg_gain.iloc[i-1] * (period - 1) + gain.iloc[i]) / period
                avg_loss.iloc[i] = (avg_loss.iloc[i-1] * (period - 1) + loss.iloc[i]) / period
            
            rs = avg_gain / (avg_loss + 1e-10)
            rsi = 100 - (100 / (1 + rs))
            market_rsi = float(rsi.iloc[-1])
            logger.info(f"S&P500 RSI 계산 완료 (Wilder's): {market_rsi:.2f}")
    except Exception as e:
        logger.warning(f"S&P500 RSI 계산 실패: {e}")
    
    # 공포/탐욕 지수 계산 (개선된 버전)
    # CNN Fear & Greed Index는 7개 지표를 동등 가중치로 평균합니다.
    # 현재는 VIX와 RSI만 사용 가능하므로, 나머지 5개 지표를 중립(50)으로 가정합니다.
    # 공식: (VIX_정규화 + RSI_조정 + 50*5) / 7
    try:
        # VIX 정규화 개선: 동적 범위 사용 (고정 범위 5-50 대신)
        # VIX는 일반적으로 10-30 범위, 극단적으로 5-80까지 가능
        # 최근 1년 데이터 기반 백분위수 사용 (없으면 고정 범위 사용)
        try:
            vix_ticker = yf.Ticker('^VIX')
            vix_hist = vix_ticker.history(period="1y")
            if not vix_hist.empty and len(vix_hist) > 20:
                vix_values = vix_hist['Close']
                vix_min = vix_values.quantile(0.05)  # 5% 백분위수
                vix_max = vix_values.quantile(0.95)  # 95% 백분위수
                # 안전장치: 범위가 너무 좁으면 고정 범위 사용
                if vix_max - vix_min < 10:
                    vix_min, vix_max = 5, 50
            else:
                vix_min, vix_max = 5, 50
        except:
            # 백분위수 계산 실패 시 고정 범위 사용
            vix_min, vix_max = 5, 50
        
        # VIX 정규화: VIX가 낮을수록 탐욕 (높은 점수)
        # 공식: (vix_max - VIX) / (vix_max - vix_min) * 100
        vix_range = vix_max - vix_min
        if vix_range > 0:
            vix_normalized = max(0, min(100, (vix_max - vix_value) / vix_range * 100))
        else:
            vix_normalized = 50  # 범위가 0이면 중립
        
        # RSI 조정 개선: 0.5 배수 제거 (RSI는 이미 0-100 범위)
        # RSI가 높을수록 탐욕이므로 그대로 사용
        if market_rsi is not None:
            rsi_adjusted = market_rsi  # 조정 없이 그대로 사용
        else:
            rsi_adjusted = 50  # RSI 계산 실패 시 중립으로 처리
        
        # 7개 지표 평균 (VIX, RSI + 나머지 5개를 중립 50으로 가정)
        calculated_value = (vix_normalized + rsi_adjusted + 50 * 5) / 7
        calculated_value = max(0, min(100, calculated_value))  # 0~100 범위로 제한
        
        # 분류 및 이모지
        if calculated_value <= 25:
            classification = "Extreme Fear"
            emoji = "😨"
        elif calculated_value <= 45:
            classification = "Fear"
            emoji = "😟"
        elif calculated_value <= 55:
            classification = "Neutral"
            emoji = "😐"
        elif calculated_value <= 75:
            classification = "Greed"
            emoji = "😊"
        else:
            classification = "Extreme Greed"
            emoji = "🚀"
        
        # 계산 상세 정보 포함
        calc_detail = f"VIX: {vix_value:.2f} (범위: {vix_min:.1f}-{vix_max:.1f}, 정규화: {vix_normalized:.1f})"
        if market_rsi is not None:
            calc_detail += f", S&P500 RSI: {market_rsi:.1f}"
        
        result = f"- 공포/탐욕 지수: {int(calculated_value)} ({classification}) {emoji} (자체 계산: {calc_detail})"
        rsi_str = f"{market_rsi:.1f}" if market_rsi is not None else "N/A"
        logger.info(f"공포/탐욕 지수 자체 계산 완료: {int(calculated_value)} ({classification}) - VIX: {vix_value:.2f}, RSI: {rsi_str}")
        return result
    except Exception as e:
        logger.error(f"공포/탐욕 지수 계산 실패: {e}")
    return None


    """
    Yahoo Finance Economic Calendar에서 오늘부터 향후 3일간의 중요 경제 지표 수집
    Investing.com 대신 Yahoo Finance 사용 (봇 차단 우회)
    
    Args:
        max_retries: 최대 재시도 횟수
    
    Returns:
        포맷팅된 경제 캘린더 텍스트
    """
    logger.info("=== 경제 캘린더 수집 시작 (Yahoo Finance) ===")
    print("=== 경제 캘린더 수집 시작 (Yahoo Finance) ===")
    
    today = datetime.now()
    end_date = today + timedelta(days=3)  # 오늘부터 3일간
    
    # 재시도 로직
    for attempt in range(max_retries):
        try:
            # Yahoo Finance Economic Calendar
            url = "https://finance.yahoo.com/calendar/economic"
            
            logger.info(f"경제 캘린더 수집 중 (시도 {attempt + 1}/{max_retries}): {url}")
            print(f"경제 캘린더 수집 중 (시도 {attempt + 1}/{max_retries}): {url}")
            
            # 재시도 시 대기 시간
            if attempt > 0:
                wait_time = 2 ** attempt
                logger.info(f"⏳ {wait_time}초 대기 후 재시도...")
                print(f"⏳ {wait_time}초 대기 후 재시도...")
                time.sleep(wait_time)
            
            response = _session.get(url, headers=HEADERS, timeout=15)
            
            # Status Code 로그
            status_code = response.status_code
            logger.info(f"HTTP Status Code: {status_code}")
            print(f"HTTP Status Code: {status_code}")
            
            if status_code != 200:
                logger.warning(f"HTTP Status Code가 200이 아님: {status_code}")
                print(f"⚠️ HTTP Status Code가 200이 아님: {status_code}")
                if attempt < max_retries - 1:
                    continue
            
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # HTML 크기 로그
            html_size = len(response.content)
            logger.info(f"HTML 크기: {html_size} bytes")
            print(f"HTML 크기: {html_size} bytes")
            
            # 경제 캘린더 이벤트 파싱
            events = []
            
            # 허용할 국가 코드 (포트폴리오와 관련된 국가만)
            ALLOWED_COUNTRIES = {'US', 'KR', 'CN', 'EU', 'GB', 'JP'}  # 미국, 한국, 중국, 유럽, 영국, 일본
            
            # Yahoo Finance의 경제 캘린더 구조 파싱
            # 여러 가능한 선택자 시도
            event_selectors = [
                'table[data-test="economic-calendar"] tbody tr',
                'table tbody tr[data-test="economic-calendar-row"]',
                'table tbody tr',
                '[data-module="EconomicCalendar"] tbody tr',
                '.economic-calendar tbody tr'
            ]
            
            found_items_count = 0
            for selector in event_selectors:
                event_rows = soup.select(selector)
                found_items_count = len(event_rows)
                logger.info(f"선택자 '{selector}': {found_items_count}개 항목 발견")
                print(f"선택자 '{selector}': {found_items_count}개 항목 발견")
                
                if event_rows:
                    for row in event_rows[:50]:  # 더 많이 확인 (3일치 데이터)
                        try:
                            # 모든 td 요소 추출하여 정확한 매핑 확인
                            tds = row.select('td')
                            if len(tds) < 3:
                                continue
                            
                            # 컬럼 매핑 재확인 (디버깅을 위해 각 td 내용 로깅)
                            td_texts = [td.get_text(strip=True) for td in tds]
                            
                            # 디버깅: 첫 5개 행만 상세 로깅
                            if len(events) < 5:
                                logger.debug(f"TD 컬럼들: {td_texts}")
                            
                            # 국가 코드 추출 (보통 2-3자리 코드)
                            country = ""
                            country_idx = -1
                            for idx, td_text in enumerate(td_texts):
                                # 국가 코드 패턴 확인 (2-3자 대문자, 또는 국가명)
                                if len(td_text) in [2, 3] and td_text.isupper() and td_text.isalpha():
                                    # ALLOWED_COUNTRIES에 있는지 확인
                                    if td_text in ALLOWED_COUNTRIES:
                                        country = td_text
                                        country_idx = idx
                                        break
                            
                            # 국가 필터링: 허용된 국가만 추출
                            if not country or country not in ALLOWED_COUNTRIES:
                                continue
                            
                            # 이벤트명 추출 (보통 국가 다음 컬럼 또는 가장 긴 텍스트)
                            event_name = ""
                            
                            # 국가 다음 컬럼이 이벤트명일 가능성
                            if country_idx + 1 < len(td_texts):
                                candidate = td_texts[country_idx + 1]
                                # 시간 패턴이 아니고, 너무 짧지 않으면 이벤트명으로 간주
                                if len(candidate) >= 5 and ':' not in candidate and not candidate.replace('.', '').isdigit():
                                    event_name = candidate
                            
                            # 이벤트명을 찾지 못한 경우, 가장 긴 텍스트를 이벤트명으로 사용
                            if not event_name or len(event_name) < 5:
                                # 시간 패턴이 아닌 가장 긴 텍스트 찾기
                                for td_text in td_texts:
                                    if len(td_text) > len(event_name) and ':' not in td_text and td_text != country:
                                        if not td_text.replace('.', '').replace('/', '').isdigit():
                                            event_name = td_text
                            
                            if not event_name or len(event_name) < 5:
                                continue
                            
                            # 날짜/시간 추출
                            event_date_str = ""
                            event_time = ""
                            
                            # 날짜 패턴 찾기 (MM/DD 또는 YYYY-MM-DD 형식)
                            for td_text in td_texts:
                                if ('/' in td_text or '-' in td_text) and len(td_text) >= 5:
                                    # 숫자와 구분자로만 구성된 경우 날짜로 간주
                                    if any(c.isdigit() for c in td_text):
                                        event_date_str = td_text
                                        break
                            
                            # 시간 패턴 찾기 (HH:MM 형식, UTC, EST 등 포함)
                            for td_text in td_texts:
                                if ':' in td_text and ('AM' in td_text or 'PM' in td_text or 'UTC' in td_text or 'EST' in td_text):
                                    event_time = td_text
                                    break
                                elif ':' in td_text and len(td_text) <= 8:  # HH:MM 형식
                                    parts = td_text.split(':')
                                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                                        event_time = td_text
                                        break
                            
                            # 중요도 추출 (별표 또는 High/Medium/Low 텍스트)
                            importance = 2  # 기본값
                            for td_text in td_texts:
                                td_lower = td_text.lower()
                                if 'high' in td_lower or '⭐' in td_text or '★' in td_text:
                                    importance = 3
                                    break
                                elif 'medium' in td_lower:
                                    importance = 2
                                elif 'low' in td_lower:
                                    importance = 1
                            
                            # 중요도 필터: US는 별 2개 이상, 다른 국가는 별 3개만
                            if country == 'US' and importance >= 2:
                                pass  # US는 중요도 2 이상 허용
                            elif country != 'US' and importance < 3:
                                continue  # 다른 국가는 중요도 3만 허용
                            
                            events.append({
                                'name': event_name,
                                'time': event_time,
                                'country': country,
                                'importance': importance,
                                'date': event_date_str
                            })
                            
                            logger.debug(f"추출된 이벤트: {event_name} ({country}), 중요도: {importance}, 날짜: {event_date_str}, 시간: {event_time}")
                            
                        except Exception as e:
                            logger.debug(f"경제 캘린더 이벤트 파싱 실패: {e}")
                            continue
                    
                    if events:
                        break
            
            # Found items count 로그
            logger.info(f"총 발견된 이벤트: {len(events)}개")
            print(f"총 발견된 이벤트: {len(events)}개")
            
            if len(events) == 0:
                logger.warning("경제 캘린더 항목이 0개입니다. HTML 구조가 변경되었을 가능성이 있습니다.")
                print("⚠️ 경제 캘린더 항목이 0개입니다. HTML 구조가 변경되었을 가능성이 있습니다.")
            
            # 중복 제거 (이벤트명 기준)
            unique_events = []
            seen_names = set()
            for event in events:
                name_lower = event['name'].lower()
                if name_lower not in seen_names:
                    seen_names.add(name_lower)
                    unique_events.append(event)
            
            if unique_events:
                # 국가별로 그룹화하여 정렬
                country_order = {'US': 1, 'KR': 2, 'CN': 3, 'EU': 4, 'GB': 5, 'JP': 6}
                unique_events.sort(key=lambda x: (country_order.get(x['country'], 99), -x['importance']))
                
                result = "**📅 오늘부터 향후 3일간 중요 경제 지표 일정 (주요 국가):**\n\n"
                for i, event in enumerate(unique_events[:10], 1):  # 최대 10개
                    stars = "⭐" * min(event['importance'], 3)
                    country_name = {'US': '🇺🇸 미국', 'KR': '🇰🇷 한국', 'CN': '🇨🇳 중국', 'EU': '🇪🇺 유럽', 'GB': '🇬🇧 영국', 'JP': '🇯🇵 일본'}.get(event['country'], event['country'])
                    result += f"{i}. {stars} <b>{event['name']}</b> ({country_name})\n"
                    if event['date']:
                        result += f"   📅 날짜: {event['date']}\n"
                    if event['time']:
                        result += f"   ⏰ 시간: {event['time']}\n"
                    result += "\n"
                logger.info(f"경제 캘린더 수집 완료: {len(unique_events)}개 이벤트 (필터링 후)")
                print(f"✅ 경제 캘린더 수집 완료: {len(unique_events)}개 이벤트 (필터링 후)")
                return result
            else:
                result = "**📅 경제 캘린더:**\n예정된 주요 경제 지표 없음 (오늘부터 향후 3일간)"
                logger.info("경제 캘린더: 중요 이벤트 없음")
                print("경제 캘린더: 중요 이벤트 없음")
                return result
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"경제 캘린더 수집 실패 (시도 {attempt + 1}/{max_retries}): {e}")
            print(f"❌ 경제 캘린더 수집 실패 (시도 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                continue
        except Exception as e:
            logger.warning(f"경제 캘린더 파싱 실패 (시도 {attempt + 1}/{max_retries}): {e}")
            print(f"❌ 경제 캘린더 파싱 실패 (시도 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                continue
    
    # 모든 시도 실패
    logger.warning("Yahoo Finance 경제 캘린더 크롤링 실패 (모든 시도 실패)")
    print("❌ Yahoo Finance 경제 캘린더 크롤링 실패 (모든 시도 실패)")
    return "**📅 경제 캘린더:**\n데이터 수집 실패 (모든 소스 실패)"


def get_us_top_movers(max_items: int = 10) -> str:
    """
    미국 시장의 실시간 Top Movers (급등주) 수집
    나스닥 100 및 S&P 500 구성 종목 중 등락률 상위 종목 추출
    
    Args:
        max_items: 최대 수집할 종목 개수
    
    Returns:
        포맷팅된 Top Movers 텍스트
    """
    logger.info("=== 미국 Top Movers 수집 시작 ===")
    print("=== 미국 Top Movers 수집 시작 ===")
    
    top_movers = []
    
    try:
        # 방법 1: Yahoo Finance Top Gainers 페이지 크롤링
        url = "https://finance.yahoo.com/gainers"
        logger.info(f"Yahoo Finance Top Gainers 수집 중: {url}")
        
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 테이블에서 종목 정보 추출
        table_rows = soup.select('table tbody tr')
        
        for row in table_rows[:max_items * 2]:  # 여유 있게 가져오기
            try:
                tds = row.select('td')
                if len(tds) < 4:
                    continue
                
                # 티커 추출 (보통 첫 번째 컬럼)
                ticker_elem = tds[0].select_one('a')
                if not ticker_elem:
                    continue
                
                ticker = ticker_elem.get_text(strip=True)
                ticker_link = ticker_elem.get('href', '')
                
                # 종목명 추출 (보통 두 번째 컬럼)
                name = tds[1].get_text(strip=True) if len(tds) > 1 else ""
                
                # 등락률 추출
                change_pct_text = ""
                for td in tds:
                    td_text = td.get_text(strip=True)
                    if '%' in td_text and ('+' in td_text or '-' in td_text):
                        change_pct_text = td_text
                        break
                
                # 가격 추출
                price_text = ""
                for td in tds:
                    td_text = td.get_text(strip=True)
                    if '$' in td_text and '.' in td_text:
                        # 가격 패턴 확인
                        try:
                            float(td_text.replace('$', '').replace(',', ''))
                            price_text = td_text
                            break
                        except ValueError:
                            continue
                # 필터링: 나스닥 100 또는 S&P 500 구성 종목만 (잡주 제외)
                # 시가총액이 큰 종목만 필터링하기 위해 가격이 $5 이상인 종목만
                if ticker and name and change_pct_text:
                    try:
                        price_value = float(price_text.replace('$', '').replace(',', '')) if price_text else 0
                        # 가격이 $5 이상이고, 등락률이 양수인 종목만 (급등주)
                        if price_value >= 5.0 and '+' in change_pct_text:
                            # 섹터 정보는 yfinance로 추가 조회
                            sector = "Unknown"
                            try:
                                stock = yf.Ticker(ticker)
                                info = stock.info
                                if info and 'sector' in info:
                                    sector = info['sector']
                            except:
                                pass
                            
                            top_movers.append({
                                'ticker': ticker,
                                'name': name,
                                'change': change_pct_text,
                                'price': price_text,
                                'sector': sector
                            })
                            
                            if len(top_movers) >= max_items:
                                break
                    except:
                        continue
                        
            except Exception as e:
                logger.debug(f"Top Movers 행 파싱 실패: {e}")
                continue
        
        # 방법 2: 크롤링 실패 시 나스닥 100 구성 종목으로 대체
        if len(top_movers) < 3:
            logger.info("크롤링 결과 부족, 나스닥 100 구성 종목으로 대체 시도...")
            
            # 나스닥 100 주요 종목 리스트 (일부)
            nasdaq_100_tickers = [
                'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'NFLX',
                'AMD', 'INTC', 'CMCSA', 'ADBE', 'COST', 'AVGO', 'PEP', 'CSCO',
                'QCOM', 'AMGN', 'TXN', 'HON', 'INTU', 'AMAT', 'BKNG', 'SBUX',
                'VRSK', 'ADP', 'GILD', 'FISV', 'LRCX', 'ADI', 'CDNS', 'KLAC'
            ]
            
            for ticker in nasdaq_100_tickers[:20]:  # 상위 20개만 확인
                try:
                    stock = yf.Ticker(ticker)
                    info = stock.info
                    
                    if not info:
                        continue
                    
                    # 등락률 확인
                    change_pct = info.get('regularMarketChangePercent', 0)
                    if change_pct and change_pct > 2.0:  # 2% 이상 급등주만
                        name = info.get('longName', info.get('shortName', ticker))
                        sector = info.get('sector', 'Unknown')
                        current_price = info.get('regularMarketPrice', 0)
                        
                        if current_price >= 5.0:  # $5 이상만
                            top_movers.append({
                                'ticker': ticker,
                                'name': name,
                                'change': f"+{change_pct:.2f}%",
                                'price': f"${current_price:.2f}",
                                'sector': sector
                            })
                            
                            if len(top_movers) >= max_items:
                                break
                except Exception as e:
                    logger.debug(f"{ticker} 정보 조회 실패: {e}")
                    continue
                            
        # 등락률 기준으로 정렬 (내림차순)
        top_movers.sort(key=lambda x: float(x['change'].replace('+', '').replace('%', '')), reverse=True)
        top_movers = top_movers[:max_items]
        
        if top_movers:
            result = "**🔥 미국 시장 Top Movers (오늘의 급등주):**\n\n"
            for i, mover in enumerate(top_movers, 1):
                result += f"{i}. <b>{mover['ticker']}</b> - {mover['name']}\n"
                result += f"   📈 등락률: {mover['change']} | 💰 가격: {mover['price']} | 🏢 섹터: {mover['sector']}\n\n"
            
            logger.info(f"미국 Top Movers 수집 완료: {len(top_movers)}개 종목")
            print(f"✅ 미국 Top Movers 수집 완료: {len(top_movers)}개 종목")
            return result
        else:
            result = "**🔥 미국 시장 Top Movers:**\n오늘의 급등주 정보 수집 실패"
            logger.warning("미국 Top Movers: 데이터 없음")
            print("⚠️ 미국 Top Movers: 데이터 없음")
            return result
            
    except Exception as e:
        logger.error(f"미국 Top Movers 수집 실패: {e}")
        print(f"❌ 미국 Top Movers 수집 실패: {e}")
        return "**🔥 미국 시장 Top Movers:**\n데이터 수집 실패"


def get_korea_hot_themes(max_themes: int = 3) -> str:
    """
    네이버 금융 PC 페이지 파싱을 통한 테마 수집
    API 차단을 피하기 위해 HTML 파싱 방식을 사용
    
    Args:
        max_themes: 최대 수집할 테마 개수
    
    Returns:
        포맷팅된 Hot Themes 텍스트
    """
    logger.info("=== 한국 시장 Hot Themes 수집 시작 ===")
    print("=== 한국 시장 Hot Themes 수집 시작 ===")
    
    url = "https://finance.naver.com/sise/theme.naver"
    themes = []
    
    try:
        # curl_cffi로 PC 페이지 접근
        response = _session.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        
        # EUC-KR 디코딩 필수
        try:
            content = response.content.decode('euc-kr', 'replace')
        except:
            content = response.text
            
        soup = BeautifulSoup(content, 'html.parser')
        
        # 테이블 행 파싱
        rows = soup.select('table.type_1 tr')
        
        for row in rows:
            try:
                cols = row.select('td')
                if len(cols) < 2:
                    continue
                
                # 테마명 (첫 번째 컬럼의 링크 텍스트)
                theme_elem = cols[0].select_one('a')
                if not theme_elem:
                    continue
                theme_name = theme_elem.get_text(strip=True)
                
                # 등락률 (두 번째 컬럼)
                change_elem = cols[1].select_one('span')
                if not change_elem:
                    continue
                change_text = change_elem.get_text(strip=True).replace('%', '')
                
                try:
                    change_rate = float(change_text)
                except:
                    continue
                
                # 상승 테마만 수집 (0.5% 이상)
                if change_rate > 0.5:
                    themes.append({
                        'name': theme_name,
                        'change': change_rate
                    })
                    
                if len(themes) >= max_themes:
                    break
                    
            except Exception:
                continue
                
        if themes:
            result = "**🚀 오늘의 강세 테마 (한국):**\n"
            for i, t in enumerate(themes, 1):
                result += f"{i}. {t['name']} (+{t['change']:.2f}%)\n"
            logger.info(f"Hot Themes 수집 완료: {len(themes)}개")
            print(f"✅ Hot Themes 수집 완료: {len(themes)}개")
            return result
        else:
            return "**🚀 오늘의 강세 테마:**\n뚜렷한 강세 테마 없음"
            
    except Exception as e:
        logger.error(f"테마 수집 실패: {e}")
        return "**🚀 오늘의 강세 테마:**\n수집 실패"


def get_hankyung_consensus() -> str:
    """
    네이버 금융 리서치 수집 (국내 시장 재료)
    한경 컨센서스 대신 네이버 금융의 시황정보/리포트를 수집 (안정성 확보)
    
    Returns:
        포맷팅된 국내 시장 재료 텍스트
    """
    logger.info("=== 네이버 금융 리서치 수집 시작 ===")
    print("=== 네이버 금융 리서치 수집 시작 ===")
    
    # 네이버 금융 시황정보 페이지
    url = "https://finance.naver.com/research/market_info_list.naver"
    
    try:
        logger.info(f"네이버 금융 리서치 페이지 수집 중: {url}")
        
        # curl_cffi Session 사용 (TLS Fingerprint 우회)
        response = _session.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        
        # 네이버 금융은 euc-kr 인코딩을 사용하므로 명시적으로 디코딩
        try:
            content = response.content.decode('euc-kr', 'replace')
        except (UnicodeDecodeError, AttributeError):
            # 디코딩 실패 시 기본 방식 사용
            content = response.text
        
        soup = BeautifulSoup(content, 'html.parser')
        
        # 리포트 리스트 추출
        reports = []
        
        # 여러 가능한 선택자 시도 (범용적으로)
        selectors = [
            'table.type_1 tbody tr',
            'table tbody tr',
            '.box_type_l tbody tr',
            'tr'
        ]
        
        for selector in selectors:
            rows = soup.select(selector)
            if not rows:
                continue
            
            for row in rows[:20]:  # 상위 20개 확인
                try:
                    # 제목 추출 (다양한 패턴 시도)
                    title_elem = row.select_one('td a, a[href*="research"], a[href*="market_info"]')
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    if not title or len(title) < 5:
                        continue
                    
                    # 작성자/증권사 추출 (선택적)
                    writer = ""
                    writer_elem = row.select_one('td:last-child, .writer, .author, td:nth-child(2)')
                    if writer_elem:
                        writer = writer_elem.get_text(strip=True)
                    
                    # 중복 제거
                    if not any(r['title'] == title for r in reports):
                        reports.append({
                            'title': title,
                            'writer': writer
                        })
                        
                        if len(reports) >= 7:  # 최대 7개
                            break
                except Exception as e:
                    logger.debug(f"네이버 리포트 행 파싱 실패: {e}")
                    continue
            
            if len(reports) >= 7:
                break
        
        if reports:
            result = "[MARKET MATERIALS]\n[🇰🇷 Domestic (Source: Naver Finance Research)]\n"
            for i, report in enumerate(reports, 1):
                writer_str = f" ({report['writer']})" if report['writer'] else ""
                result += f"- {report['title']}{writer_str}\n"
            
            logger.info(f"네이버 금융 리서치 수집 완료: {len(reports)}개")
            print(f"✅ 네이버 금융 리서치 수집 완료: {len(reports)}개")
            return result
        else:
            result = "[MARKET MATERIALS]\n[🇰🇷 Domestic (Source: Naver Finance Research)]\n데이터 수집 실패"
            logger.warning("네이버 금융 리서치: 데이터 없음")
            print("⚠️ 네이버 금융 리서치: 데이터 없음")
            return result
            
    except Exception as e:
        logger.error(f"네이버 금융 리서치 수집 실패: {e}")
        print(f"❌ 네이버 금융 리서치 수집 실패: {e}")
        return "[MARKET MATERIALS]\n[🇰🇷 Domestic (Source: Naver Finance Research)]\n데이터 수집 실패"


def get_global_rss_news(max_items_per_source: int = 3) -> List[str]:
    """
    Bloomberg, CNBC 등 글로벌 RSS 피드에서 뉴스 헤드라인 수집
    
    Args:
        max_items_per_source: 소스당 최대 수집할 뉴스 개수
    
    Returns:
        뉴스 헤드라인 리스트 (형식: "[소스명] 헤드라인")
    """
    if not FEEDPARSER_AVAILABLE:
        logger.warning("feedparser가 설치되지 않음, RSS 피드 수집 불가")
        return []
    
    news_list = []
    
    # 검증된 글로벌 뉴스 소스
    rss_sources = {
        "Bloomberg": "https://feeds.bloomberg.com/markets/news.rss",
        "CNBC": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "Investing.com": "https://www.investing.com/rss/news.rss"
    }
    
    for source, url in rss_sources.items():
        try:
            logger.info(f"{source} RSS 피드 수집 중: {url}")
            
            # curl_cffi 세션으로 RSS 피드 가져오기 (차단 우회)
            response = _session.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            
            # feedparser로 RSS 파싱
            feed = feedparser.parse(response.content)
            
            if not feed.entries:
                logger.debug(f"{source}: RSS 피드 항목 없음")
                continue
            
            count = 0
            for entry in feed.entries[:max_items_per_source]:
                try:
                    title = entry.get('title', '').strip()
                    if title and len(title) >= 20:  # 20자 이상만 필터링
                        # RSS 피드에서 summary/description 추출 시도
                        summary = entry.get('summary', '') or entry.get('description', '')
                        # HTML 태그 제거 (간단한 처리)
                        if summary:
                            from bs4 import BeautifulSoup
                            try:
                                summary = BeautifulSoup(summary, 'html.parser').get_text(strip=True)
                            except:
                                pass
                        # summary가 있으면 포함, 없으면 제목만
                        if summary:
                            news_list.append(f"[{source}] {title} | {summary[:150]}")
                        else:
                            news_list.append(f"[{source}] {title}")
                        count += 1
                except Exception as e:
                    logger.debug(f"{source} 항목 파싱 실패: {e}")
                    continue
            
            if count > 0:
                logger.info(f"{source} RSS 수집 완료: {count}개")
            else:
                logger.debug(f"{source}: 유효한 헤드라인 없음")
                
        except Exception as e:
            logger.warning(f"{source} RSS 수집 실패: {e}")
            continue
    
    return news_list


def get_google_news_rss() -> str:
    """
    해외 시장 재료 수집 (Yahoo Finance + Bloomberg + CNBC RSS)
    Yahoo Finance HTML 크롤링과 글로벌 RSS 피드를 통합하여 수집
    
    Returns:
        포맷팅된 해외 시장 재료 텍스트
    """
    logger.info("=== 해외 시장 재료 수집 시작 ===")
    print("=== 해외 시장 재료 수집 시작 ===")
    
    all_articles = []
    
    # 1. Yahoo Finance News 수집 (yfinance 사용)
    market_tickers = ['^GSPC', '^DJI', '^IXIC', 'NVDA', 'TSLA', 'AAPL']
    
    try:
        logger.info(f"yfinance를 사용한 Yahoo Finance News 수집 시작")
        
        yahoo_news_count = 0
        for ticker in market_tickers:
            try:
                ticker_obj = yf.Ticker(ticker)
                news_list = ticker_obj.news
                
                if not news_list:
                    continue
                
                for news_item in news_list:
                    try:
                        content = news_item.get('content', {})
                        title = content.get('title', '') if isinstance(content, dict) else ''
                        
                        if not title or len(title) < 20:
                            continue
                        
                        # 중복 제거
                        title_lower = title.lower().strip()
                        if any(title_lower in a.lower() for a in all_articles):
                            continue
                        
                        all_articles.append(f"[Yahoo Finance] {title}")
                        yahoo_news_count += 1
                        
                        if yahoo_news_count >= 5:  # Yahoo Finance는 상위 5개
                            break
                            
                    except Exception as e:
                        logger.debug(f"Yahoo News 항목 파싱 실패: {e}")
                        continue
                
                if yahoo_news_count >= 5:
                    break
                    
            except Exception as e:
                logger.debug(f"{ticker} 뉴스 수집 실패: {e}")
                continue
        
        logger.info(f"Yahoo Finance News 수집 완료: {yahoo_news_count}개 (yfinance 사용)")
    except Exception as e:
        logger.warning(f"Yahoo Finance News 수집 실패: {e}")
    
    # 2. 글로벌 RSS 피드 수집 (Bloomberg, CNBC)
    rss_news = get_global_rss_news(max_items_per_source=3)
    if rss_news:
        all_articles.extend(rss_news)
        logger.info(f"글로벌 RSS 수집 완료: {len(rss_news)}개")
    
    # 중복 제거 및 정렬
    unique_articles = []
    seen_titles = set()
    for article in all_articles:
        # 소스명 제거한 제목으로 중복 체크
        title_only = article.split('] ', 1)[-1] if '] ' in article else article
        title_lower = title_only.lower().strip()
        
        if title_lower not in seen_titles:
            seen_titles.add(title_lower)
            unique_articles.append(article)
    
    if unique_articles:
        result = "[🌎 해외 재료 (Sources: Yahoo Finance, Bloomberg, CNBC, Reuters)]\n"
        for i, article in enumerate(unique_articles, 1):
            result += f"{i}. {article}\n"
        
        logger.info(f"해외 시장 재료 수집 완료: {len(unique_articles)}개")
        print(f"✅ 해외 시장 재료 수집 완료: {len(unique_articles)}개")
        return result
    else:
        result = "[🌎 해외 재료 (Sources: Yahoo Finance, Bloomberg, CNBC, Reuters)]\n데이터 수집 실패"
        logger.warning("해외 시장 재료: 데이터 없음")
        print("⚠️ 해외 시장 재료: 데이터 없음")
        return result


def is_korean_text(text: str) -> bool:
    """
    텍스트가 한국어인지 판단
    
    Args:
        text: 판단할 텍스트
    
    Returns:
        한국어가 포함되어 있으면 True
    """
    import re
    # 한글 유니코드 범위: 가-힣 (AC00-D7A3)
    korean_pattern = re.compile(r'[\uAC00-\uD7A3]')
    return bool(korean_pattern.search(text))


def translate_headlines(headlines_text: str) -> str:
    """
    뉴스 헤드라인 포맷팅 및 영어 뉴스 한국어 번역 (deep-translator 사용)
    영어 뉴스의 경우 한국어 번역을 하단에 추가
    
    Args:
        headlines_text: 원문 헤드라인 텍스트
    
    Returns:
        포맷팅된 뉴스 텍스트 (영어 뉴스는 한국어 번역 포함)
    """
    if "뉴스 데이터 수집 불가" in headlines_text:
        return headlines_text
    
    try:
        import re
        from deep_translator import GoogleTranslator
        
        # 헤드라인만 추출 (번호와 제목)
        lines = headlines_text.split('\n')
        headlines_data = []  # (번호, 제목) 튜플 리스트
        
        for line in lines:
            line = line.strip()
            if line and not line.startswith('**') and not line.startswith('요약:'):
                # 번호와 제목 추출
                if line.startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.', '10.')):
                    # HTML 태그 제거
                    clean_line = re.sub(r'<[^>]+>', '', line)
                    # 번호와 제목 분리
                    match = re.match(r'^(\d+)\.\s*(.+)', clean_line)
                    if match:
                        number = match.group(1)
                        title = match.group(2).strip()
                        headlines_data.append((number, title))
        
        # Hot 뉴스인지 일반 뉴스인지 확인
        is_hot_news = "해외시장 Hot 뉴스" in headlines_text or "국내시장 Hot 뉴스" in headlines_text
        
        if not headlines_data:
            # 포맷팅만 적용
            if is_hot_news:
                if not headlines_text.startswith("<b>🔥"):
                    return f"<b>🔥 Hot/인기 뉴스</b>\n{headlines_text}"
            else:
                if not headlines_text.startswith("<b>📰"):
                    return f"<b>📰 주요 시장 뉴스 (제목+요약)</b>\n{headlines_text}"
            return headlines_text
        
        # 최종 결과 포맷팅
        formatted_lines = []
        if is_hot_news:
            formatted_lines.append("<b>🔥 Hot/인기 뉴스</b>\n")
        else:
            formatted_lines.append("<b>📰 주요 시장 뉴스 (제목+요약)</b>\n")
        
        # 원본 뉴스 텍스트에서 요약 정보도 함께 가져오기
        original_lines = headlines_text.split('\n')
        summary_map = {}  # 번호 -> 요약
        current_number = None
        for i, line in enumerate(original_lines):
            line = line.strip()
            if line.startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.', '10.')):
                match = re.match(r'^(\d+)\.', line)
                if match:
                    current_number = match.group(1)
            elif line.startswith('요약:') and current_number:
                summary_text = line.replace('요약:', '').strip()
                summary_map[current_number] = summary_text
        
        # 모든 헤드라인을 번호 순서대로 출력
        all_numbers = sorted(set([num for num, _ in headlines_data]), key=int)
        
        # 번역이 필요한 뉴스 수집
        items_to_translate = []
        for number in all_numbers:
            headline_info = next((num, title) for num, title in headlines_data if num == number)
            _, title = headline_info
            
            if not is_korean_text(title):
                summary = summary_map.get(number, "")
                items_to_translate.append({
                    'number': number,
                    'title': title,
                    'summary': summary if summary and not is_korean_text(summary) and len(summary) > 20 else None
                })
        
        # deep-translator를 사용한 번역
        translation_map = {}  # number -> {'title': 번역된 제목, 'summary': 번역된 요약}
        
        if items_to_translate:
            try:
                logger.info(f"뉴스 번역 시작: {len(items_to_translate)}개 뉴스 (deep-translator 사용)")
                
                # GoogleTranslator 초기화
                translator = GoogleTranslator(source='en', target='ko')
                
                # 각 뉴스 제목과 요약 번역
                for item in items_to_translate:
                    try:
                        # 제목 번역
                        translated_title = translator.translate(item['title'])
                        translation_map[item['number']] = {'title': translated_title}
                        
                        # 요약 번역 (있는 경우)
                        if item['summary']:
                            translated_summary = translator.translate(item['summary'][:200])
                            translation_map[item['number']]['summary'] = translated_summary
                        
                        # Rate limit 방지를 위한 짧은 지연
                        import time
                        time.sleep(0.1)  # 100ms 지연
                        
                    except Exception as e:
                        logger.warning(f"뉴스 {item['number']}번 번역 실패: {e}")
                        continue
                
                logger.info(f"뉴스 번역 완료: {len(translation_map)}개 번역 성공")
                
            except Exception as e:
                logger.warning(f"번역 라이브러리 초기화 실패: {e}, 원문만 표시")
                # 폴백: 번역 실패 시 원문만 표시
        
        # 포맷팅: 번역 결과 포함
        for number in all_numbers:
            # 해당 번호의 헤드라인 찾기
            headline_info = next((num, title) for num, title in headlines_data if num == number)
            _, title = headline_info
            
            # 원문 표시
            formatted_lines.append(f"<b>{number}. {title}</b>")
            
            # 요약 표시
            if number in summary_map:
                formatted_lines.append(f"   요약: {summary_map[number]}")
            
            # 번역 결과 표시 (배치 번역 결과 사용)
            if number in translation_map:
                translated = translation_map[number]
                if 'title' in translated:
                    formatted_lines.append(f"   🇰🇷 번역: {translated['title']}")
                if 'summary' in translated and translated['summary']:
                    formatted_lines.append(f"      요약 번역: {translated['summary']}")
            
            formatted_lines.append("")  # 빈 줄
        
        result = "\n".join(formatted_lines)
        logger.info(f"뉴스 포맷팅 완료: {len(headlines_data)}개")
        return result
        
    except Exception as e:
        logger.warning(f"뉴스 헤드라인 포맷팅 실패: {e}, 원문 그대로 사용")
        return headlines_text


def get_krx_api_status() -> Dict[str, any]:
    """
    KRX API 상태 정보 반환
    
    Returns:
        {
            'expired': 유효기간 만료 여부 (bool),
            'expiry_date': 만료일 (date 또는 None),
            'days_until_expiry': 만료까지 남은 일수 (int 또는 None)
        }
    """
    try:
        from config.settings import settings

        if not settings.krx_api_key:
            return {'expired': False, 'expiry_date': None, 'days_until_expiry': None}
        
        if settings.krx_api_key_expiry:
            today = date.today()
            days_left = (settings.krx_api_key_expiry - today).days
            return {
                'expired': today > settings.krx_api_key_expiry,
                'expiry_date': settings.krx_api_key_expiry,
                'days_until_expiry': days_left if days_left >= 0 else 0
            }
        else:
            return {'expired': False, 'expiry_date': None, 'days_until_expiry': None}
    except Exception as e:
        logger.debug(f"KRX API 상태 확인 실패: {e}")
        return {'expired': False, 'expiry_date': None, 'days_until_expiry': None}


def get_kr_stock_data(ticker_code: str) -> Dict[str, Optional[float]]:
    """
    국내 주식 특화 데이터 수집 (수급, ETF 괴리율)

    TraditionalAPISource를 사용하여 데이터 수집 (Fallback 체인 적용)
    - KIS API → pykrx → KRX API → 네이버 크롤링

    Args:
        ticker_code: 국내 티커 코드 (예: '005930' for '005930.KS')

    Returns:
        {
            'foreign_net': 외국인 순매매량 (만 주, 최근 3거래일 합계),
            'institutional_net': 기관 순매매량 (만 주, 최근 3거래일 합계),
            'foreign_net_1d': 외국인 순매매량 (만 주, 최근 1거래일),
            'institutional_net_1d': 기관 순매매량 (만 주, 최근 1거래일),
            'disparity_rate': ETF 괴리율 (NAV 대비 %, ETF가 아닐 경우 None),
            'total_volume': 전체 거래량 (주 단위, ACC_TRDVOL, 최근 3거래일 합계),
            'total_volume_1d': 전체 거래량 (주 단위, ACC_TRDVOL, 최근 1거래일)
        }
    """
    result = {
        'foreign_net': None,
        'institutional_net': None,
        'foreign_net_1d': None,
        'institutional_net_1d': None,
        'disparity_rate': None,
        'total_volume': None,
        'total_volume_1d': None
    }

    try:
        from dual_source.sources.api_source import TraditionalAPISource
        from config.settings import settings

        # TraditionalAPISource를 사용하여 데이터 수집
        krx_api_key = getattr(settings, 'krx_api_key', None)
        source = TraditionalAPISource(krx_api_key=krx_api_key)
        data = source._collect_korean_stock(ticker_code)

        # 수집된 데이터를 결과에 매핑
        result['foreign_net'] = data.get('foreign_net')
        result['institutional_net'] = data.get('institutional_net')
        result['foreign_net_1d'] = data.get('foreign_net_1d')
        result['institutional_net_1d'] = data.get('institutional_net_1d')
        result['disparity_rate'] = data.get('disparity_rate')
        result['total_volume'] = data.get('total_volume')
        result['total_volume_1d'] = data.get('total_volume_1d')

        logger.debug(f"{ticker_code}: TraditionalAPISource로 수급 데이터 수집 완료")
        return result

    except Exception as e:
        logger.error(f"{ticker_code} 국내 주식 데이터 수집 실패: {e}")
        return result


def get_global_institutional_data(ticker_symbol: str) -> Optional[float]:
    """
    해외 주식 기관 보유 비중 수집

    Args:
        ticker_symbol: 해외 티커 심볼 (예: 'AAPL', 'NVDA')

    Returns:
        기관 보유 비중 (%) 또는 None (실패 시)
    """
    try:
        stock = yf.Ticker(ticker_symbol)
        info = stock.info

        if not info or len(info) == 0:
            return None

        # heldPercentInstitutions 정보 추출
        held_percent = info.get('heldPercentInstitutions')

        if held_percent is not None:
            held_percent = float(held_percent) * 100  # 소수점을 퍼센트로 변환
            return round(held_percent, 2)

        return None

    except Exception as e:
        logger.debug(f"{ticker_symbol} 기관 보유 비중 수집 실패: {e}")
        return None


def get_kr_stock_data_v2(ticker_code: str) -> Dict[str, Optional[float]]:
    """
    듀얼 소스 시스템을 사용한 국내 주식 데이터 수집 (병렬 수집 + 교차 검증)

    기존 get_kr_stock_data() 함수와 동일한 반환 형식을 유지하여 호환성을 보장합니다.
    추가로 신뢰도(_confidence)와 검증 상태(_validation_status) 메타데이터를 포함합니다.

    Args:
        ticker_code: 국내 티커 코드 (예: '005930.KS', '379810.KS')

    Returns:
        {
            'foreign_net': 외국인 순매매량 (만 주, 최근 3거래일 합계),
            'institutional_net': 기관 순매매량 (만 주, 최근 3거래일 합계),
            'foreign_net_1d': 외국인 순매매량 (만 주, 최근 1거래일),
            'institutional_net_1d': 기관 순매매량 (만 주, 최근 1거래일),
            'disparity_rate': ETF 괴리율 (NAV 대비 %, ETF가 아닐 경우 None),
            'total_volume': 전체 거래량 (주 단위, 최근 3거래일 합계),
            'total_volume_1d': 전체 거래량 (주 단위, 최근 1거래일),
            '_confidence': 데이터 신뢰도 (0~100%),
            '_validation_status': 검증 상태 (match, partial, conflict, single, empty)
        }
    """
    try:
        from src.dual_source import get_collector

        collector = get_collector()
        validated = collector.collect_sync(ticker_code)

        # 기존 반환 형식으로 변환
        data = validated.get('data', {})
        result: Dict[str, Optional[float]] = {
            'foreign_net': data.get('foreign_net'),
            'institutional_net': data.get('institutional_net'),
            'foreign_net_1d': data.get('foreign_net_1d'),
            'institutional_net_1d': data.get('institutional_net_1d'),
            'disparity_rate': data.get('disparity_rate'),
            'total_volume': data.get('total_volume'),
            'total_volume_1d': data.get('total_volume_1d'),
            # 추가 메타데이터
            '_confidence': validated.get('confidence', 0.0),
            '_validation_status': validated.get('validation', {}).get('status', 'unknown'),
        }

        # ValidationStatus enum을 문자열로 변환
        status = result.get('_validation_status')
        if hasattr(status, 'value'):
            result['_validation_status'] = status.value

        logger.debug(
            f"{ticker_code} 듀얼 소스 v2: "
            f"신뢰도={result['_confidence']:.1f}%, "
            f"상태={result['_validation_status']}"
        )

        return result

    except ImportError as e:
        logger.warning(f"듀얼 소스 모듈 로드 실패, 기존 방식으로 폴백: {e}")
        return get_kr_stock_data(ticker_code)
    except Exception as e:
        logger.error(f"{ticker_code} 듀얼 소스 v2 수집 실패, 기존 방식으로 폴백: {e}")
        return get_kr_stock_data(ticker_code)

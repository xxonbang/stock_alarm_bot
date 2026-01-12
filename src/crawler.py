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
from datetime import datetime, timedelta
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
except ImportError:
    feedparser = None
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

logger = logging.getLogger(__name__)

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


def get_yahoo_finance_news(max_items: int = 10) -> List[Dict]:
    """
    Yahoo Finance에서 뉴스 제목과 요약문 수집
    
    Args:
        max_items: 최대 수집할 뉴스 개수
    
    Returns:
        [{"title": "...", "summary": "...", "link": "..."}, ...] 형태의 리스트
    """
    news_items = []
    try:
        url = "https://finance.yahoo.com/news/"
        logger.info(f"Yahoo Finance 뉴스 수집 중: {url}")
        
        response = _session.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Yahoo Finance 뉴스 구조 파싱
        # 여러 가능한 선택자 시도
        article_selectors = [
            'article[data-module="StreamItem"]',
            '.js-stream-content li',
            'li[class*="stream-item"]',
            'article',
        ]
        
        found_items = []
        for selector in article_selectors:
            articles = soup.select(selector)
            for article in articles:
                try:
                    # 제목 추출
                    title_elem = article.select_one('h3 a, h2 a, a[class*="title"]')
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    link = title_elem.get('href', '')
                    if link and not link.startswith('http'):
                        link = f"https://finance.yahoo.com{link}"
                    
                    # 요약문 추출
                    summary_elem = article.select_one('p, .summary, [class*="summary"], [class*="description"]')
                    summary = summary_elem.get_text(strip=True) if summary_elem else ""
                    
                    if title and len(title) > 10:
                        found_items.append({
                            'title': title,
                            'summary': summary[:200] if summary else "",  # 요약문 최대 200자
                            'link': link
                        })
                        if len(found_items) >= max_items:
                            break
                except Exception as e:
                    logger.debug(f"뉴스 항목 파싱 실패: {e}")
                    continue
            
            if len(found_items) >= max_items:
                break
        
        news_items = found_items[:max_items]
        logger.info(f"Yahoo Finance 뉴스 수집 완료: {len(news_items)}개")
        
    except Exception as e:
        logger.warning(f"Yahoo Finance 뉴스 수집 실패: {e}")
    
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
        ticker_name_mapping = {
            # 해외 종목
            'TSLA': ['tesla', '테슬라'],
            'NVDA': ['nvidia', '엔비디아'],
            'AAPL': ['apple', '애플'],
            'GOOGL': ['google', 'alphabet', '구글'],
            'MSFT': ['microsoft', '마이크로소프트'],
            'SPY': ['s&p 500', 'sp500', 's&p500'],
            'QQQ': ['nasdaq', '나스닥'],
            'VTI': ['total stock market', 'vanguard total'],
            'GLD': ['gold', 'spdr gold', '금'],
            'SLV': ['silver', 'ishares silver', '은'],
            'BTC-USD': ['bitcoin', 'btc', '비트코인'],
            'ETH-USD': ['ethereum', 'eth', '이더리움'],
            # 국내 종목
            '005930.KS': ['samsung', '삼성전자', '삼성'],
            '000660.KS': ['sk hynix', 'hynix', 'sk하이닉스', '하이닉스'],
        }
        
        # 포트폴리오 티커에 대한 기업명 수집
        for ticker in portfolio_tickers:
            if ticker in ticker_name_mapping:
                portfolio_names[ticker] = ticker_name_mapping[ticker]
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


def get_fred_macro_data() -> str:
    """
    FRED API를 사용하여 연준 데이터 수집 (Macro Intelligence)
    
    Returns:
        포맷팅된 FRED 매크로 데이터 텍스트
    """
    logger.info("=== FRED API 매크로 데이터 수집 시작 ===")
    
    if Fred is None:
        logger.warning("fredapi 라이브러리가 없어 FRED 데이터를 수집할 수 없습니다.")
        return "[MACRO DATA (Source: Federal Reserve FRED)]\nFRED API 라이브러리 미설치"
    
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
    
    # Part B: yfinance로 수집 가능한 지표들 (FRED에 없는 것들)
    macro_tickers = {
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


def get_economic_calendar(max_retries: int = 3) -> str:
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


def get_seeking_alpha_outlook(max_retries: int = 3) -> str:
    """
    yfinance 내장 뉴스 기능을 사용한 전문가 시장 전망 수집
    웹 크롤링 대신 안정적인 라이브러리 기능 활용
    
    Args:
        max_retries: 최대 재시도 횟수 (yfinance는 안정적이므로 거의 사용 안 됨)
    
    Returns:
        포맷팅된 시장 전망 텍스트
    """
    logger.info("=== 전문가 시장 전망 수집 시작 (yfinance 뉴스 기능) ===")
    print("=== 전문가 시장 전망 수집 시작 (yfinance 뉴스 기능) ===")
    
    # 시장을 대표하는 주요 지수 티커
    market_tickers = {
        '^GSPC': 'S&P 500',
        '^IXIC': '나스닥',
        '^KS11': '코스피',
        '^DJI': '다우존스'
    }
    
    # 관련 키워드 (제목에 포함되어야 함) - 더 넓은 범위로 확장
    relevant_keywords = [
        'outlook', 'forecast', 'analysis', 'fed', 'rate', 'market', 'economy', 'economic',
        '전망', '예측', '분석', '연준', '금리', '시장', '경제',
        'target', 'upgrade', 'downgrade', 'bullish', 'bearish', 'inflation', 'gdp',
        '목표가', '상향', '하향', '상승', '하락', '인플레이션',
        'policy', 'central bank', '정책', '중앙은행', '기준금리'
    ]
    
    all_articles = []
    
    for attempt in range(max_retries):
        try:
            for ticker, market_name in market_tickers.items():
                try:
                    logger.info(f"{market_name} ({ticker}) 뉴스 수집 중...")
                    print(f"{market_name} ({ticker}) 뉴스 수집 중...")
                    
                    # yfinance Ticker 객체 생성
                    ticker_obj = yf.Ticker(ticker)
                    
                    # 뉴스 가져오기
                    news_list = ticker_obj.news
                    
                    if not news_list:
                        logger.debug(f"{ticker}: 뉴스 없음")
                                    continue
                            
                    logger.info(f"{ticker}: {len(news_list)}개 뉴스 발견")
                    
                    # 뉴스 필터링 (키워드 기반)
                    for news_item in news_list:
                        try:
                            # yfinance 뉴스 구조: content.title, canonicalUrl.url, provider.displayName
                            content = news_item.get('content', {})
                            title = content.get('title', '') if isinstance(content, dict) else ''
                            
                            # link 추출
                            canonical_url = news_item.get('canonicalUrl', {})
                            link = canonical_url.get('url', '') if isinstance(canonical_url, dict) else ''
                            
                            # publisher 추출
                            provider = news_item.get('provider', {})
                            publisher = provider.get('displayName', 'Yahoo Finance') if isinstance(provider, dict) else 'Yahoo Finance'
                            
                            if not title:
                                continue
                            
                            # 키워드 필터링 (더 유연하게)
                            title_lower = title.lower()
                            
                            # 키워드가 있으면 우선순위 높음, 없어도 최근 뉴스면 포함 (최대 3개)
                            has_keyword = any(keyword.lower() in title_lower for keyword in relevant_keywords)
                            
                            if has_keyword or len(all_articles) < 3:
                                all_articles.append({
                                    'title': title,
                                    'link': link,
                                    'publisher': publisher,
                                    'market': market_name,
                                    'has_keyword': has_keyword
                                })
                                
                                # 충분한 기사 수집되면 중단
                                if len(all_articles) >= 10:
                                    break
                except Exception as e:
                            logger.debug(f"뉴스 항목 파싱 실패: {e}")
                    continue
            
                            
                except Exception as e:
                    logger.warning(f"{ticker} 뉴스 수집 실패: {e}")
                    print(f"⚠️ {ticker} 뉴스 수집 실패: {e}")
                    continue
            
            # 중복 제거 (제목 기준) 및 키워드 우선순위 정렬
            unique_articles = []
            seen_titles = set()
            for article in all_articles:
                title_lower = article['title'].lower()
                if title_lower not in seen_titles:
                    seen_titles.add(title_lower)
                    unique_articles.append(article)
            
            # 키워드가 있는 기사를 우선 정렬
            unique_articles.sort(key=lambda x: (not x.get('has_keyword', False), x['title']))
            
            # 최대 5개로 제한
            unique_articles = unique_articles[:5]
            
            if unique_articles:
                result = "**📊 전문가 시장 전망 (yfinance 뉴스):**\n\n"
                for i, article in enumerate(unique_articles, 1):
                    result += f"{i}. <b>{article['title']}</b>\n"
                    if article['publisher']:
                        result += f"   📰 출처: {article['publisher']} ({article['market']})\n"
                    if article['link']:
                        result += f"   🔗 {article['link']}\n"
                    result += "\n"
                
                logger.info(f"전문가 시장 전망 수집 완료: {len(unique_articles)}개 기사")
                print(f"✅ 전문가 시장 전망 수집 완료: {len(unique_articles)}개 기사")
                return result
            else:
                result = "**📊 전문가 시장 전망:**\n관련 기사 없음 (키워드 필터링 후)"
                logger.info("전문가 시장 전망: 관련 기사 없음")
                print("전문가 시장 전망: 관련 기사 없음")
                return result
                
        except Exception as e:
            logger.warning(f"전문가 전망 수집 실패 (시도 {attempt + 1}/{max_retries}): {e}")
            print(f"❌ 전문가 전망 수집 실패 (시도 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
    
    # 모든 시도 실패
    logger.warning("전문가 시장 전망 수집 실패 (모든 시도 실패)")
    print("❌ 전문가 시장 전망 수집 실패 (모든 시도 실패)")
    return "**📊 전문가 시장 전망:**\n데이터 수집 실패"


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
    if feedparser is None:
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
    
    # 1. Yahoo Finance News 수집
    url = "https://finance.yahoo.com/topic/stock-market-news/"
    
    try:
        logger.info(f"Yahoo Finance News 수집 중: {url}")
        
        # curl_cffi Session 사용 (TLS Fingerprint 우회)
        response = _session.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 뉴스 헤드라인 추출: 모든 h3 태그에서 추출
        h3_tags = soup.find_all('h3')
        
        for h3 in h3_tags:
            try:
                # h3 내부의 링크 또는 텍스트 추출
                link = h3.find('a')
                if link:
                    title = link.get_text(strip=True)
                else:
                    title = h3.get_text(strip=True)
                
                # 20자 이상인 것만 필터링 (광고 제외)
                if title and len(title) >= 20:
                    # 중복 제거
                    if title not in all_articles:
                        all_articles.append(f"[Yahoo Finance] {title}")
                        
                        if len(all_articles) >= 5:  # Yahoo Finance는 상위 5개
                            break
            except Exception as e:
                logger.debug(f"Yahoo News 항목 파싱 실패: {e}")
                continue
        
        logger.info(f"Yahoo Finance News 수집 완료: {len([a for a in all_articles if '[Yahoo Finance]' in a])}개")
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


def get_market_headlines(max_items: int = 10) -> str:
    """
    기존 호환성을 위한 함수 (제목만 수집)
    새로운 get_market_news_with_context() 사용 권장
    """
    return get_market_news_with_context(max_items)


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


def translate_headlines(headlines_text: str, ai_researcher=None) -> str:
    """
    뉴스 헤드라인 포맷팅 (API 호출 제거 - Batch Processing 구조)
    번역 없이 원문 그대로 사용하여 API 호출을 단 1회로 제한
    
    [중요] 이 함수는 AI를 사용하지 않습니다. 순수 Python 문자열 처리만 수행합니다.
    
    Args:
        headlines_text: 원문 헤드라인 텍스트
        ai_researcher: 사용하지 않음 (호환성을 위해 유지, 무시됨)
    
    Returns:
        포맷팅된 뉴스 텍스트 (원문 그대로, 번역 없음)
    """
    if "뉴스 데이터 수집 불가" in headlines_text:
        return headlines_text
    
    try:
        import re
        
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
        
        if not headlines_data:
            # 포맷팅만 적용
            if not headlines_text.startswith("<b>📰"):
                return f"<b>📰 주요 시장 뉴스 (제목+요약)</b>\n{headlines_text}"
            return headlines_text
        
        # 최종 결과 포맷팅
        formatted_lines = []
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
        
        for number in all_numbers:
            # 해당 번호의 헤드라인 찾기
            headline_info = next((num, title) for num, title in headlines_data if num == number)
            _, title = headline_info
            
            # 원문 그대로 표시 (번역 없음)
                formatted_lines.append(f"<b>{number}. {title}</b>")
                if number in summary_map:
                    formatted_lines.append(f"   요약: {summary_map[number]}")
            formatted_lines.append("")  # 빈 줄
        
        result = "\n".join(formatted_lines)
        logger.info(f"뉴스 포맷팅 완료: {len(headlines_data)}개 (API 호출 없음 - Batch Processing)")
        return result
        
    except Exception as e:
        logger.warning(f"뉴스 헤드라인 포맷팅 실패: {e}, 원문 그대로 사용")
        return headlines_text

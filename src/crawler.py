"""
뉴스 및 시황 크롤링 모듈 (고도화 버전)
뉴스 제목+요약문 수집 및 매크로 경제 지표 수집
"""
import requests
from bs4 import BeautifulSoup
import logging
from typing import List, Dict, Optional
import time
import yfinance as yf
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# User-Agent 헤더 (봇 차단 방지)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}


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
        
        response = requests.get(url, headers=HEADERS, timeout=10)
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
        
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
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


def filter_relevant_news(news_items: List[Dict]) -> List[Dict]:
    """
    포트폴리오와 관련된 뉴스만 필터링 (노이즈 제거)
    가중치 시스템 적용: 높은 가중치 키워드 매칭 시 우선순위 부여
    
    Args:
        news_items: 뉴스 아이템 리스트
    
    Returns:
        필터링된 뉴스 아이템 리스트 (가중치 순으로 정렬)
    """
    # 포트폴리오 관련 키워드 (가중치별 분류)
    keyword_weights = {
        'high': [
            # 핵심 종목명
            'nvidia', 'nvda', 'tesla', 'tsla', 'apple', 'aapl', 'google', 'googl', 'microsoft', 'msft',
            'samsung', 'sk hynix', 'hynix',
            # 핵심 매크로 지표
            'fed', 'federal reserve', 'interest rate', 'cpi', 'inflation', 'unemployment',
            # 핵심 원자재
            'gold', 'silver', 'oil', 'crude',
            # 핵심 암호화폐
            'bitcoin', 'btc', 'ethereum', 'eth',
            # 핵심 지수
            's&p', 'sp500', 'nasdaq', 'dow', 'kospi', 'kosdaq'
        ],
        'medium': [
            # 기술/반도체 일반
            'ai', 'artificial intelligence', 'tech', 'technology', 'semiconductor', 'chip',
            # 에너지 일반
            'energy', 'petroleum',
            # 암호화폐 일반
            'crypto', 'cryptocurrency',
            # 금리/채권
            'treasury', 'bond', 'yield', 'rate'
        ],
        'low': [
            # 시장 전반 (너무 일반적이어서 낮은 가중치)
            'market', 'trading', 'investment', 'investor', 'equity', 'stock', 'index', 'etf',
            'economic', 'economy'
        ]
    }
    
    scored_news = []
    for news in news_items:
        title_lower = news['title'].lower()
        summary_lower = news.get('summary', '').lower()
        combined_text = f"{title_lower} {summary_lower}"
        
        # 가중치 계산
        score = 0
        matched_keywords = []
        
        for weight_level, keywords in keyword_weights.items():
            weight_value = {'high': 3, 'medium': 2, 'low': 1}[weight_level]
            for keyword in keywords:
                if keyword in combined_text:
                    score += weight_value
                    matched_keywords.append(keyword)
                    break  # 같은 가중치 레벨에서는 첫 매칭만 카운트
        
        # 최소 점수 이상만 포함 (low만 매칭된 경우 제외)
        if score >= 2:  # high 1개 또는 medium 1개 이상
            scored_news.append({
                'news': news,
                'score': score,
                'keywords': matched_keywords
            })
        else:
            logger.debug(f"필터링됨 (점수 부족: {score}): {news['title'][:50]}")
    
    # 가중치 순으로 정렬 (높은 점수 우선)
    scored_news.sort(key=lambda x: x['score'], reverse=True)
    filtered_news = [item['news'] for item in scored_news]
    
    logger.info(f"뉴스 필터링: {len(news_items)}개 -> {len(filtered_news)}개 (포트폴리오 관련, 가중치 적용)")
    if scored_news:
        logger.debug(f"상위 3개 뉴스 점수: {[item['score'] for item in scored_news[:3]]}")
    
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
    
    # 포트폴리오 관련 뉴스만 필터링
    filtered_news = filter_relevant_news(all_news)
    
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


def get_market_indicators() -> str:
    """
    매크로 경제 지표 수집 (yfinance + 공포/탐욕 지수)
    
    Returns:
        포맷팅된 매크로 지표 텍스트
    """
    logger.info("=== 매크로 경제 지표 수집 시작 ===")
    
    indicators = []
    
    # Part A: yfinance로 수집 가능한 지표들
    macro_tickers = {
        'KRW=X': 'USD/KRW 환율',
        '^TNX': 'US 10-Year Treasury',
        'CL=F': 'WTI 원유',
        'GC=F': '금 선물',
        '^VIX': 'VIX 변동성 지수',
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
        except Exception as e:
            logger.warning(f"{name} ({ticker}) 수집 실패: {e}")
            indicators.append(f"- {name}: N/A")
    
    # Part B: 공포/탐욕 지수 (Fear & Greed Index)
    fear_greed = get_fear_greed_index()
    if fear_greed:
        indicators.append(fear_greed)
    
    # 결과 포맷팅
    if indicators:
        result = "**매크로 경제 지표:**\n" + "\n".join(indicators)
        logger.info(f"매크로 지표 수집 완료: {len(indicators)}개")
    else:
        result = "**매크로 경제 지표:**\n데이터 수집 불가"
        logger.warning("매크로 지표 수집 실패")
    
    return result


def get_fear_greed_index() -> Optional[str]:
    """
    공포/탐욕 지수 (Fear & Greed Index) 수집 (세부 지표 포함)
    CNN Business 또는 Alternative.me에서 수집 시도
    
    Returns:
        포맷팅된 공포/탐욕 지수 문자열 (세부 지표 포함) 또는 None
    """
    try:
        # Alternative.me Fear & Greed Index (무료 API)
        url = "https://api.alternative.me/fng/"
        logger.info("공포/탐욕 지수 수집 중...")
        
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if 'data' in data and len(data['data']) > 0:
            latest = data['data'][0]
            value = int(latest.get('value', 0))
            classification = latest.get('value_classification', 'N/A')
            
            # 이모지 추가
            if value <= 25:
                emoji = "😨"  # Extreme Fear
            elif value <= 45:
                emoji = "😟"  # Fear
            elif value <= 55:
                emoji = "😐"  # Neutral
            elif value <= 75:
                emoji = "😊"  # Greed
            else:
                emoji = "🚀"  # Extreme Greed
            
            result = f"- 공포/탐욕 지수: {value} ({classification}) {emoji}"
            logger.info(f"공포/탐욕 지수 수집 완료: {value} ({classification})")
            return result
    except Exception as e:
        logger.warning(f"공포/탐욕 지수 수집 실패: {e}")
    
    # Fallback: CNN Business 크롤링 시도 (세부 지표 포함)
    try:
        url = "https://www.cnn.com/markets/fear-and-greed"
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 종합 점수 파싱
        value = None
        value_elem = soup.select_one('[class*="fear"], [class*="greed"], [id*="fear"], [id*="greed"]')
        if value_elem:
            text = value_elem.get_text(strip=True)
            import re
            numbers = re.findall(r'\d+', text)
            if numbers:
                value = int(numbers[0])
        
        # 세부 지표 파싱 시도 (7가지)
        detail_indicators = []
        detail_selectors = [
            'div[class*="indicator"]',
            '.market-indicator',
            '[data-module="MarketIndicator"]'
        ]
        
        for selector in detail_selectors:
            indicators = soup.select(selector)
            if indicators:
                for indicator in indicators[:7]:  # 최대 7개
                    try:
                        name_elem = indicator.select_one('span, .name, [class*="name"]')
                        value_elem = indicator.select_one('.value, [class*="value"]')
                        if name_elem and value_elem:
                            name = name_elem.get_text(strip=True)
                            value_text = value_elem.get_text(strip=True)
                            if name and value_text:
                                detail_indicators.append(f"{name}: {value_text}")
                    except Exception:
                        continue
                if detail_indicators:
                    break
        
        # 결과 포맷팅
        if value is not None and 0 <= value <= 100:
            classification = "Extreme Fear" if value <= 25 else "Fear" if value <= 45 else "Neutral" if value <= 55 else "Greed" if value <= 75 else "Extreme Greed"
            emoji = "😨" if value <= 25 else "😟" if value <= 45 else "😐" if value <= 55 else "😊" if value <= 75 else "🚀"
            
            result = f"- 공포/탐욕 지수: {value} ({classification}) {emoji}"
            
            # 세부 지표 추가
            if detail_indicators:
                result += "\n  세부 지표:"
                for indicator in detail_indicators[:5]:  # 최대 5개
                    result += f"\n    • {indicator}"
            
            logger.info(f"공포/탐욕 지수 수집 완료 (CNN): {value}, 세부 지표 {len(detail_indicators)}개")
            return result
    except Exception as e:
        logger.debug(f"CNN 공포/탐욕 지수 크롤링 실패: {e}")
    
    return None


def get_economic_calendar(max_retries: int = 3) -> str:
    """
    Investing.com Economic Calendar에서 오늘/내일 발표될 중요 경제 지표 수집
    중요도 3개(⭐⭐⭐) 이상만 수집, 재시도 로직 포함
    
    Args:
        max_retries: 최대 재시도 횟수
    
    Returns:
        포맷팅된 경제 캘린더 텍스트
    """
    logger.info("=== 경제 캘린더 수집 시작 ===")
    
    today = datetime.now()
    tomorrow = today + timedelta(days=1)
    today_str = today.strftime('%Y-%m-%d')
    tomorrow_str = tomorrow.strftime('%Y-%m-%d')
    
    # 재시도 로직
    for attempt in range(max_retries):
        try:
            # Investing.com Economic Calendar
            url = "https://www.investing.com/economic-calendar/"
            
            logger.info(f"경제 캘린더 수집 중 (시도 {attempt + 1}/{max_retries}): {url}")
            
            # 재시도 시 대기 시간
            if attempt > 0:
                wait_time = 2 ** attempt  # Exponential backoff: 2초, 4초, 8초
                logger.info(f"⏳ {wait_time}초 대기 후 재시도...")
                time.sleep(wait_time)
            
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 경제 캘린더 이벤트 파싱
            events = []
            
            # Investing.com의 경제 캘린더 테이블 구조 파싱
            # 여러 가능한 선택자 시도
            event_selectors = [
                'table.ec-table tr[data-event-detail-id]',
                '.js-event-item',
                'tr[data-event-detail-id]',
                'tbody tr',
                '.eventRow'
            ]
            
            for selector in event_selectors:
                event_rows = soup.select(selector)
                if event_rows:
                    for row in event_rows[:20]:  # 더 많이 확인
                        try:
                            # 날짜 추출 및 필터링 (오늘/내일만)
                            date_elem = row.select_one('td.date, .date, [class*="date"]')
                            event_date_str = ""
                            if date_elem:
                                event_date_str = date_elem.get_text(strip=True)
                            
                            # 날짜가 명시되지 않았거나 오늘/내일인 경우만 처리
                            # (Investing.com은 오늘 날짜를 기본으로 표시)
                            is_today_or_tomorrow = (
                                not event_date_str or
                                today_str in event_date_str or
                                tomorrow_str in event_date_str or
                                'today' in event_date_str.lower() or
                                'tomorrow' in event_date_str.lower()
                            )
                            
                            if not is_today_or_tomorrow:
                                continue
                            
                            # 중요도 추출 (별 개수)
                            importance_elem = row.select_one('.importance, .star, [class*="importance"], i[class*="grayFull"]')
                            importance = 0
                            if importance_elem:
                                importance_text = importance_elem.get_text()
                                # 별 개수 또는 클래스에서 중요도 추출
                                importance = importance_text.count('⭐') + importance_text.count('★')
                                # 클래스명에서 중요도 추출 시도
                                if importance == 0:
                                    class_name = importance_elem.get('class', [])
                                    if any('grayFull' in str(c) for c in class_name):
                                        # grayFull 클래스 개수로 중요도 판단
                                        importance = len([c for c in class_name if 'grayFull' in str(c)])
                            
                            # 중요도 3개 이상만 수집
                            if importance >= 3:
                                # 이벤트명 추출
                                event_name_elem = row.select_one('td.event, .event, a[class*="event"]')
                                event_name = event_name_elem.get_text(strip=True) if event_name_elem else ""
                                
                                # 시간 추출
                                time_elem = row.select_one('td.time, .time, [class*="time"]')
                                event_time = time_elem.get_text(strip=True) if time_elem else ""
                                
                                # 국가 추출
                                country_elem = row.select_one('td.flagCur, .flag, [class*="flag"], span[class*="flag"]')
                                country = country_elem.get_text(strip=True) if country_elem else ""
                                
                                if event_name and len(event_name) > 5:
                                    events.append({
                                        'name': event_name,
                                        'time': event_time,
                                        'country': country,
                                        'importance': importance,
                                        'date': event_date_str
                                    })
                        except Exception as e:
                            logger.debug(f"경제 캘린더 이벤트 파싱 실패: {e}")
                            continue
                    
                    if events:
                        break
            
            # 중복 제거 (이벤트명 기준)
            unique_events = []
            seen_names = set()
            for event in events:
                name_lower = event['name'].lower()
                if name_lower not in seen_names:
                    seen_names.add(name_lower)
                    unique_events.append(event)
            
            if unique_events:
                result = "**📅 오늘/내일 중요 경제 지표 일정:**\n\n"
                for i, event in enumerate(unique_events[:5], 1):  # 최대 5개
                    stars = "⭐" * min(event['importance'], 3)  # 최대 3개
                    result += f"{i}. {stars} <b>{event['name']}</b> ({event['country']})\n"
                    if event['time']:
                        result += f"   시간: {event['time']}\n"
                    result += "\n"
                logger.info(f"경제 캘린더 수집 완료: {len(unique_events)}개 이벤트")
                return result
            else:
                result = "**📅 경제 캘린더:**\n오늘/내일 중요 경제 지표 일정 없음"
                logger.info("경제 캘린더: 중요 이벤트 없음")
                return result
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"경제 캘린더 수집 실패 (시도 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                continue
        except Exception as e:
            logger.warning(f"경제 캘린더 파싱 실패 (시도 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                continue
    
    # 모든 시도 실패 시 대체 소스 시도
    logger.warning("Investing.com 크롤링 실패, 대체 소스 시도...")
    return "**📅 경제 캘린더:**\n데이터 수집 실패 (모든 소스 실패)"


def get_seeking_alpha_outlook(max_retries: int = 3) -> str:
    """
    Seeking Alpha Market Outlook 섹션에서 전문가 시장 전망 수집
    재시도 로직 및 Market Strategy 카테고리 필터링 포함
    
    Args:
        max_retries: 최대 재시도 횟수
    
    Returns:
        포맷팅된 시장 전망 텍스트
    """
    logger.info("=== Seeking Alpha 시장 전망 수집 시작 ===")
    
    # 재시도 로직
    for attempt in range(max_retries):
        try:
            # Seeking Alpha Market Outlook - Market Strategy 카테고리
            urls = [
                "https://seekingalpha.com/market-outlook/market-strategy",
                "https://seekingalpha.com/market-outlook",
                "https://seekingalpha.com/news/market-outlook"
            ]
            
            url = urls[0] if attempt == 0 else urls[min(attempt, len(urls) - 1)]
            
            logger.info(f"Seeking Alpha 시장 전망 수집 중 (시도 {attempt + 1}/{max_retries}): {url}")
            
            # 재시도 시 대기 시간
            if attempt > 0:
                wait_time = 2 ** attempt
                logger.info(f"⏳ {wait_time}초 대기 후 재시도...")
                time.sleep(wait_time)
            
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Market Outlook 기사 파싱
            articles = []
            
            # 여러 가능한 선택자 시도
            article_selectors = [
                'article[data-module="ArticleListItem"]',
                '.sa-article-list-item',
                'article',
                '[data-test-id="post-list-item"]',
                '.article-item'
            ]
            
            for selector in article_selectors:
                article_elems = soup.select(selector)
                if article_elems:
                    for article in article_elems[:10]:  # 더 많이 확인
                        try:
                            # 제목 추출
                            title_elem = article.select_one('h3 a, h2 a, h4 a, a[class*="title"], a[data-test-id="post-list-item-title"]')
                            if not title_elem:
                                continue
                            
                            title = title_elem.get_text(strip=True)
                            link = title_elem.get('href', '')
                            if link and not link.startswith('http'):
                                link = f"https://seekingalpha.com{link}"
                            
                            # 요약문 추출
                            summary_elem = article.select_one('p, .summary, [class*="summary"], [data-test-id="post-list-item-summary"]')
                            summary = summary_elem.get_text(strip=True) if summary_elem else ""
                            
                            # Market Strategy 관련 키워드 필터링
                            title_lower = title.lower()
                            summary_lower = summary.lower()
                            combined = f"{title_lower} {summary_lower}"
                            
                            strategy_keywords = [
                                'outlook', 'forecast', 'strategy', 'analysis', 'market view',
                                'investment', 'portfolio', 'sector', 'trend', 'prediction'
                            ]
                            
                            # 키워드 매칭 확인
                            is_strategy_related = any(keyword in combined for keyword in strategy_keywords)
                            
                            if title and len(title) > 10 and is_strategy_related:
                                articles.append({
                                    'title': title,
                                    'summary': summary[:200] if summary else "",
                                    'link': link
                                })
                        except Exception as e:
                            logger.debug(f"Seeking Alpha 기사 파싱 실패: {e}")
                            continue
                    
                    if articles:
                        break
            
            # 중복 제거
            unique_articles = []
            seen_titles = set()
            for article in articles:
                title_lower = article['title'].lower()
                if title_lower not in seen_titles:
                    seen_titles.add(title_lower)
                    unique_articles.append(article)
            
            if unique_articles:
                result = "**📊 전문가 시장 전망 (Seeking Alpha):**\n\n"
                for i, article in enumerate(unique_articles[:5], 1):  # 최대 5개
                    result += f"{i}. <b>{article['title']}</b>\n"
                    if article['summary']:
                        result += f"   {article['summary']}\n"
                    result += "\n"
                logger.info(f"Seeking Alpha 시장 전망 수집 완료: {len(unique_articles)}개")
                return result
            else:
                result = "**📊 전문가 시장 전망:**\n관련 기사 없음"
                logger.info("Seeking Alpha: 관련 기사 없음")
                return result
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"Seeking Alpha 시장 전망 수집 실패 (시도 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                continue
        except Exception as e:
            logger.warning(f"Seeking Alpha 파싱 실패 (시도 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                continue
    
    # 모든 시도 실패
    logger.warning("Seeking Alpha 크롤링 실패 (모든 시도 실패)")
    return "**📊 전문가 시장 전망:**\n데이터 수집 실패"


def get_market_headlines(max_items: int = 10) -> str:
    """
    기존 호환성을 위한 함수 (제목만 수집)
    새로운 get_market_news_with_context() 사용 권장
    """
    return get_market_news_with_context(max_items)


def translate_headlines(headlines_text: str, ai_researcher) -> str:
    """
    뉴스 헤드라인을 한글로 번역 (AI 사용)
    제목+요약 형식도 지원
    
    Args:
        headlines_text: 원문 헤드라인 텍스트
        ai_researcher: AIResearcher 인스턴스
    
    Returns:
        원문 + 한글 번역이 포함된 텍스트
    """
    if "뉴스 데이터 수집 불가" in headlines_text:
        return headlines_text
    
    try:
        # 헤드라인만 추출
        lines = headlines_text.split('\n')
        headlines_only = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('**') and not line.startswith('요약:'):
                # 번호와 제목만 추출
                if line.startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.', '10.')):
                    # HTML 태그 제거
                    import re
                    clean_line = re.sub(r'<[^>]+>', '', line)
                    headlines_only.append(clean_line)
        
        if not headlines_only:
            return headlines_text
        
        # 번역 요청
        translation_prompt = f"""아래는 영어 뉴스 헤드라인입니다. 각 헤드라인을 한글로 번역해주세요.

원문:
{chr(10).join(headlines_only)}

요구사항:
1. 각 헤드라인을 정확하게 한글로 번역
2. 원문과 번역을 함께 표시 (원문\n   번역 형식)
3. 번호는 유지
4. 가독성을 높이기 위해 명확하게 포맷팅

출력 형식:
1. [원문]\n   → [한글 번역]
2. [원문]\n   → [한글 번역]
...
"""
        
        translated = ai_researcher._call_ai(translation_prompt)
        
        # 결과 포맷팅 (HTML 태그로 가독성 향상)
        lines = translated.split('\n')
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # 영어 제목 앞뒤의 '**' 제거
            line = line.replace('**', '')
            # 번호가 있는 줄은 그대로, 번역 줄은 들여쓰기
            if line.startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.', '10.')):
                formatted_lines.append(f"<b>{line}</b>")
            elif line.startswith('→'):
                formatted_lines.append(f"   <i>{line}</i>")
            else:
                formatted_lines.append(line)
        
        result = "**주요 시장 뉴스 헤드라인:**\n" + "\n".join(formatted_lines)
        return result
        
    except Exception as e:
        logger.warning(f"뉴스 헤드라인 번역 실패: {e}, 원문 그대로 사용")
        return headlines_text

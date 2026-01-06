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

# User-Agent 헤더 (봇 차단 방지) - 최신 Chrome 브라우저
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,ko;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Cache-Control': 'max-age=0',
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
            
            response = requests.get(url, headers=HEADERS, timeout=15)
            
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
                        except:
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
                    
                    if len(all_articles) >= 10:
                        break
                        
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


def translate_headlines(headlines_text: str, ai_researcher) -> str:
    """
    뉴스 헤드라인을 한글로 번역 (AI 사용)
    제목+요약 형식도 지원
    한국어 제목은 번역하지 않고 그대로 유지
    
    Args:
        headlines_text: 원문 헤드라인 텍스트
        ai_researcher: AIResearcher 인스턴스
    
    Returns:
        원문 + 한글 번역이 포함된 텍스트 (한국어는 원문만)
    """
    if "뉴스 데이터 수집 불가" in headlines_text:
        return headlines_text
    
    try:
        import re
        
        # 헤드라인만 추출 (번호와 제목)
        lines = headlines_text.split('\n')
        headlines_data = []  # (번호, 제목, 한국어 여부) 튜플 리스트
        
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
                        is_korean = is_korean_text(title)
                        headlines_data.append((number, title, is_korean))
        
        if not headlines_data:
            return headlines_text
        
        # 영어 제목만 필터링
        english_headlines = [(num, title) for num, title, is_kr in headlines_data if not is_kr]
        korean_headlines = [(num, title) for num, title, is_kr in headlines_data if is_kr]
        
        # 영어 제목만 번역
        translated_results = {}  # {번호: 번역문}
        if english_headlines:
            # 번호와 제목을 함께 전달하여 매칭 용이하게
            english_titles_with_num = [f"{num}. {title}" for num, title in english_headlines]
            
            translation_prompt = f"""아래는 영어 뉴스 헤드라인입니다. 각 헤드라인을 한글로 번역해주세요.

원문:
{chr(10).join(english_titles_with_num)}

요구사항:
1. 각 헤드라인을 정확하게 한글로 번역
2. 번호를 유지하고 원문과 번역을 함께 표시
3. 출력 형식을 정확히 따르세요

출력 형식:
1. [원문 제목]
   → [한글 번역]

2. [원문 제목]
   → [한글 번역]
...
"""
            
            translated_text, _ = ai_researcher._call_ai(translation_prompt)
            
            # 번역 결과 파싱 (번호로 매칭)
            translated_lines = translated_text.split('\n')
            current_number = None
            for line in translated_lines:
                line = line.strip()
                if not line:
                    continue
                
                # 번호 추출
                num_match = re.match(r'^(\d+)\.', line)
                if num_match:
                    current_number = num_match.group(1)
                elif line.startswith('→') and current_number:
                    # 번역문
                    translation = line.replace('→', '').strip()
                    translated_results[current_number] = translation
                    current_number = None
        
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
        all_numbers = sorted(set([num for num, _, _ in headlines_data]), key=int)
        
        for number in all_numbers:
            # 해당 번호의 헤드라인 찾기
            headline_info = next((num, title, is_kr) for num, title, is_kr in headlines_data if num == number)
            _, title, is_korean = headline_info
            
            if is_korean:
                # 한국어는 원문만 표시 (번역 생략)
                formatted_lines.append(f"<b>{number}. {title}</b>")
                if number in summary_map:
                    formatted_lines.append(f"   요약: {summary_map[number]}")
            else:
                # 영어는 원문 + 번역 표시
                formatted_lines.append(f"<b>{number}. {title}</b>")
                if number in translated_results:
                    translation = translated_results[number]
                    formatted_lines.append(f"   <i>→ {translation}</i>")
                if number in summary_map:
                    formatted_lines.append(f"   요약: {summary_map[number]}")
            
            formatted_lines.append("")  # 빈 줄
        
        result = "\n".join(formatted_lines)
        logger.info(f"뉴스 번역 완료: 영어 {len(english_headlines)}개, 한국어 {len(korean_headlines)}개 (한국어는 번역 생략)")
        return result
        
    except Exception as e:
        logger.warning(f"뉴스 헤드라인 번역 실패: {e}, 원문 그대로 사용")
        return headlines_text

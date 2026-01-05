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


def get_market_news_with_context(max_items: int = 10) -> str:
    """
    뉴스 제목과 요약문을 함께 수집하여 포맷팅된 텍스트로 반환
    
    Args:
        max_items: 최대 수집할 뉴스 개수
    
    Returns:
        포맷팅된 뉴스 텍스트
    """
    logger.info("=== 시장 뉴스 수집 시작 (제목+요약) ===")
    
    all_news = []
    
    # Yahoo Finance 수집
    yahoo_news = get_yahoo_finance_news(max_items=max_items)
    if yahoo_news:
        all_news.extend(yahoo_news)
    
    # 네이버 금융 수집
    naver_news = get_naver_finance_news(max_items=max_items)
    if naver_news:
        all_news.extend(naver_news)
    
    # 중복 제거 (제목 기준)
    unique_news = []
    seen_titles = set()
    for news in all_news:
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
        logger.info(f"뉴스 수집 완료: {len(unique_news)}개 (제목+요약)")
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
    공포/탐욕 지수 (Fear & Greed Index) 수집
    CNN Business 또는 Alternative.me에서 수집 시도
    
    Returns:
        포맷팅된 공포/탐욕 지수 문자열 또는 None
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
    
    # Fallback: CNN Business 크롤링 시도
    try:
        url = "https://www.cnn.com/markets/fear-and-greed"
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # CNN Fear & Greed Index 파싱 시도
        value_elem = soup.select_one('[class*="fear"], [class*="greed"], [id*="fear"], [id*="greed"]')
        if value_elem:
            text = value_elem.get_text(strip=True)
            # 숫자 추출
            import re
            numbers = re.findall(r'\d+', text)
            if numbers:
                value = int(numbers[0])
                if 0 <= value <= 100:
                    classification = "Extreme Fear" if value <= 25 else "Fear" if value <= 45 else "Neutral" if value <= 55 else "Greed" if value <= 75 else "Extreme Greed"
                    emoji = "😨" if value <= 25 else "😟" if value <= 45 else "😐" if value <= 55 else "😊" if value <= 75 else "🚀"
                    result = f"- 공포/탐욕 지수: {value} ({classification}) {emoji}"
                    logger.info(f"공포/탐욕 지수 수집 완료 (CNN): {value}")
                    return result
    except Exception as e:
        logger.debug(f"CNN 공포/탐욕 지수 크롤링 실패: {e}")
    
    return None


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

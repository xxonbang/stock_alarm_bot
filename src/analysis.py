"""
기술적 분석 모듈
yfinance를 사용하여 주가 데이터 수집 및 기간별 수익률 계산
"""
import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
import pytz

logger = logging.getLogger(__name__)


def get_stock_data(ticker: str, period: str = "1y") -> Optional[yf.Ticker]:
    """
    주식 티커 데이터를 가져옴
    
    Args:
        ticker: 주식 티커 심볼 (예: 'AAPL', '005930.KS')
        period: 데이터 기간 ('1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max')
    
    Returns:
        yf.Ticker 객체 또는 None (실패 시)
    """
    try:
        stock = yf.Ticker(ticker)
        # 데이터 존재 여부 확인
        info = stock.info
        if not info or len(info) == 0:
            logger.warning(f"{ticker}: 정보를 가져올 수 없습니다.")
            return None
        return stock
    except Exception as e:
        logger.error(f"{ticker} 데이터 조회 실패: {e}")
        return None


def get_current_price(ticker: str) -> Optional[float]:
    """
    현재 주가를 가져옴
    
    Args:
        ticker: 주식 티커 심볼
    
    Returns:
        현재가 또는 None (실패 시)
    """
    try:
        stock = get_stock_data(ticker)
        if stock is None:
            return None
        
        # 실시간 데이터 시도
        data = stock.history(period="1d", interval="1m")
        if not data.empty:
            return float(data['Close'].iloc[-1])
        
        # 실시간 데이터가 없으면 최신 종가 사용
        info = stock.info
        if 'currentPrice' in info:
            return float(info['currentPrice'])
        elif 'regularMarketPrice' in info:
            return float(info['regularMarketPrice'])
        elif 'previousClose' in info:
            return float(info['previousClose'])
        
        logger.warning(f"{ticker}: 현재가를 가져올 수 없습니다.")
        return None
    except Exception as e:
        logger.error(f"{ticker} 현재가 조회 실패: {e}")
        return None


def get_historical_price(ticker: str, days_ago: int) -> Optional[float]:
    """
    과거 특정 시점의 주가를 가져옴 (거래일 기준)
    
    Args:
        ticker: 주식 티커 심볼
        days_ago: 며칠 전 거래일 데이터를 가져올지 (거래일 기준, 휴장일 제외)
    
    Returns:
        과거 주가 또는 None (실패 시)
    """
    try:
        stock = get_stock_data(ticker)
        if stock is None:
            return None
        
        # 충분한 기간의 데이터 가져오기
        # 1년 데이터를 요청하는 경우도 있으므로 충분히 가져오기
        if days_ago <= 30:
            period = max(days_ago * 2, 60)
        elif days_ago <= 180:
            period = max(days_ago * 2, 365)
        else:
            period = max(days_ago * 2, 730)  # 2년치 데이터
        
        data = stock.history(period=f"{period}d")
        
        if data.empty:
            logger.warning(f"{ticker}: 과거 데이터가 없습니다.")
            return None
        
        # 데이터 인덱스는 이미 거래일만 포함되어 있음
        # 가장 최근 데이터가 마지막 인덱스에 있음
        # days_ago 거래일 전의 데이터를 가져오기
        # 예: days_ago=1이면 1거래일 전 (어제 거래일)
        #     days_ago=2이면 2거래일 전 (그저께 거래일)
        
        if len(data) <= days_ago:
            # 데이터가 충분하지 않으면 가장 오래된 데이터 사용
            logger.warning(f"{ticker}: {days_ago}거래일 전 데이터가 없어 가장 오래된 데이터 사용 ({len(data)}거래일)")
            return float(data['Close'].iloc[0])
        
        # 거래일 기준으로 인덱스 계산
        # data.index[-1] = 가장 최근 거래일
        # data.index[-2] = 1거래일 전
        # data.index[-3] = 2거래일 전
        # 따라서 data.index[-(days_ago+1)] = days_ago 거래일 전
        target_index = -(days_ago + 1)
        
        if abs(target_index) > len(data):
            # 인덱스가 범위를 벗어나면 가장 오래된 데이터 사용
            logger.warning(f"{ticker}: {days_ago}거래일 전 데이터가 없어 가장 오래된 데이터 사용 ({len(data)}거래일)")
            return float(data['Close'].iloc[0])
        
        return float(data['Close'].iloc[target_index])
        
    except Exception as e:
        logger.error(f"{ticker} {days_ago}일 전 가격 조회 실패: {e}")
        return None


def calculate_returns(ticker: str) -> Dict:
    """
    기간별 수익률을 계산
    
    Args:
        ticker: 주식 티커 심볼
    
    Returns:
        {
            'ticker': ticker,
            'current_price': 현재가,
            'returns': {
                '1D': 수익률%,
                '2D': 수익률%,
                ...
            }
        }
    """
    result = {
        'ticker': ticker,
        'current_price': None,
        'returns': {}
    }
    
    # 현재가 조회
    current_price = get_current_price(ticker)
    if current_price is None:
        result['current_price'] = "데이터 없음"
        return result
    
    result['current_price'] = current_price
    
    # 기간별 수익률 계산
    periods = {
        '1D': 1,
        '2D': 2,
        '3D': 3,
        '1W': 7,
        '1M': 30,
        '2M': 60,
        '3M': 90,
        '6M': 180,
        '1Y': 365
    }
    
    for period_name, days in periods.items():
        try:
            past_price = get_historical_price(ticker, days)
            if past_price is None or past_price == 0:
                result['returns'][period_name] = "N/A"
            else:
                return_pct = ((current_price - past_price) / past_price) * 100
                result['returns'][period_name] = round(return_pct, 2)
        except Exception as e:
            logger.error(f"{ticker} {period_name} 수익률 계산 실패: {e}")
            result['returns'][period_name] = "오류"
    
    return result


def analyze_all_tickers(tickers: List[str]) -> List[Dict]:
    """
    모든 티커에 대해 분석 수행
    
    Args:
        tickers: 분석할 티커 리스트
    
    Returns:
        분석 결과 리스트
    """
    results = []
    for ticker in tickers:
        logger.info(f"분석 중: {ticker}")
        result = calculate_returns(ticker)
        results.append(result)
    return results


def get_stock_summary_by_category(
    possession_domestic: List[str],
    possession_overseas: List[str],
    interest_domestic: List[str],
    interest_overseas: List[str]
) -> Dict[str, str]:
    """
    카테고리별로 주가 데이터를 수집하고 요약 텍스트로 변환
    카테고리별로 구분하여 표시
    
    Args:
        possession_domestic: 보유 종목 (국내)
        possession_overseas: 보유 종목 (해외)
        interest_domestic: 관심 종목 (국내)
        interest_overseas: 관심 종목 (해외)
    
    Returns:
        주가 요약 텍스트 문자열 (카테고리별 구분)
    """
    logger.info("=== 주가 데이터 수집 및 요약 시작 (카테고리별) ===")
    
    # 카테고리별 결과 저장
    category_results = {}
    
    # 1. 보유 종목 (국내)
    if possession_domestic:
        logger.info(f"보유 종목 (국내) 분석: {len(possession_domestic)}개")
        results = analyze_all_tickers(possession_domestic)
        category_results['possession_domestic'] = results
    
    # 2. 보유 종목 (해외)
    if possession_overseas:
        logger.info(f"보유 종목 (해외) 분석: {len(possession_overseas)}개")
        results = analyze_all_tickers(possession_overseas)
        category_results['possession_overseas'] = results
    
    # 3. 관심 종목 (국내)
    if interest_domestic:
        logger.info(f"관심 종목 (국내) 분석: {len(interest_domestic)}개")
        results = analyze_all_tickers(interest_domestic)
        category_results['interest_domestic'] = results
    
    # 4. 관심 종목 (해외)
    if interest_overseas:
        logger.info(f"관심 종목 (해외) 분석: {len(interest_overseas)}개")
        results = analyze_all_tickers(interest_overseas)
        category_results['interest_overseas'] = results
    
    # 카테고리별로 포맷팅
    return format_stock_summary_by_category(category_results)


def format_stock_summary_by_category(category_results: Dict) -> Dict[str, str]:
    """
    카테고리별 주가 결과를 포맷팅하여 각 카테고리별로 개별 메시지 반환
    
    Args:
        category_results: 카테고리별 분석 결과 딕셔너리
    
    Returns:
        카테고리별 포맷팅된 메시지 딕셔너리
        {
            'possession_domestic': '메시지',
            'possession_overseas': '메시지',
            'interest_domestic': '메시지',
            'interest_overseas': '메시지'
        }
    """
    # 티커 이름 매핑
    ticker_names = {
        # 국내 보유
        '360200.KS': 'ACE 미국S&P500',
        '379810.KS': 'KODEX 미국나스닥100',
        '484320.KS': 'KODEX 미국AI전력핵심인프라',
        '411060.KS': 'ACE KRX금현물',
        # 국내 관심
        '449170.KS': 'TIGER KOFR금리액티브',
        '005930.KS': '삼성전자',
        '000660.KS': 'SK하이닉스',
        # 해외 관심
        'TSLA': '테슬라',
        'NVDA': '엔비디아',
        'AAPL': '애플',
        'GOOGL': '구글',
        'MSFT': '마이크로소프트',
        'SPY': '미국S&P500',
        'QQQ': '미국나스닥100',
        'VTI': '미국주식시장지수펀드',
        'GLD': '금 (SPDR Gold Trust)',
        'SLV': '은 (iShares Silver Trust)',
        'BTC-USD': '비트코인',
        'ETH-USD': '이더리움',
    }
    
    # 카테고리별 메시지 저장
    category_messages = {}
    
    # 카테고리 순서대로 처리
    categories = [
        ('possession_domestic', '<b>💼 보유 종목 (국내)</b>'),
        ('possession_overseas', '<b>💼 보유 종목 (해외)</b>'),
        ('interest_domestic', '<b>👀 관심 종목 (국내)</b>'),
        ('interest_overseas', '<b>👀 관심 종목 (해외)</b>'),
    ]
    
    for category_key, category_title in categories:
        if category_key in category_results and category_results[category_key]:
            results = category_results[category_key]
            summary_parts = [category_title]
            
            for result in results:
                ticker = result.get('ticker', 'Unknown')
                current_price = result.get('current_price', 'N/A')
                returns = result.get('returns', {})
                
                # 티커 한글 이름
                ticker_name = ticker_names.get(ticker, ticker)
                
                # 가격 포맷팅 (티커 기준으로 통화 결정)
                if isinstance(current_price, (int, float)):
                    # 한국 주식/ETF는 원화, 그 외는 달러
                    if 'KS' in ticker or 'KQ' in ticker:
                        # 한국 주식/ETF: 원화
                        price_str = f"<b>{current_price:,.0f}원</b>"
                    else:
                        # 해외 주식/ETF/암호화폐: 달러
                        if current_price >= 1:
                            price_str = f"<b>${current_price:,.2f}</b>"
                        else:
                            price_str = f"<b>${current_price:.4f}</b>"
                else:
                    price_str = str(current_price)
                
                # 주요 수익률 계산
                period_mapping = {
                    '24h': ('1D', '1일'),
                    '2d': ('2D', '2일'),
                    '3d': ('3D', '3일'),
                    '7d': ('1W', '1주'),
                    '1m': ('1M', '1개월'),
                    '2m': ('2M', '2개월'),
                    '3m': ('3M', '3개월'),
                    '6m': ('6M', '6개월'),
                    '1y': ('1Y', '1년')
                }
                
                returns_parts = []
                for period_key, (period_code, period_label) in period_mapping.items():
                    if period_code in returns:
                        val = returns[period_code]
                        if isinstance(val, (int, float)):
                            arrow = "📈" if val >= 0 else "📉"
                            sign = "+" if val >= 0 else ""
                            returns_parts.append(f"{arrow} {period_label}: {sign}{val:.2f}%")
                
                if returns_parts:
                    returns_str = "\n    " + "\n    ".join(returns_parts)
                else:
                    returns_str = "N/A"
                
                # 종목명과 티커명 강조 효과
                summary_line = f"📊 <b>{ticker_name}</b> <code>({ticker})</code>\n   현재가: <b>{price_str}</b>\n   변동률:{returns_str}"
                summary_parts.append(summary_line)
            
            # 카테고리별 메시지 생성
            category_messages[category_key] = "\n".join(summary_parts)
    
    total_count = sum(len(results) for results in category_results.values() if results)
    logger.info(f"주가 요약 텍스트 생성 완료: {total_count}개 종목 (카테고리별 개별 메시지)")
    
    return category_messages


def get_stock_summary(tickers: List[str]) -> str:
    """
    주가 데이터를 수집하고 요약 텍스트로 변환
    Python 내부에서 모든 계산을 수행하여 AI에게는 완성된 텍스트만 전달
    
    Args:
        tickers: 분석할 티커 리스트
    
    Returns:
        주가 요약 텍스트 문자열
    """
    logger.info("=== 주가 데이터 수집 및 요약 시작 ===")
    
    results = analyze_all_tickers(tickers)
    summary_lines = []
    
    # 티커 이름 매핑 (한글 이름 추가)
    ticker_names = {
        # 국내 보유
        '360200.KS': 'ACE 미국S&P500',
        '379810.KS': 'KODEX 미국나스닥100',
        '484320.KS': 'KODEX 미국AI전력핵심인프라',
        '411060.KS': 'ACE KRX금현물',
        # 국내 관심
        '449170.KS': 'TIGER KOFR금리액티브',
        '005930.KS': '삼성전자',
        '000660.KS': 'SK하이닉스',
        # 해외 관심
        'TSLA': '테슬라',
        'NVDA': '엔비디아',
        'AAPL': '애플',
        'GOOGL': '구글',
        'MSFT': '마이크로소프트',
        'SPY': '미국S&P500',
        'QQQ': '미국나스닥100',
        'VTI': '미국주식시장지수펀드',
        'IAU': '금',
        'GLD': '금',
        'SLV': '은',
        'XAG': '은',
        'XAU': '금',
        'BTC-USD': '비트코인',
        'ETH-USD': '이더리움',
    }
    
    for result in results:
        ticker = result.get('ticker', 'Unknown')
        current_price = result.get('current_price', 'N/A')
        returns = result.get('returns', {})
        
        # 티커 한글 이름
        ticker_name = ticker_names.get(ticker, ticker)
        
        # 가격 포맷팅 (티커 기준으로 통화 결정)
        if isinstance(current_price, (int, float)):
            # 한국 주식/ETF는 원화, 그 외는 달러
            if 'KS' in ticker or 'KQ' in ticker:
                # 한국 주식/ETF: 원화
                price_str = f"<b>{current_price:,.0f}원</b>"
            else:
                # 해외 주식/ETF/암호화폐: 달러
                if current_price >= 1:
                    price_str = f"<b>${current_price:,.2f}</b>"
                else:
                    price_str = f"<b>${current_price:.4f}</b>"
        else:
            price_str = str(current_price)
        
        # 주요 수익률 계산 (Python 내부 연산 완료)
        # [24h, 2d, 3d, 7d, 1m, 2m, 3m, 6m, 1y]
        period_mapping = {
            '24h': ('1D', '1일'),
            '2d': ('2D', '2일'),
            '3d': ('3D', '3일'),
            '7d': ('1W', '1주'),
            '1m': ('1M', '1개월'),
            '2m': ('2M', '2개월'),
            '3m': ('3M', '3개월'),
            '6m': ('6M', '6개월'),
            '1y': ('1Y', '1년')
        }
        
        # 가독성 향상을 위한 포맷팅
        returns_parts = []
        for period_key, (period_code, period_label) in period_mapping.items():
            if period_code in returns:
                val = returns[period_code]
                if isinstance(val, (int, float)):
                    arrow = "📈" if val >= 0 else "📉"
                    sign = "+" if val >= 0 else ""
                    returns_parts.append(f"{arrow} {period_label}: {sign}{val:.2f}%")
        
        # 가독성 향상: 여러 줄로 표시
        if returns_parts:
            returns_str = "\n    " + "\n    ".join(returns_parts)
        else:
            returns_str = "N/A"
        
        # 직관적이고 가독성 높은 요약 라인 생성 (HTML 강조 효과)
        # 종목명과 티커명에 강조 효과 추가
        summary_line = f"📊 <b>{ticker_name}</b> <code>({ticker})</code>\n   현재가: <b>{price_str}</b>\n   변동률:{returns_str}"
        summary_lines.append(summary_line)
    
    result_text = "**주가 현황:**\n" + "\n".join(summary_lines)
    logger.info(f"주가 요약 텍스트 생성 완료: {len(summary_lines)}개 종목")
    
    return result_text



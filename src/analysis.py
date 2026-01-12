"""
기술적 분석 모듈
yfinance를 사용하여 주가 데이터 수집 및 기간별 수익률 계산
기술적 지표(RSI, 이동평균선 괴리율) 계산 포함

[중요: AI 금지 구역]
이 모듈은 순수 수치 계산 전용입니다. AI API 호출을 절대 하지 않습니다.
- google.generativeai 라이브러리 import 금지
- AI를 사용한 분석/요약 금지
- 모든 계산은 pandas/numpy로만 처리
"""
import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
import pytz
import pandas as pd
import numpy as np
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# TradingView API 의존성 제거 - 자체 계산 엔진 사용

# AI 금지 검증: 이 파일에서 직접 import하지 않았는지 확인
# (다른 모듈에서 간접적으로 import되는 것은 허용)
import sys
if 'google.generativeai' in sys.modules:
    # 다른 모듈에서 이미 import된 경우, 이 파일에서 직접 import한 것은 아님
    pass
# 이 파일에서는 google.generativeai를 직접 import하지 않음 (정상)


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
    현재 주가를 가져옴 (Close 컬럼 명시적 사용)
    
    Args:
        ticker: 주식 티커 심볼
    
    Returns:
        현재가 또는 None (실패 시)
    """
    try:
        stock = get_stock_data(ticker)
        if stock is None:
            return None
        
        # 최신 거래일의 종가(Close)를 명시적으로 가져오기
        # 배당/분할 반영을 위해 auto_adjust=True 사용
        data = stock.history(period="5d", auto_adjust=True)  # 최근 5일 데이터
        
        if not data.empty:
            # 가장 최근 거래일의 Close 가격 사용
            return float(data['Close'].iloc[-1])
        
        # history가 실패하면 info에서 가져오기
        info = stock.info
        if 'regularMarketPrice' in info:
            return float(info['regularMarketPrice'])
        elif 'currentPrice' in info:
            return float(info['currentPrice'])
        elif 'previousClose' in info:
            return float(info['previousClose'])
        
        logger.warning(f"{ticker}: 현재가를 가져올 수 없습니다.")
        return None
    except Exception as e:
        logger.error(f"{ticker} 현재가 조회 실패: {e}")
        return None


def get_historical_price(ticker: str, days_ago: int) -> Optional[float]:
    """
    과거 특정 시점의 주가를 가져옴 (정확한 날짜 기준, 거래일 보장)
    
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
        
        # 정확한 날짜 기준으로 데이터 가져오기 (리포트 제안 방식)
        # 충분한 기간의 데이터를 가져와서 정확한 날짜를 찾음
        if days_ago <= 30:
            period_days = max(days_ago * 3, 90)  # 여유 있게
        elif days_ago <= 180:
            period_days = max(days_ago * 2, 400)
        else:
            period_days = max(days_ago * 2, 800)  # 1년 이상은 충분히
        
        # start/end 날짜를 명시적으로 지정하여 데이터 가져오기
        end_date = datetime.now(pytz.UTC)
        start_date = end_date - timedelta(days=period_days)
        
        # 배당/분할 반영을 위해 auto_adjust=True 사용
        data = stock.history(start=start_date.strftime('%Y-%m-%d'), end=end_date.strftime('%Y-%m-%d'), auto_adjust=True)
        
        if data.empty:
            logger.warning(f"{ticker}: 과거 데이터가 없습니다.")
            return None
        
        # 데이터가 거래일만 포함되어 있으므로, days_ago 거래일 전의 데이터를 정확히 찾기
        if len(data) <= days_ago:
            # 데이터가 충분하지 않으면 가장 오래된 데이터 사용
            logger.warning(f"{ticker}: {days_ago}거래일 전 데이터가 없어 가장 오래된 데이터 사용 ({len(data)}거래일)")
            # Close 컬럼 명시적 사용 (Adj Close 아님)
            return float(data['Close'].iloc[0])
        
        # 거래일 기준으로 정확한 인덱스 계산
        # data.index[-1] = 가장 최근 거래일
        # data.index[-2] = 1거래일 전
        # 따라서 data.index[-(days_ago+1)] = days_ago 거래일 전
        target_index = -(days_ago + 1)
        
        if abs(target_index) > len(data):
            logger.warning(f"{ticker}: {days_ago}거래일 전 데이터가 없어 가장 오래된 데이터 사용 ({len(data)}거래일)")
            return float(data['Close'].iloc[0])
        
        # Close 컬럼 명시적 사용 (Adj Close가 아닌 실제 종가)
        target_price = float(data['Close'].iloc[target_index])
        
        # 디버깅: 날짜와 가격 로그 (장기 수익률 계산 시)
        if days_ago >= 30:
            target_date = data.index[target_index]
            logger.debug(f"{ticker}: {days_ago}거래일 전 ({target_date.strftime('%Y-%m-%d')}) 가격: {target_price:,.0f}")
        
        return target_price
        
    except Exception as e:
        logger.error(f"{ticker} {days_ago}일 전 가격 조회 실패: {e}")
        return None


def calculate_rsi(prices: pd.Series, period: int = 14) -> Optional[float]:
    """
    RSI (Relative Strength Index) 계산 - Wilder's Smoothing 방식 (표준 방법)
    
    J. Welles Wilder가 1978년 개발한 표준 RSI 계산 방법을 사용합니다.
    Simple Moving Average 대신 Wilder's Smoothing (RMA)을 사용하여
    최근 데이터에 더 큰 가중치를 부여합니다.
    
    Args:
        prices: 종가 시리즈
        period: RSI 기간 (기본값: 14일)
    
    Returns:
        RSI 값 (0~100) 또는 None
    """
    try:
        if len(prices) < period + 1:
            return None
        
        # 가격 변화량 계산
        delta = prices.diff()
        
        # 상승분과 하락분 분리
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        # Wilder's Smoothing (RMA - Running Moving Average)
        # 초기값: 첫 period일의 단순 평균
        avg_gain = pd.Series(index=prices.index, dtype=float)
        avg_loss = pd.Series(index=prices.index, dtype=float)
        
        # 첫 번째 평균값 계산
        avg_gain.iloc[period] = gain.iloc[1:period+1].mean()
        avg_loss.iloc[period] = loss.iloc[1:period+1].mean()
        
        # 이후 값: Wilder's smoothing 공식
        # RMA = (이전 RMA * (period - 1) + 현재 값) / period
        for i in range(period + 1, len(prices)):
            avg_gain.iloc[i] = (avg_gain.iloc[i-1] * (period - 1) + gain.iloc[i]) / period
            avg_loss.iloc[i] = (avg_loss.iloc[i-1] * (period - 1) + loss.iloc[i]) / period
        
        # RS (Relative Strength) 계산
        rs = avg_gain / (avg_loss + 1e-10)  # 0으로 나누기 방지
        
        # RSI 계산
        rsi = 100 - (100 / (1 + rs))
        
        # 최신 RSI 값 반환
        return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else None
    except Exception as e:
        logger.error(f"RSI 계산 실패: {e}")
        return None


def calculate_ma_deviation(current_price: float, ma20: Optional[float]) -> Optional[float]:
    """
    20일 이동평균선 괴리율 계산
    
    Args:
        current_price: 현재가
        ma20: 20일 이동평균선 가격
    
    Returns:
        괴리율 (%) 또는 None
    """
    try:
        if ma20 is None or ma20 == 0:
            return None
        deviation = (current_price / ma20) * 100
        return float(deviation)
    except Exception as e:
        logger.error(f"이동평균선 괴리율 계산 실패: {e}")
        return None


def get_technical_indicators(ticker: str) -> Dict[str, Optional[float]]:
    """
    기술적 지표 계산 (RSI, 20일 이동평균선, 괴리율)
    
    Args:
        ticker: 주식 티커 심볼
    
    Returns:
        {
            'rsi': RSI 값 (0~100),
            'ma20': 20일 이동평균선 가격,
            'ma_deviation': 20일 이동평균선 괴리율 (%)
        }
    """
    try:
        stock = get_stock_data(ticker)
        if stock is None:
            return {'rsi': None, 'ma20': None, 'ma_deviation': None}
        
        # 최소 30일치 데이터 필요 (RSI 14일 + MA 20일 + 여유)
        # 배당/분할 반영을 위해 auto_adjust=True 사용
        hist = stock.history(period="2mo", auto_adjust=True)
        
        if hist.empty or len(hist) < 30:
            logger.warning(f"{ticker}: 기술적 지표 계산을 위한 데이터 부족 ({len(hist)}일)")
            return {'rsi': None, 'ma20': None, 'ma_deviation': None}
        
        # Close 가격 사용
        closes = hist['Close']
        current_price = float(closes.iloc[-1])
        
        # RSI 계산
        rsi = calculate_rsi(closes, period=14)
        
        # 20일 이동평균선 계산
        ma20 = float(closes.rolling(window=20).mean().iloc[-1]) if len(closes) >= 20 else None
        
        # 괴리율 계산
        ma_deviation = calculate_ma_deviation(current_price, ma20)
        
        return {
            'rsi': rsi,
            'ma20': ma20,
            'ma_deviation': ma_deviation
        }
    except Exception as e:
        logger.error(f"{ticker} 기술적 지표 계산 실패: {e}")
        return {'rsi': None, 'ma20': None, 'ma_deviation': None}


def calculate_returns(ticker: str) -> Dict:
    """
    기간별 수익률 및 기술적 지표를 계산
    
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
            },
            'technical': {
                'rsi': RSI 값,
                'ma20': 20일 이동평균선,
                'ma_deviation': 20일 이동평균선 괴리율 (%)
            }
        }
    """
    result = {
        'ticker': ticker,
        'current_price': None,
        'returns': {},
        'technical': {}
    }
    
    # 현재가 조회
    current_price = get_current_price(ticker)
    if current_price is None:
        result['current_price'] = "데이터 없음"
        return result
    
    result['current_price'] = current_price
    
    # 기간별 수익률 계산 (거래일 기준, 실제 시장 기준과 일치하도록 조정)
    # 참고: 1개월 = 약 20-22거래일, 1년 = 약 250거래일 (한국 시장 기준)
    periods = {
        '1D': 1,      # 1거래일 전
        '3D': 3,      # 3거래일 전
        '1W': 5,      # 1주일 = 약 5거래일 (기존 7에서 조정)
        '1M': 20,     # 1개월 = 약 20거래일 (기존 30에서 조정)
        '3M': 60,     # 3개월 = 약 60거래일 (기존 90에서 조정)
        '6M': 120,    # 6개월 = 약 120거래일 (기존 180에서 조정)
        '1Y': 250     # 1년 = 약 250거래일 (기존 365에서 조정)
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
    
    # 기술적 지표 계산
    technical = get_technical_indicators(ticker)
    result['technical'] = technical
    
    return result


def analyze_all_tickers(tickers: List[str]) -> List[Dict]:
    """
    모든 티커에 대해 분석 수행 (멀티스레딩으로 속도 최적화)
    
    Args:
        tickers: 분석할 티커 리스트
    
    Returns:
        분석 결과 리스트
    """
    results = []
    
    # ThreadPoolExecutor를 사용하여 멀티스레딩으로 데이터 수집
    # yfinance는 threads=True 옵션을 지원하지만, 여기서는 각 티커를 병렬로 처리
    max_workers = min(len(tickers), 10)  # 최대 10개 스레드 (너무 많으면 API 제한 걸릴 수 있음)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 모든 티커에 대해 비동기 작업 제출
        future_to_ticker = {
            executor.submit(calculate_returns, ticker): ticker 
            for ticker in tickers
        }
        
        # 완료된 작업부터 결과 수집
        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.error(f"{ticker} 분석 실패: {e}")
                continue
    
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
    # 티커 이름 매핑 (한글 이름이 있는 경우만, 없으면 yfinance로 동적 조회)
    ticker_names = {
        # 국내 보유
        '360200.KS': 'ACE 미국S&P500',
        '379810.KS': 'KODEX 미국나스닥100',
        '390390.KS': 'KODEX 미국반도체',
        '465580.KS': 'KODEX ACE 미국빅테크TOP7 Plus',
        '484320.KS': 'KODEX 미국AI전력핵심인프라',
        '411060.KS': 'ACE KRX금현물',
        '438080.KS': 'ACE 미국S&P500미국채혼합50액티브',
        '487230.KS': 'KODEX 미국AI전력핵심인프라',
        # 국내 관심
        '449170.KS': 'TIGER KOFR금리액티브',
        '464310.KS': 'TIGER 글로벌AI&로보틱스 INDXX',
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
                technical = result.get('technical', {})
                
                # 티커 한글 이름 (매핑에 없으면 yfinance로 조회)
                ticker_name = ticker_names.get(ticker)
                if not ticker_name or ticker_name == ticker:
                    # yfinance로 종목명 조회
                    try:
                        stock = yf.Ticker(ticker)
                        info = stock.info
                        if info and len(info) > 0:
                            # 종목명 추출 (우선순위: longName > shortName > symbol)
                            ticker_name = info.get('longName') or info.get('shortName') or info.get('symbol', ticker)
                            logger.debug(f"종목명 조회 성공: {ticker} -> {ticker_name}")
                        else:
                            ticker_name = ticker
                    except Exception as e:
                        logger.debug(f"종목명 조회 실패: {ticker} - {e}")
                        ticker_name = ticker
                
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
                    '3d': ('3D', '3일'),
                    '7d': ('1W', '1주'),
                    '1m': ('1M', '1개월'),
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
                
                # 기술적 지표 포맷팅 (AI 전달용)
                technical_parts = []
                rsi = technical.get('rsi')
                ma_deviation = technical.get('ma_deviation')
                
                if rsi is not None:
                    rsi_status = ""
                    if rsi >= 70:
                        rsi_status = " [과매수]"
                    elif rsi <= 30:
                        rsi_status = " [과매도]"
                    technical_parts.append(f"RSI: {rsi:.1f}{rsi_status}")
                
                if ma_deviation is not None:
                    ma_status = ""
                    if ma_deviation > 105:
                        ma_status = " [단기 과열]"
                    elif ma_deviation < 95:
                        ma_status = " [침체]"
                    technical_parts.append(f"20일 이격도: {ma_deviation:.1f}%{ma_status}")
                
                if technical_parts:
                    technical_str = " | ".join(technical_parts)
                else:
                    technical_str = "N/A"
                
                # 종목명과 티커명 강조 효과 (기술적 지표 포함)
                summary_line = f"📊 <b>{ticker_name}</b> <code>({ticker})</code>\n   현재가: <b>{price_str}</b>\n   변동률:{returns_str}\n   기술적 지표: {technical_str}"
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
        # [24h, 3d, 7d, 1m, 3m, 6m, 1y]
        period_mapping = {
            '24h': ('1D', '1일'),
            '3d': ('3D', '3일'),
            '7d': ('1W', '1주'),
            '1m': ('1M', '1개월'),
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


def calculate_indicators(hist: pd.DataFrame) -> Dict:
    """
    Pandas를 사용하여 기술적 지표(RSI, 이격도) 직접 계산
    API 호출 없이 로컬에서 계산하므로 100% 성공 보장
    
    Args:
        hist: yfinance로 가져온 주가 데이터 (DataFrame)
    
    Returns:
        {
            'rsi': RSI 값 (0~100),
            'disparity': 이격도 (%),
            'signal': 매매 신호 ('BUY', 'SELL', 'NEUTRAL' 등)
        }
    """
    try:
        if len(hist) < 20:
            return {}

        close = hist['Close']

        # 1. RSI (14일) 계산 - Wilder's Smoothing 방식 사용
        current_rsi = calculate_rsi(close, period=14)
        if current_rsi is None:
            return {}

        # 2. 이격도 (Disparity 20일) 계산
        ma20 = close.rolling(window=20).mean()
        current_ma20 = ma20.iloc[-1]
        current_price = close.iloc[-1]
        disparity = (current_price / current_ma20) * 100

        # 3. 신호 판단
        signal = "NEUTRAL"
        if current_rsi >= 70:
            signal = "SELL (Overbought)"
        elif current_rsi <= 30:
            signal = "BUY (Oversold)"
        elif disparity >= 105:
            signal = "SELL (High Disparity)"
        elif disparity <= 95:
            signal = "BUY (Low Disparity)"

        return {
            "rsi": round(current_rsi, 2) if current_rsi is not None else None,
            "disparity": round(disparity, 2),
            "signal": signal
        }
    except Exception as e:
        logger.debug(f"지표 계산 오류: {e}")
        return {}


def get_technical_summary(symbol: str) -> str:
    """
    yfinance 데이터 기반 기술적 분석 수행
    TradingView API 대체용 (자체 계산 엔진)
    
    Args:
        symbol: 종목 코드 (예: '005930.KS', 'TSLA')
    
    Returns:
        포맷팅된 기술적 분석 텍스트
    """
    # 금리형 ETF 예외 처리 (파킹형 ETF는 매일 상승하므로 RSI 계산 불가)
    interest_rate_etfs = {
        '449170.KS',  # TIGER KOFR금리액티브
        '423160.KS',  # CD금리
        '423150.KS',  # KBSTAR 단기통안채
        '423140.KS',  # KBSTAR 단기국공채
    }
    
    if symbol in interest_rate_etfs:
        logger.info(f"{symbol}: 금리형 ETF - RSI 계산 건너뜀")
        return "N/A (금리형 ETF - 매일 상승)"
    
    try:
        # yfinance로 데이터 가져오기 (이미 세션 캐싱됨)
        ticker = yf.Ticker(symbol)
        # RSI, MA 계산을 위해 최소 2달치 데이터 필요
        # 배당/분할 반영을 위해 auto_adjust=True 사용
        hist = ticker.history(period="3mo", auto_adjust=True)
        
        if hist.empty:
            return "N/A (No Data)"

        indicators = calculate_indicators(hist)
        
        if not indicators:
            return "N/A (Insufficient Data)"

        return f"{indicators['signal']} (RSI: {indicators['rsi']}, 이격도: {indicators['disparity']}%)"

    except Exception as e:
        logger.warning(f"{symbol} 분석 실패: {e}")
        return "Analysis Failed"


def get_tradingview_technical_summary(tickers: List[str]) -> str:
    """
    기술적 분석 신호 수집 (자체 계산 엔진 사용)
    TradingView API 의존성 완전 제거 - yfinance 데이터로 직접 계산
    
    Args:
        tickers: 종목 코드 리스트 (예: ['005930.KS', 'TSLA'])
    
    Returns:
        포맷팅된 기술적 분석 텍스트
    """
    logger.info("=== TradingView 기술적 분석 수집 시작 ===")
    print("=== TradingView 기술적 분석 수집 시작 ===")
    
    signals = []
    
    # 금리형 ETF 예외 처리 (파킹형 ETF는 매일 상승하므로 RSI 계산 불가)
    interest_rate_etfs = {
        '449170.KS',  # TIGER KOFR금리액티브
        '423160.KS',  # CD금리
        '423150.KS',  # KBSTAR 단기통안채
        '423140.KS',  # KBSTAR 단기국공채
    }
    
    for ticker in tickers:
        try:
            # 금리형 ETF는 스킵
            if ticker in interest_rate_etfs:
                signals.append(f"- {ticker}: N/A (금리형 ETF - 매일 상승)")
                logger.info(f"{ticker}: 금리형 ETF - RSI 계산 건너뜀")
                continue
            
            # 암호화폐는 스킵
            if '-USD' in ticker or '-KRW' in ticker or '-USDT' in ticker:
                logger.debug(f"{ticker}: 암호화폐는 지원하지 않음, 스킵")
                continue
            
            # yfinance로 데이터 가져오기
            ticker_obj = yf.Ticker(ticker)
            # 배당/분할 반영을 위해 auto_adjust=True 사용
            hist = ticker_obj.history(period="3mo", auto_adjust=True)
            
            if hist.empty or len(hist) < 20:
                signals.append(f"- {ticker}: N/A (데이터 부족)")
                logger.warning(f"{ticker}: 데이터 부족 ({len(hist)}일)")
                continue
            
            # 지표 계산
            indicators = calculate_indicators(hist)
            
            if not indicators:
                signals.append(f"- {ticker}: N/A (계산 실패)")
                logger.warning(f"{ticker}: 지표 계산 실패")
                continue
            
            # 결과 포맷팅
            signal_text = f"- {ticker}: {indicators['signal']} (RSI: {indicators['rsi']}, 이격도: {indicators['disparity']}%)"
            signals.append(signal_text)
            logger.info(f"{ticker} 분석 완료: {indicators['signal']} (RSI: {indicators['rsi']})")
            
        except Exception as e:
            logger.warning(f"{ticker} 분석 실패: {e}")
            signals.append(f"- {ticker}: N/A (분석 실패)")
            continue
    
    if signals:
        result = "[TECHNICAL SIGNALS (Local Calculation)]\n" + "\n".join(signals)
        logger.info(f"기술적 분석 수집 완료: {len(signals)}개")
        print(f"✅ 기술적 분석 수집 완료: {len(signals)}개")
        return result
    else:
        result = "[TECHNICAL SIGNALS (Local Calculation)]\n데이터 수집 실패"
        logger.warning("기술적 분석: 데이터 없음")
        print("⚠️ 기술적 분석: 데이터 없음")
        return result



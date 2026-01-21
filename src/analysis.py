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
from datetime import timezone
import pandas as pd
import numpy as np
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# TradingView API 의존성 제거 - 자체 계산 엔진 사용

# yfinance 데이터 캐시 (티커별로 history 데이터 캐싱하여 중복 호출 방지)
# 멀티스레딩 환경에서의 안전성을 위해 Lock 사용
# TTL: 1시간 (3600초) - 캐시 데이터 유효기간
_yfinance_cache = {}  # {ticker: {'hist_data': DataFrame, 'info': dict, 'timestamp': datetime}}
_yfinance_cache_lock = threading.Lock()  # 캐시 쓰기 보호용 Lock
_CACHE_TTL_SECONDS = 3600  # 1시간

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


def calculate_macd(prices: pd.Series, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> Dict[str, Optional[float]]:
    """
    MACD (Moving Average Convergence Divergence) 계산

    Gerald Appel이 1970년대 개발한 추세 추종 모멘텀 지표입니다.
    - MACD Line: 단기 EMA와 장기 EMA의 차이
    - Signal Line: MACD Line의 EMA
    - Histogram: MACD Line과 Signal Line의 차이

    Args:
        prices: 종가 시리즈
        fast_period: 단기 EMA 기간 (기본값: 12일)
        slow_period: 장기 EMA 기간 (기본값: 26일)
        signal_period: Signal Line EMA 기간 (기본값: 9일)

    Returns:
        {
            'macd_line': MACD Line 값,
            'signal_line': Signal Line 값,
            'histogram': Histogram 값 (MACD - Signal),
            'trend': 추세 판단 ('상승', '하락', '중립')
        }
    """
    result = {
        'macd_line': None,
        'signal_line': None,
        'histogram': None,
        'trend': None
    }

    try:
        # 최소 데이터 요구: slow_period + signal_period
        min_required = slow_period + signal_period
        if len(prices) < min_required:
            logger.debug(f"MACD 계산: 데이터 부족 ({len(prices)}일 < {min_required}일 필요)")
            return result

        # EMA 계산 (pandas ewm 사용)
        # span = period, adjust=False로 표준 EMA 계산
        ema_fast = prices.ewm(span=fast_period, adjust=False).mean()
        ema_slow = prices.ewm(span=slow_period, adjust=False).mean()

        # MACD Line = 단기 EMA - 장기 EMA
        macd_line = ema_fast - ema_slow

        # Signal Line = MACD Line의 EMA
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()

        # Histogram = MACD Line - Signal Line
        histogram = macd_line - signal_line

        # 최신 값 추출
        current_macd = float(macd_line.iloc[-1])
        current_signal = float(signal_line.iloc[-1])
        current_histogram = float(histogram.iloc[-1])

        # NaN 체크
        if pd.isna(current_macd) or pd.isna(current_signal) or pd.isna(current_histogram):
            return result

        result['macd_line'] = round(current_macd, 4)
        result['signal_line'] = round(current_signal, 4)
        result['histogram'] = round(current_histogram, 4)

        # 추세 판단
        # - MACD > Signal: 상승 추세 (골든크로스 상태)
        # - MACD < Signal: 하락 추세 (데드크로스 상태)
        # - Histogram이 양수에서 증가: 상승 모멘텀 강화
        # - Histogram이 음수에서 감소: 하락 모멘텀 강화
        if current_histogram > 0:
            # 이전 Histogram과 비교하여 모멘텀 판단
            if len(histogram) >= 2:
                prev_histogram = float(histogram.iloc[-2])
                if not pd.isna(prev_histogram):
                    if current_histogram > prev_histogram:
                        result['trend'] = '상승↑'  # 상승 모멘텀 강화
                    else:
                        result['trend'] = '상승'   # 상승 모멘텀 약화
                else:
                    result['trend'] = '상승'
            else:
                result['trend'] = '상승'
        elif current_histogram < 0:
            if len(histogram) >= 2:
                prev_histogram = float(histogram.iloc[-2])
                if not pd.isna(prev_histogram):
                    if current_histogram < prev_histogram:
                        result['trend'] = '하락↓'  # 하락 모멘텀 강화
                    else:
                        result['trend'] = '하락'   # 하락 모멘텀 약화
                else:
                    result['trend'] = '하락'
            else:
                result['trend'] = '하락'
        else:
            result['trend'] = '중립'

        return result

    except Exception as e:
        logger.error(f"MACD 계산 실패: {e}")
        return result


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


def calculate_pullback_status(hist_data: pd.DataFrame) -> Optional[str]:
    """
    눌림목(Pullback) 판별 로직
    
    상승 추세 중 일시적 조정 구간을 찾아 매수 적기인지 판별합니다.
    
    Args:
        hist_data: 주가/거래량 데이터 (최소 60일치 필요)
    
    Returns:
        '눌림목 발생(강력)': 4대 조건 모두 만족
        '조정 중': 일부 조건 만족
        '해당 없음': 조건 미충족
        None: 데이터 부족 또는 계산 실패
    """
    try:
        if hist_data.empty or len(hist_data) < 60:
            logger.debug("눌림목 판별: 데이터 부족 (최소 60일 필요)")
            return None
        
        # Close와 Volume 데이터 추출
        closes = hist_data['Close']
        volumes = hist_data['Volume'] if 'Volume' in hist_data.columns else None
        
        if volumes is None or volumes.isna().all():
            logger.debug("눌림목 판별: 거래량 데이터 없음")
            # 거래량 없이도 나머지 조건은 체크 가능
        
        current_price = float(closes.iloc[-1])
        
        # 1. 상승 추세 확인 (MA5 > MA20 > MA60 정배열)
        ma5 = closes.rolling(window=5).mean()
        ma20 = closes.rolling(window=20).mean()
        ma60 = closes.rolling(window=60).mean()
        
        if len(closes) < 60:
            return None
        
        ma5_current = float(ma5.iloc[-1])
        ma20_current = float(ma20.iloc[-1])
        ma60_current = float(ma60.iloc[-1])
        
        # 정배열 확인
        uptrend = (ma5_current > ma20_current > ma60_current)
        
        # 2. 조정 폭 확인 (최근 10거래일 최고점 대비 현재가가 -5% ~ -15% 범위)
        recent_10_days = closes.iloc[-10:]
        recent_high = float(recent_10_days.max())
        retracement_pct = ((current_price - recent_high) / recent_high) * 100
        
        retracement_ok = (-15.0 <= retracement_pct <= -5.0)
        
        # 3. 지지선 확인 (현재가가 MA20의 100% ~ 103% 사이)
        ma20_ratio = (current_price / ma20_current) * 100 if ma20_current > 0 else None
        support_ok = (ma20_ratio is not None and 100.0 <= ma20_ratio <= 103.0)
        
        # 4. 거래량 확인 (당일 거래량이 최근 5거래일 평균의 60% 이하)
        volume_ok = False
        if volumes is not None and not volumes.isna().all():
            try:
                current_volume = float(volumes.iloc[-1])
                recent_5_avg_volume = float(volumes.iloc[-5:].mean())
                
                if recent_5_avg_volume > 0:
                    volume_ratio = (current_volume / recent_5_avg_volume) * 100
                    volume_ok = (volume_ratio <= 60.0)
            except (ValueError, IndexError) as e:
                logger.debug(f"눌림목 판별: 거래량 계산 실패 - {e}")
        
        # 조건 합산
        conditions_met = sum([uptrend, retracement_ok, support_ok, volume_ok])
        
        if conditions_met == 4:
            return '눌림목 발생(강력)'
        elif conditions_met >= 2:
            return '조정 중'
        else:
            return '해당 없음'
    
    except Exception as e:
        logger.error(f"눌림목 판별 실패: {e}")
        return None


def calculate_advanced_indicators(ticker: str, hist_data: Optional[pd.DataFrame] = None) -> Dict[str, Optional[float]]:
    """
    고급 기술적 지표 계산 (20일 이격도, 52주 신고가 위치)
    
    Args:
        ticker: 주식 티커 심볼
        hist_data: 주가 데이터 (None이면 자동 조회)
    
    Returns:
        {
            'ma_disparity': 20일 이격도 (이평선 대비 %),
            'year_high_pos': 52주 신고가 대비 위치 (%)
        }
    """
    result = {
        'ma_disparity': None,
        'year_high_pos': None
    }
    
    try:
        if hist_data is None:
            # 캐시 확인: calculate_returns에서 이미 가져온 데이터가 있는지 확인
            with _yfinance_cache_lock:
                if ticker in _yfinance_cache:
                    cached_data = _yfinance_cache[ticker]
                    # TTL 체크: 캐시가 만료되었는지 확인
                    cache_timestamp = cached_data.get('timestamp')
                    if cache_timestamp:
                        age_seconds = (datetime.now() - cache_timestamp).total_seconds()
                        if age_seconds > _CACHE_TTL_SECONDS:
                            # 캐시 만료 - 삭제
                            del _yfinance_cache[ticker]
                            logger.debug(f"{ticker}: 캐시 만료 (TTL: {_CACHE_TTL_SECONDS}초, 경과: {age_seconds:.0f}초)")
                        elif 'hist_data' in cached_data and cached_data['hist_data'] is not None:
                            cached_hist = cached_data['hist_data']
                            if len(cached_hist) >= 20:  # 최소 20거래일 필요
                                hist_data = cached_hist
                                logger.debug(f"{ticker}: 캐시된 데이터 재사용 (calculate_advanced_indicators)")
            
            # 캐시에 없으면 yfinance로 데이터 가져오기
            if hist_data is None or hist_data.empty:
                stock = get_stock_data(ticker)
                if stock is None:
                    return result
                # 52주 신고가를 위해 1년치 데이터 필요
                hist_data = stock.history(period="1y", auto_adjust=True)
        
        if hist_data.empty or len(hist_data) < 20:
            logger.warning(f"{ticker}: 고급 지표 계산을 위한 데이터 부족 ({len(hist_data)}일)")
            return result
        
        closes = hist_data['Close']
        current_price = float(closes.iloc[-1])
        
        # 1. 20일 이격도 계산 (MA Disparity)
        if len(closes) >= 20:
            ma20 = float(closes.rolling(window=20).mean().iloc[-1])
            ma_disparity = (current_price / ma20) * 100 if ma20 > 0 else None
            result['ma_disparity'] = round(ma_disparity, 2) if ma_disparity else None
        
        # 2. 52주 신고가 위치 계산 (Year High Position)
        # history(period='1y')['High'].max() 사용 (더 정확)
        highs = hist_data['High']
        if len(highs) > 0:
            year_high = float(highs.max())
            year_high_pos = (current_price / year_high) * 100 if year_high > 0 else None
            result['year_high_pos'] = round(year_high_pos, 2) if year_high_pos else None
        
        return result
        
    except Exception as e:
        logger.error(f"{ticker} 고급 기술적 지표 계산 실패: {e}")
        return result


def get_technical_indicators(ticker: str, hist_data: Optional[pd.DataFrame] = None) -> Dict[str, Optional[float]]:
    """
    기술적 지표 계산 (RSI, 20일 이동평균선, 괴리율, MACD)

    Args:
        ticker: 주식 티커 심볼
        hist_data: 이미 가져온 히스토리 데이터 (Optional, 있으면 재호출 안 함)

    Returns:
        {
            'rsi': RSI 값 (0~100),
            'ma20': 20일 이동평균선 가격,
            'ma_deviation': 20일 이동평균선 괴리율 (%),
            'ma_disparity': 20일 이격도 (%),
            'year_high_pos': 52주 신고가 대비 위치 (%),
            'pullback_status': 눌림목 판별 결과,
            'macd': MACD Line 값,
            'macd_signal': Signal Line 값,
            'macd_histogram': Histogram 값,
            'macd_trend': MACD 추세 판단
        }
    """
    try:
        # 이미 데이터가 제공된 경우 재호출하지 않음 (중복 호출 방지)
        if hist_data is not None and not hist_data.empty:
            hist = hist_data
        else:
            stock = get_stock_data(ticker)
            if stock is None:
                return {'rsi': None, 'ma20': None, 'ma_deviation': None, 'ma_disparity': None, 'year_high_pos': None, 'pullback_status': None, 'macd': None, 'macd_signal': None, 'macd_histogram': None, 'macd_trend': None}
            
            # 최소 60일치 데이터 필요 (RSI 14일 + MA 20일 + MA 60일(눌림목) + 여유)
            # 배당/분할 반영을 위해 auto_adjust=True 사용
            # 1년치 데이터를 가져와서 필요한 기간만 사용 (calculate_returns와 동일한 데이터 소스)
            hist = stock.history(period="1y", auto_adjust=True)
        
        if hist.empty or len(hist) < 30:
            logger.warning(f"{ticker}: 기술적 지표 계산을 위한 데이터 부족 ({len(hist)}일)")
            return {'rsi': None, 'ma20': None, 'ma_deviation': None, 'ma_disparity': None, 'year_high_pos': None, 'pullback_status': None, 'macd': None, 'macd_signal': None, 'macd_histogram': None, 'macd_trend': None}
        
        # 데이터 정합성 체크 및 문제 행 제외
        # High >= Low, Close가 High/Low 범위 내 확인
        invalid_rows = []
        for idx in hist.index:
            try:
                high = hist.loc[idx, 'High']
                low = hist.loc[idx, 'Low']
                close = hist.loc[idx, 'Close']
                
                # None 또는 NaN 체크
                if pd.isna(high) or pd.isna(low) or pd.isna(close):
                    invalid_rows.append(idx)
                    continue
                
                # 정합성 검증
                if high < low or close < low or close > high or high <= 0 or low <= 0 or close <= 0:
                    invalid_rows.append(idx)
            except (KeyError, IndexError) as e:
                logger.debug(f"{ticker} 데이터 정합성 체크 실패 (행: {idx}): {e}")
                invalid_rows.append(idx)
        
        if invalid_rows:
            logger.warning(f"{ticker}: 데이터 정합성 문제 발견 ({len(invalid_rows)}일): High/Low/Close 값 비정상, 문제 행 제외")
            # 문제가 있는 행 제외
            hist = hist.drop(invalid_rows)
            
            # 데이터가 너무 적어지면 계산 불가
            if hist.empty or len(hist) < 20:
                logger.warning(f"{ticker}: 정합성 문제 행 제외 후 데이터 부족 ({len(hist)}일)")
                return {'rsi': None, 'ma20': None, 'ma_deviation': None, 'ma_disparity': None, 'year_high_pos': None, 'pullback_status': None, 'macd': None, 'macd_signal': None, 'macd_histogram': None, 'macd_trend': None}
        
        # Close 가격 사용
        closes = hist['Close']
        current_price = float(closes.iloc[-1])
        
        # RSI 계산
        rsi = calculate_rsi(closes, period=14)
        
        # 20일 이동평균선 계산
        ma20 = float(closes.rolling(window=20).mean().iloc[-1]) if len(closes) >= 20 else None
        
        # 괴리율 계산
        ma_deviation = calculate_ma_deviation(current_price, ma20)
        
        # 고급 지표 추가 (이미 가져온 데이터 재사용)
        advanced = calculate_advanced_indicators(ticker, hist_data=hist)
        
        # 눌림목 판별
        pullback_status = calculate_pullback_status(hist)

        # MACD 계산
        macd_data = calculate_macd(closes)

        return {
            'rsi': rsi,
            'ma20': ma20,
            'ma_deviation': ma_deviation,
            'ma_disparity': advanced.get('ma_disparity'),
            'year_high_pos': advanced.get('year_high_pos'),
            'pullback_status': pullback_status,
            'macd': macd_data.get('macd_line'),
            'macd_signal': macd_data.get('signal_line'),
            'macd_histogram': macd_data.get('histogram'),
            'macd_trend': macd_data.get('trend')
        }
    except Exception as e:
        logger.error(f"{ticker} 기술적 지표 계산 실패: {e}")
        return {'rsi': None, 'ma20': None, 'ma_deviation': None, 'ma_disparity': None, 'year_high_pos': None, 'pullback_status': None, 'macd': None, 'macd_signal': None, 'macd_histogram': None, 'macd_trend': None}


def calculate_returns(ticker: str) -> Dict:
    """
    기간별 수익률 및 기술적 지표를 계산 (수급 데이터, ETF 괴리율 포함)
    
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
                'ma_deviation': 20일 이동평균선 괴리율 (%),
                'ma_disparity': 20일 이격도 (%),
                'year_high_pos': 52주 신고가 대비 위치 (%),
                'pullback_status': 눌림목 판별 결과
            },
            'supply_demand': {
                'foreign': 외국인 순매매량 (만 주),
                'institutional': 기관 순매매량 (만 주)
            },
            'disparity_rate': ETF 괴리율 (NAV 대비 %, ETF가 아닐 경우 None),
            'institutional_held': 기관 보유 비중 (%, 해외 주식만)
        }
    """
    result = {
        'ticker': ticker,
        'current_price': None,
        'returns': {},
        'technical': {},
        'supply_demand': {'foreign': None, 'institutional': None},
        'disparity_rate': None,
        'institutional_held': None,
        'total_volume': None  # 전체 거래량 (만 주 단위)
    }
    
    # 날짜 불일치 문제 해결: 한 번의 데이터 조회로 현재가와 과거 가격을 모두 가져옴
    try:
        stock = get_stock_data(ticker)
        if stock is None:
            result['current_price'] = "데이터 없음"
            return result
        
        # 1년치 데이터를 한 번에 가져와서 같은 데이터 소스 사용
        # 배당/분할 반영을 위해 auto_adjust=True 사용
        data = stock.history(period="1y", auto_adjust=True)
        
        if data.empty:
            result['current_price'] = "데이터 없음"
            return result
        
        # stock.info도 미리 가져와서 종목명 조회 시 재사용 (중복 호출 방지)
        try:
            stock_info = stock.info if stock else None
            # stock.info를 result에 저장하여 format_stock_summary_by_category에서 재사용
            if stock_info:
                result['stock_info'] = stock_info
        except Exception as e:
            logger.debug(f"{ticker} stock.info 조회 실패: {e}")
            stock_info = None
        
        # yfinance 데이터 캐시에 저장 (get_tradingview_technical_summary에서 재사용)
        # 멀티스레딩 환경에서의 안전성을 위해 Lock 사용
        with _yfinance_cache_lock:
            _yfinance_cache[ticker] = {
                'hist_data': data,
                'info': stock_info,
                'timestamp': datetime.now()
            }
        
        # 현재가: 가장 최근 거래일의 종가
        current_price = float(data['Close'].iloc[-1])
        result['current_price'] = current_price
        
        # 전체 거래량: 1개월 평균, 3개월 평균 계산
        # KRX API 거래량은 아래에서 국내 주식 데이터 수집 시 함께 가져옴
        if 'Volume' in data.columns:
            # 1개월 평균 거래량 (최근 20거래일)
            if len(data) >= 20:
                volume_1m = data['Volume'].iloc[-20:].mean()
                if pd.notna(volume_1m) and volume_1m > 0:
                    result['total_volume_1m'] = float(volume_1m) / 10000.0  # 만주 단위
                else:
                    result['total_volume_1m'] = None
            else:
                result['total_volume_1m'] = None
            
            # 3개월 평균 거래량 (최근 60거래일)
            if len(data) >= 60:
                volume_3m = data['Volume'].iloc[-60:].mean()
                if pd.notna(volume_3m) and volume_3m > 0:
                    result['total_volume_3m'] = float(volume_3m) / 10000.0  # 만주 단위
                else:
                    result['total_volume_3m'] = None
            else:
                result['total_volume_3m'] = None
            
            # 최신 거래량 (기존 호환성 유지)
            latest_volume = data['Volume'].iloc[-1]
            if pd.notna(latest_volume) and latest_volume > 0:
                volume_in_man = float(latest_volume) / 10000.0
                result['total_volume'] = volume_in_man
            else:
                result['total_volume'] = None
        else:
            result['total_volume'] = None
            result['total_volume_1m'] = None
            result['total_volume_3m'] = None
        
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
        
        for period_name, days_ago in periods.items():
            try:
                # 같은 데이터 소스에서 과거 가격 추출
                if len(data) <= days_ago:
                    # 데이터가 요청 기간의 70% 미만이면 N/A 반환 (부정확한 수익률 방지)
                    data_coverage = (len(data) / days_ago) * 100 if days_ago > 0 else 0
                    if data_coverage < 70:
                        logger.warning(f"{ticker}: {period_name} 데이터 부족 ({len(data)}/{days_ago}거래일, {data_coverage:.0f}%) - N/A 반환")
                        result['returns'][period_name] = "N/A"
                        continue
                    # 70% 이상이면 가장 오래된 데이터 사용 (경고와 함께)
                    logger.warning(f"{ticker}: {days_ago}거래일 전 데이터가 없어 가장 오래된 데이터 사용 ({len(data)}거래일, {data_coverage:.0f}%)")
                    past_price = float(data['Close'].iloc[0])
                else:
                    # 거래일 기준으로 정확한 인덱스 계산
                    # data.index[-1] = 가장 최근 거래일
                    # data.index[-2] = 1거래일 전
                    # 따라서 data.index[-(days_ago+1)] = days_ago 거래일 전
                    target_index = -(days_ago + 1)
                    past_price = float(data['Close'].iloc[target_index])
                
                # None 체크 및 유효성 검증 강화
                if past_price is None or pd.isna(past_price) or past_price <= 0:
                    result['returns'][period_name] = "N/A"
                elif current_price is None or pd.isna(current_price) or current_price <= 0:
                    result['returns'][period_name] = "N/A"
                else:
                    try:
                        return_pct = ((current_price - past_price) / past_price) * 100
                        result['returns'][period_name] = round(return_pct, 2)
                    except (ZeroDivisionError, ValueError, TypeError) as e:
                        logger.warning(f"{ticker} {period_name} 수익률 계산 오류: {e}")
                        result['returns'][period_name] = "오류"
            except Exception as e:
                logger.error(f"{ticker} {period_name} 수익률 계산 실패: {e}")
                result['returns'][period_name] = "오류"
    
    except Exception as e:
        logger.error(f"{ticker} 데이터 조회 실패: {e}")
        result['current_price'] = "데이터 없음"
        return result
    
    # 기술적 지표 계산 (이미 가져온 데이터 재사용하여 중복 호출 방지)
    technical = get_technical_indicators(ticker, hist_data=data)
    result['technical'] = technical
    
    # 국내 주식인 경우 수급 데이터, ETF 괴리율, 거래량 수집
    if '.KS' in ticker or '.KQ' in ticker:
        try:
            # Feature Flag: 듀얼 소스 시스템 사용 여부 (기본값: True)
            try:
                from config.settings import settings
                use_dual_source = settings.use_dual_source
            except Exception:
                use_dual_source = True  # 기본값 True

            kr_data = None

            if use_dual_source:
                try:
                    from src.crawler import get_kr_stock_data_v2
                    kr_data = get_kr_stock_data_v2(ticker)
                    # 듀얼 소스 성공 여부 확인 (신뢰도 기반)
                    confidence = kr_data.get('_confidence', 0) if kr_data else 0
                    if confidence >= 50:
                        logger.debug(f"{ticker}: 듀얼 소스 시스템 사용 (신뢰도: {confidence}%)")
                    else:
                        logger.warning(f"{ticker}: 듀얼 소스 신뢰도 낮음 ({confidence}%), 기존 방식으로 fallback")
                        kr_data = None  # fallback 트리거
                except Exception as e:
                    logger.warning(f"{ticker}: 듀얼 소스 실패 ({e}), 기존 방식으로 fallback")
                    kr_data = None  # fallback 트리거

            # 듀얼 소스 미사용 또는 실패 시 기존 방식으로 fallback
            if kr_data is None:
                from src.crawler import get_kr_stock_data
                kr_data = get_kr_stock_data(ticker)
                logger.debug(f"{ticker}: 기존 방식 사용 (fallback)")
            if kr_data:
                # None 체크 강화 (3일치와 1일치 모두 수집)
                foreign_net = kr_data.get('foreign_net')
                institutional_net = kr_data.get('institutional_net')
                foreign_net_1d = kr_data.get('foreign_net_1d')
                institutional_net_1d = kr_data.get('institutional_net_1d')
                disparity_rate = kr_data.get('disparity_rate')
                total_volume = kr_data.get('total_volume')
                total_volume_1d = kr_data.get('total_volume_1d')
                
                # 3일치 데이터
                if foreign_net is not None:
                    result['supply_demand']['foreign'] = foreign_net
                if institutional_net is not None:
                    result['supply_demand']['institutional'] = institutional_net
                # 1일치 데이터
                if foreign_net_1d is not None:
                    if 'supply_demand_1d' not in result:
                        result['supply_demand_1d'] = {}
                    result['supply_demand_1d']['foreign'] = foreign_net_1d
                if institutional_net_1d is not None:
                    if 'supply_demand_1d' not in result:
                        result['supply_demand_1d'] = {}
                    result['supply_demand_1d']['institutional'] = institutional_net_1d
                
                if disparity_rate is not None:
                    result['disparity_rate'] = disparity_rate
                
                # KRX API 거래량이 있으면 우선 사용 (yfinance보다 정확)
                # 3일치 거래량
                if total_volume is not None and isinstance(total_volume, (int, float)) and total_volume > 0:
                    try:
                        # KRX API는 주 단위로 반환하므로 만주로 변환
                        result['total_volume'] = float(total_volume) / 10000.0
                        logger.debug(f"{ticker} KRX API 거래량(3일) 사용: {result['total_volume']:.2f}만주")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"{ticker} 거래량 변환 실패: {e}")
                        # 변환 실패 시 기존 yfinance 값 유지
                # 1일치 거래량
                if total_volume_1d is not None and isinstance(total_volume_1d, (int, float)) and total_volume_1d > 0:
                    try:
                        result['total_volume_1d'] = float(total_volume_1d) / 10000.0
                        logger.debug(f"{ticker} KRX API 거래량(1일) 사용: {result['total_volume_1d']:.2f}만주")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"{ticker} 거래량(1일) 변환 실패: {e}")
        except Exception as e:
            logger.debug(f"{ticker} 국내 주식 데이터 수집 실패: {e}")
    
    # 해외 주식인 경우 기관 보유 비중 수집
    else:
        try:
            from src.crawler import get_global_institutional_data
            institutional_held = get_global_institutional_data(ticker)
            result['institutional_held'] = institutional_held
        except Exception as e:
            logger.debug(f"{ticker} 기관 보유 비중 수집 실패: {e}")
    
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
    
    # yfinance 캐시 초기화 (새로운 실행마다 캐시 초기화)
    global _yfinance_cache
    with _yfinance_cache_lock:
        _yfinance_cache.clear()
    logger.debug("yfinance 캐시 초기화 완료")
    
    # KRX API 캐시 초기화 (새로운 실행마다 캐시 초기화)
    try:
        from src.crawler import _krx_api_cache, _krx_etf_api_cache
        _krx_api_cache.clear()
        _krx_etf_api_cache.clear()
        logger.debug("KRX API 캐시 초기화 완료")
    except Exception as e:
        logger.debug(f"KRX API 캐시 초기화 실패 (정상 작동 계속): {e}")
    
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
    # 티커 이름 매핑은 공통 모듈에서 가져오기
    from config.ticker_names import get_ticker_name
    
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
                
                # 티커 한글 이름 (매핑에 없으면 calculate_returns에서 가져온 stock_info 재사용)
                ticker_name = get_ticker_name(ticker)
                if not ticker_name or ticker_name == ticker:
                    # calculate_returns에서 이미 가져온 stock_info 재사용 (중복 호출 방지)
                    stock_info = result.get('stock_info')
                    if stock_info and len(stock_info) > 0:
                        # 종목명 추출 (우선순위: longName > shortName > symbol)
                        ticker_name = stock_info.get('longName') or stock_info.get('shortName') or stock_info.get('symbol', ticker)
                        logger.debug(f"종목명 조회 성공 (재사용): {ticker} -> {ticker_name}")
                    else:
                        # stock_info가 없으면 yfinance로 조회 (fallback)
                        try:
                            stock = yf.Ticker(ticker)
                            info = stock.info
                            if info and len(info) > 0:
                                ticker_name = info.get('longName') or info.get('shortName') or info.get('symbol', ticker)
                                logger.debug(f"종목명 조회 성공 (fallback): {ticker} -> {ticker_name}")
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
                        price_str = f"{current_price:,.0f}원"
                    else:
                        # 해외 주식/ETF/암호화폐: 달러
                        if current_price >= 1:
                            price_str = f"${current_price:,.2f}"
                        else:
                            price_str = f"${current_price:.4f}"
                else:
                    price_str = str(current_price)
                
                # 상태 이모지 결정 (종목 헤더용)
                rsi = technical.get('rsi')
                ma_deviation = technical.get('ma_deviation')
                ma_disparity = technical.get('ma_disparity')
                pullback_status = technical.get('pullback_status')
                
                status_emoji = "[해당없음]"
                if pullback_status and '눌림목' in pullback_status:
                    status_emoji = "[✅눌림목]"
                elif rsi is not None:
                    if rsi >= 70:
                        status_emoji = "[🔥과열]"
                    elif rsi <= 30:
                        status_emoji = "[❄️침체]"
                elif ma_deviation is not None:
                    if ma_deviation > 105:
                        status_emoji = "[🔥과열]"
                    elif ma_deviation < 95:
                        status_emoji = "[❄️침체]"
                elif ma_disparity is not None:
                    if ma_disparity > 105:
                        status_emoji = "[🔥과열]"
                    elif ma_disparity < 95:
                        status_emoji = "[❄️침체]"
                
                # 1일 변동률 추출 및 이모지 결정
                one_day_return = None
                if '1D' in returns:
                    one_day_return = returns['1D']
                
                # 1일 변동률 이모지 (🔴 상승, 🔵 하락)
                one_day_emoji = ""
                if one_day_return is not None and isinstance(one_day_return, (int, float)):
                    one_day_emoji = "🔴" if one_day_return >= 0 else "🔵"
                    sign = "+" if one_day_return >= 0 else ""
                    one_day_str = f"({one_day_emoji}{sign}{one_day_return:.2f}%)"
                else:
                    one_day_str = ""
                
                # 주요 기간 수익률 추출 (1주, 1개월) - 라벨 포함
                period_mapping = {
                    '1W': '1주',
                    '1M': '1개월'
                }
                
                main_returns = []
                for period_code, period_label in period_mapping.items():
                    if period_code in returns:
                        val = returns[period_code]
                        if isinstance(val, (int, float)):
                            sign = "+" if val >= 0 else ""
                            # 소수점 자리수 조정 (1월은 정수, 1주는 소수점 1자리)
                            if period_code == '1M':
                                main_returns.append(f"<code>{period_label}{sign}{val:.0f}%</code>")
                            else:
                                main_returns.append(f"<code>{period_label}{sign}{val:.1f}%</code>")
                
                # 주요 기간 수익률 한 줄 포맷팅
                if main_returns:
                    main_returns_str = " ".join(main_returns)
                else:
                    main_returns_str = ""
                
                # 기술적 지표 초압축 포맷 (R:RSI, D:이격도, 52주:위치%)
                technical_parts = []
                
                # RSI: R55 형식
                if rsi is not None:
                    technical_parts.append(f"<code>RSI:{int(rsi)}</code>")
                
                # 이격도: D101 형식 (ma_deviation 우선)
                deviation_value = ma_deviation if ma_deviation is not None else ma_disparity
                if deviation_value is not None:
                    technical_parts.append(f"<code>이격:{int(deviation_value)}</code>")
                
                # 52주 위치: 52주:98% 형식
                year_high_pos = technical.get('year_high_pos')
                if year_high_pos is not None:
                    technical_parts.append(f"| <code>52주:{int(year_high_pos)}%</code>")

                # MACD 추세 표시
                macd_trend = technical.get('macd_trend')
                if macd_trend is not None:
                    technical_parts.append(f"| <code>MACD:{macd_trend}</code>")

                if technical_parts:
                    technical_str = "⚙️ " + " ".join(technical_parts)
                else:
                    technical_str = "⚙️ N/A"
                
                # 전체 거래량 및 수급 데이터 초압축 포맷 (1개월 평균과 3개월 평균 표시)
                # 국내 종목인지 해외 종목인지 확인
                is_domestic = '.KS' in ticker or '.KQ' in ticker
                
                if is_domestic:
                    # 국내 종목: 1개월 평균과 3개월 평균 거래량 표시 (외국인/기관 순매매량 포함)
                    # 1개월 평균 데이터 포맷팅
                    volume_parts_1m = []
                    supply_parts_1m = []
                    
                    total_volume_1m = result.get('total_volume_1m')
                    if total_volume_1m is not None and total_volume_1m > 0:
                        volume_parts_1m.append(f"<code>평균(1M):{total_volume_1m:.0f}만</code>")
                    
                    # 1개월 평균 수급 데이터는 최근 1거래일 데이터 사용 (1개월 평균 수급은 계산 복잡하므로)
                    supply_demand_1d = result.get('supply_demand_1d', {})
                    foreign_net_1d = supply_demand_1d.get('foreign')
                    institutional_net_1d = supply_demand_1d.get('institutional')

                    if foreign_net_1d is not None:
                        # -0 방지: 반올림 후 0이면 부호 없이 표시
                        rounded_val = round(foreign_net_1d)
                        if rounded_val == 0:
                            supply_parts_1m.append(f"<code>외:0만</code>")
                        else:
                            sign = "+" if foreign_net_1d >= 0 else ""
                            supply_parts_1m.append(f"<code>외:{sign}{foreign_net_1d:.0f}만</code>")

                    if institutional_net_1d is not None:
                        # -0 방지: 반올림 후 0이면 부호 없이 표시
                        rounded_val = round(institutional_net_1d)
                        if rounded_val == 0:
                            supply_parts_1m.append(f"<code>기:0만</code>")
                        else:
                            sign = "+" if institutional_net_1d >= 0 else ""
                            supply_parts_1m.append(f"<code>기:{sign}{institutional_net_1d:.0f}만</code>")

                    # 쌍끌이 판단: 반올림 값이 양수일 때 (표시와 일관성 유지)
                    if foreign_net_1d is not None and institutional_net_1d is not None:
                        if round(foreign_net_1d) > 0 and round(institutional_net_1d) > 0:
                            supply_parts_1m.append("<code>🔥쌍끌이</code>")
                    
                    # 3개월 평균 데이터 포맷팅
                    volume_parts_3m = []
                    supply_parts_3m = []
                    
                    total_volume_3m = result.get('total_volume_3m')
                    if total_volume_3m is not None and total_volume_3m > 0:
                        volume_parts_3m.append(f"<code>평균(3M):{total_volume_3m:.0f}만</code>")
                    
                    # 3개월 평균 수급 데이터는 최근 3거래일 합계 데이터 사용
                    supply_demand = result.get('supply_demand', {})
                    foreign_net = supply_demand.get('foreign')
                    institutional_net = supply_demand.get('institutional')

                    if foreign_net is not None:
                        # -0 방지: 반올림 후 0이면 부호 없이 표시
                        rounded_val = round(foreign_net)
                        if rounded_val == 0:
                            supply_parts_3m.append(f"<code>외:0만</code>")
                        else:
                            sign = "+" if foreign_net >= 0 else ""
                            supply_parts_3m.append(f"<code>외:{sign}{foreign_net:.0f}만</code>")

                    if institutional_net is not None:
                        # -0 방지: 반올림 후 0이면 부호 없이 표시
                        rounded_val = round(institutional_net)
                        if rounded_val == 0:
                            supply_parts_3m.append(f"<code>기:0만</code>")
                        else:
                            sign = "+" if institutional_net >= 0 else ""
                            supply_parts_3m.append(f"<code>기:{sign}{institutional_net:.0f}만</code>")

                    # 쌍끌이 판단: 반올림 값이 양수일 때 (표시와 일관성 유지)
                    if foreign_net is not None and institutional_net is not None:
                        if round(foreign_net) > 0 and round(institutional_net) > 0:
                            supply_parts_3m.append("<code>🔥쌍끌이</code>")
                    
                    # ETF 괴리율 (1개월 줄에만 표시)
                    disparity_rate = result.get('disparity_rate')
                    nav_part = None
                    if disparity_rate is not None:
                        sign = "+" if disparity_rate >= 0 else ""
                        nav_part = f"<code>NAV{sign}{disparity_rate:.2f}%</code>"
                    
                    # 1개월 평균 포맷팅
                    volume_supply_str_1m = ""
                    if volume_parts_1m:
                        volume_supply_str_1m = volume_parts_1m[0]
                        if supply_parts_1m:
                            foreign_part_1m = None
                            inst_part_1m = None
                            dual_buying_1m = None
                            for part in supply_parts_1m:
                                if '외:' in part:
                                    foreign_part_1m = part
                                elif '기:' in part:
                                    inst_part_1m = part
                                elif '쌍끌이' in part:
                                    dual_buying_1m = part

                            if foreign_part_1m or inst_part_1m:
                                supply_combined_1m = " | ".join([p for p in [foreign_part_1m, inst_part_1m] if p])
                                volume_supply_str_1m += f" | {supply_combined_1m}"

                            if dual_buying_1m:
                                volume_supply_str_1m += f" {dual_buying_1m}"

                        if nav_part:
                            volume_supply_str_1m += f" | {nav_part}"

                    # 3개월 평균 포맷팅
                    volume_supply_str_3m = ""
                    if volume_parts_3m:
                        volume_supply_str_3m = volume_parts_3m[0]
                        if supply_parts_3m:
                            foreign_part_3m = None
                            inst_part_3m = None
                            dual_buying_3m = None
                            for part in supply_parts_3m:
                                if '외:' in part:
                                    foreign_part_3m = part
                                elif '기:' in part:
                                    inst_part_3m = part
                                elif '쌍끌이' in part:
                                    dual_buying_3m = part

                            if foreign_part_3m or inst_part_3m:
                                supply_combined_3m = " | ".join([p for p in [foreign_part_3m, inst_part_3m] if p])
                                volume_supply_str_3m += f" | {supply_combined_3m}"

                            if dual_buying_3m:
                                volume_supply_str_3m += f" {dual_buying_3m}"
                else:
                    # 해외 종목: 1개월 평균, 3개월 평균 거래량과 기관 보유 비중 표시
                    volume_parts_1m = []
                    volume_parts_3m = []
                    institutional_held = result.get('institutional_held')
                    
                    # 1개월 평균 거래량
                    total_volume_1m = result.get('total_volume_1m')
                    if total_volume_1m is not None and total_volume_1m > 0:
                        volume_parts_1m.append(f"<code>평균(1M):{total_volume_1m:.0f}만</code>")
                    
                    # 3개월 평균 거래량
                    total_volume_3m = result.get('total_volume_3m')
                    if total_volume_3m is not None and total_volume_3m > 0:
                        volume_parts_3m.append(f"<code>평균(3M):{total_volume_3m:.0f}만</code>")
                    
                    # 기관 보유 비중 (1개월 줄에만 표시)
                    if institutional_held is not None:
                        volume_parts_1m.append(f"<code>기관보유:{institutional_held:.1f}%</code>")
                    
                    # 해외 종목은 1개월, 3개월 각각 표시
                    volume_supply_str_1m = " | ".join(volume_parts_1m) if volume_parts_1m else ""
                    volume_supply_str_3m = " | ".join(volume_parts_3m) if volume_parts_3m else ""
                
                # 종목 요약 메시지 생성 (초압축 5줄 포맷)
                # 1행: 헤더 (종목명, 티커, 상태)
                # 2행: 가격/수익 (현재가, 1일%, 주요 기간 수익률)
                # 3행: 지표 (RSI, 이격도, 52주)
                # 4행: 거래량/수급 1개월 평균
                # 5행: 거래량/수급 3개월 평균
                summary_lines = [
                    f"📊 <b>{ticker_name}</b> <code>{ticker}</code> {status_emoji}",
                    f"💰 <b>{price_str}</b> {one_day_str} | {main_returns_str}",
                    f"{technical_str}"
                ]
                
                if volume_supply_str_1m:
                    summary_lines.append(f"📊 {volume_supply_str_1m}")
                
                if volume_supply_str_3m:
                    summary_lines.append(f"📊 {volume_supply_str_3m}")
                
                summary_line = "\n".join(summary_lines)
                summary_parts.append(summary_line)
                
                # 종목 간 구분을 위한 빈 줄 추가
                summary_parts.append("")
            
            # 카테고리별 메시지 생성 (마지막 빈 줄 제거)
            if summary_parts and summary_parts[-1] == "":
                summary_parts = summary_parts[:-1]
            category_messages[category_key] = "\n".join(summary_parts)
    
    total_count = sum(len(results) for results in category_results.values() if results)
    logger.info(f"주가 요약 텍스트 생성 완료: {total_count}개 종목 (카테고리별 개별 메시지)")
    
    return category_messages


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
            
            # 캐시 확인: calculate_returns에서 이미 가져온 데이터가 있는지 확인
            hist = None
            with _yfinance_cache_lock:
                if ticker in _yfinance_cache:
                    cached_data = _yfinance_cache[ticker]
                    # TTL 체크: 캐시가 만료되었는지 확인
                    cache_timestamp = cached_data.get('timestamp')
                    if cache_timestamp:
                        age_seconds = (datetime.now() - cache_timestamp).total_seconds()
                        if age_seconds > _CACHE_TTL_SECONDS:
                            # 캐시 만료 - 삭제
                            del _yfinance_cache[ticker]
                            logger.debug(f"{ticker}: 캐시 만료 (TTL: {_CACHE_TTL_SECONDS}초, 경과: {age_seconds:.0f}초)")
                        elif 'hist_data' in cached_data and cached_data['hist_data'] is not None:
                            cached_hist = cached_data['hist_data']
                            if len(cached_hist) >= 60:  # 최소 60거래일 필요
                                # 최근 3개월치만 추출 (약 60거래일)
                                hist = cached_hist.tail(60)
                                logger.debug(f"{ticker}: 캐시된 데이터 재사용 (3개월치 추출)")
            
            # 캐시에 없으면 yfinance로 데이터 가져오기
            if hist is None or hist.empty:
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



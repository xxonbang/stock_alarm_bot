"""
티커 이름 매핑 공통 모듈
모든 티커 이름 매핑을 단일 소스에서 관리
"""

# 티커 한글 이름 매핑 (표시용)
TICKER_NAMES = {
    # 국내 보유
    '360200.KS': 'ACE 미국S&P500',
    '379810.KS': 'KODEX 미국나스닥100',
    '390390.KS': 'KODEX 미국반도체',
    '465580.KS': 'KODEX ACE 미국빅테크TOP7 Plus',
    '484320.KS': 'KODEX 미국AI전력핵심인프라',
    '411060.KS': 'ACE KRX금현물',
    '438080.KS': 'ACE 미국S&P500미국채혼합50액티브',
    '487230.KS': 'KODEX 미국AI전력핵심인프라',
    # 국내 보유 (개별종목)
    '064400.KS': 'LG CNS',
    # 국내 관심
    '449170.KS': 'TIGER KOFR금리액티브',
    '464310.KS': 'TIGER 글로벌AI&로보틱스 INDXX',
    '005930.KS': '삼성전자',
    '000660.KS': 'SK하이닉스',
    '068270.KS': '셀트리온',
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

# 티커 이름 매핑 (뉴스 필터링용 - 키워드 리스트)
TICKER_NAME_MAPPING = {
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
    '064400.KS': ['lg cns', 'lgcns', 'lg씨엔에스', '씨엔에스'],
}

def get_ticker_name(ticker: str) -> str:
    """
    티커 코드로 한글 이름 조회
    
    Args:
        ticker: 티커 코드 (예: '005930.KS')
    
    Returns:
        한글 이름 또는 티커 코드 (없는 경우)
    """
    return TICKER_NAMES.get(ticker, ticker)

def get_ticker_keywords(ticker: str) -> list:
    """
    티커 코드로 키워드 리스트 조회 (뉴스 필터링용)
    
    Args:
        ticker: 티커 코드 (예: 'TSLA')
    
    Returns:
        키워드 리스트 또는 빈 리스트 (없는 경우)
    """
    return TICKER_NAME_MAPPING.get(ticker, [])

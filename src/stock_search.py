"""
종목 검색 모듈
한글 → 로컬 캐시(pykrx 기반) / 영문 → yfinance
"""
import json
import logging
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

CACHE_PATH = Path(__file__).parent.parent / 'data' / 'krx_stocks.json'

# pykrx 실패 시 fallback용 주요 종목 사전
_BUILTIN_STOCKS = {
    '삼성전자': '005930.KS', '삼성전자우': '005935.KS',
    'SK하이닉스': '000660.KS', 'LG에너지솔루션': '373220.KS',
    '삼성바이오로직스': '207940.KS', '현대차': '005380.KS',
    '기아': '000270.KS', '셀트리온': '068270.KS',
    'KB금융': '105560.KS', '신한지주': '055550.KS',
    'POSCO홀딩스': '005490.KS', 'NAVER': '035420.KS',
    '네이버': '035420.KS', '카카오': '035720.KS',
    'LG화학': '051910.KS', '삼성SDI': '006400.KS',
    '현대모비스': '012330.KS', 'LG전자': '066570.KS',
    'SK이노베이션': '096770.KS', 'SK텔레콤': '017670.KS',
    'KT': '030200.KS', 'KT&G': '033780.KS',
    '삼성물산': '028260.KS', '삼성생명': '032830.KS',
    'LG': '003550.KS', 'SK': '034730.KS',
    '한국전력': '015760.KS', '하나금융지주': '086790.KS',
    '포스코퓨처엠': '003670.KS', '에코프로비엠': '247540.KQ',
    '에코프로': '086520.KQ', '두산에너빌리티': '034020.KS',
    'HD한국조선해양': '009540.KS', 'HD현대중공업': '329180.KS',
    '한화에어로스페이스': '012450.KS', '한화오션': '042660.KS',
    'LG CNS': '064400.KS', '크래프톤': '259960.KS',
    '한미반도체': '042700.KQ', '리노공업': '058470.KQ',
    '삼성전기': '009150.KS', 'SK스퀘어': '402340.KS',
    '카카오뱅크': '323410.KS', '카카오페이': '377300.KS',
    '두산밥캣': '241560.KS', '현대건설': '000720.KS',
    'HLB': '028300.KQ', '알테오젠': '196170.KQ',
    'LG이노텍': '011070.KS', 'CJ제일제당': '097950.KS',
    '삼성화재': '000810.KS', '메리츠금융지주': '138040.KS',
    '고려아연': '010130.KS', 'SK바이오팜': '326030.KS',
}


def refresh_cache() -> bool:
    """네이버 금융에서 전체 종목 목록을 가져와 캐시 파일 갱신"""
    try:
        import requests
        from bs4 import BeautifulSoup

        stocks = {}

        for market, suffix in [('0', '.KS'), ('1', '.KQ')]:
            page = 1
            while True:
                url = f'https://finance.naver.com/sise/sise_market_sum.naver?sosok={market}&page={page}'
                r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                soup = BeautifulSoup(r.text, 'html.parser')

                rows = soup.select('table.type_2 tbody tr')
                found = 0
                for row in rows:
                    a_tag = row.select_one('a.tltle')
                    if not a_tag:
                        continue
                    name = a_tag.text.strip()
                    href = a_tag.get('href', '')
                    code = href.split('code=')[-1] if 'code=' in href else ''
                    if name and code:
                        stocks[name] = f'{code}{suffix}'
                        found += 1

                if found == 0:
                    break
                page += 1
                if page > 40:
                    break

        if not stocks:
            return False

        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(stocks, f, ensure_ascii=False, indent=2)

        logger.info(f"KRX 종목 캐시 갱신: {len(stocks)}개")
        return True

    except Exception as e:
        logger.warning(f"KRX 종목 캐시 갱신 실패: {e}")
        return False


def _load_korean_stocks() -> dict:
    """캐시 파일 로드, 없으면 내장 사전 반환"""
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data:
                return data
        except Exception:
            pass

    return _BUILTIN_STOCKS


def search_stock(name: str) -> List[Tuple[str, str]]:
    """
    종목 검색

    한글 → 로컬 KRX 캐시에서 부분 매칭
    영문 → yfinance Search

    Returns:
        [(종목명, 종목코드), ...]
    """
    has_korean = any('\uac00' <= c <= '\ud7a3' for c in name)

    if has_korean:
        return _search_korean(name)
    else:
        return _search_overseas(name)


def _search_korean(name: str) -> List[Tuple[str, str]]:
    """한글 종목명으로 국내 종목 검색 (로컬 캐시)"""
    stocks = _load_korean_stocks()
    results = []

    for stock_name, ticker in stocks.items():
        if name.lower() in stock_name.lower():
            results.append((stock_name, ticker))

    # 정확한 매칭 우선, 이름 길이순
    results.sort(key=lambda x: (x[0] != name, len(x[0])))
    return results[:5]


def _search_overseas(name: str) -> List[Tuple[str, str]]:
    """영문 종목명/티커로 해외 종목 검색 (yfinance)"""
    try:
        import yfinance as yf

        results = []
        search_results = yf.Search(name)

        if hasattr(search_results, 'quotes') and search_results.quotes:
            for quote in search_results.quotes[:5]:
                symbol = quote.get('symbol', '')
                short_name = quote.get('shortname') or quote.get('longname') or symbol
                if symbol:
                    results.append((short_name, symbol))

        return results

    except Exception as e:
        logger.error(f"해외 종목 검색 실패: {e}")
        return []

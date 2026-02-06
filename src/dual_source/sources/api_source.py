"""
전통적 API 기반 데이터 소스 (Source B)

REST API, 라이브러리, 크롤링을 통해 구조화된 데이터 직접 수집

한국 주식: pykrx + KRX API + 네이버 크롤링
해외 주식: yfinance

장점:
- 빠른 응답 속도 (100-500ms)
- 추가 비용 없음
- 구조화된 데이터 직접 획득

단점:
- API 스펙 변경 시 코드 수정 필요
- Rate limit 제한
"""
import logging
from datetime import datetime, timedelta, date
from typing import Optional, Dict

import requests
from bs4 import BeautifulSoup

from .base import DataSourceBase
from ..types import SupplyDemandData

logger = logging.getLogger(__name__)

# pykrx 라이브러리 내부 경고 로그 억제 (NoneType 에러 등)
logging.getLogger('pykrx').setLevel(logging.ERROR)

# HTTP 세션 (재사용)
_session = requests.Session()

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}


class TraditionalAPISource(DataSourceBase):
    """전통적 API 기반 데이터 소스 (Source B)"""

    def __init__(self, krx_api_key: Optional[str] = None):
        """
        Args:
            krx_api_key: KRX OpenAPI 인증키 (선택사항)
        """
        super().__init__()
        self._krx_api_key = krx_api_key
        self._kis_source = None  # Lazy init, 재사용하여 불필요한 재생성 방지

    @property
    def source_name(self) -> str:
        return "traditional_api"

    @property
    def priority(self) -> int:
        return 2  # Source B: 보조

    def is_supported(self, ticker_code: str) -> bool:
        """한국 주식과 해외 주식 모두 지원"""
        return True

    def _is_korean_stock(self, ticker_code: str) -> bool:
        """한국 주식인지 확인"""
        return '.KS' in ticker_code or '.KQ' in ticker_code

    def _collect_with_pykrx(self, code: str) -> SupplyDemandData:
        """pykrx를 사용한 수급 데이터 수집 (주식/ETF 자동 구분)"""
        result: SupplyDemandData = {}

        try:
            from pykrx import stock

            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')

            df = None

            # pykrx 내부 버그 대응: 예외 발생 전에 logging.info(args, kwargs) 호출
            # root logger를 임시로 비활성화하여 불필요한 에러 로그 억제
            root_logger = logging.getLogger()
            original_level = root_logger.level
            root_logger.setLevel(logging.CRITICAL)

            try:
                # 1. 먼저 일반 주식으로 시도
                try:
                    df = stock.get_market_trading_volume_by_date(start_date, end_date, code)
                except Exception:
                    pass

                # 2. 실패하거나 빈 데이터면 ETF로 시도
                if df is None or df.empty:
                    try:
                        df = stock.get_etf_trading_volume_by_date(start_date, end_date, code)
                    except Exception:
                        pass
            finally:
                root_logger.setLevel(original_level)

            if df is None or df.empty:
                return result

            # 최근 3거래일 합계
            recent_3d = df.tail(3)
            if len(recent_3d) > 0:
                if '외국인합계' in recent_3d.columns:
                    foreign_sum = recent_3d['외국인합계'].sum()
                    result['foreign_net'] = round(foreign_sum / 10000, 2)

                if '기관합계' in recent_3d.columns:
                    institutional_sum = recent_3d['기관합계'].sum()
                    result['institutional_net'] = round(institutional_sum / 10000, 2)

            # 최근 1거래일
            if len(df) > 0:
                latest = df.iloc[-1]
                if '외국인합계' in df.columns:
                    result['foreign_net_1d'] = round(latest['외국인합계'] / 10000, 2)
                if '기관합계' in df.columns:
                    result['institutional_net_1d'] = round(latest['기관합계'] / 10000, 2)

            logger.debug(f"pykrx 수급: 외인={result.get('foreign_net')}만주, 기관={result.get('institutional_net')}만주")

        except ImportError:
            logger.warning("pykrx 미설치")
        except Exception as e:
            logger.debug(f"pykrx 수집 실패: {e}")

        return result

    def _collect_with_krx_api(self, code: str) -> SupplyDemandData:
        """KRX OpenAPI를 사용한 수급 데이터 수집"""
        result: SupplyDemandData = {}

        if not self._krx_api_key:
            return result

        foreign_sum = 0.0
        institutional_sum = 0.0
        count = 0

        for i in range(3):
            date_str = (datetime.now() - timedelta(days=i)).strftime('%Y%m%d')
            url = "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd"
            headers = {"AUTH_KEY": self._krx_api_key}

            for isu_cd in [code, f"KR{code.zfill(10)}"]:
                try:
                    response = _session.get(
                        url,
                        params={"basDd": date_str, "isuCd": isu_cd},
                        headers=headers,
                        timeout=5
                    )

                    if response.status_code == 200:
                        data = response.json()
                        if 'OutBlock_1' in data and len(data['OutBlock_1']) > 0:
                            row = data['OutBlock_1'][0]
                            isu = str(row.get('ISU_CD', '')).strip()

                            if code in isu or isu.endswith(code):
                                foreign_raw = row.get('FRGN_NTBY_QTY') or row.get('외국인순매수') or 0
                                inst_raw = row.get('ORG_NTBY_QTY') or row.get('기관순매수') or 0

                                foreign_val = self._parse_numeric(foreign_raw)
                                inst_val = self._parse_numeric(inst_raw)

                                if count == 0:
                                    result['foreign_net_1d'] = round(foreign_val / 10000, 2)
                                    result['institutional_net_1d'] = round(inst_val / 10000, 2)

                                foreign_sum += foreign_val
                                institutional_sum += inst_val
                                count += 1
                                break

                except Exception as e:
                    logger.debug(f"KRX API 실패: {e}")
                    continue

            if count > 0:
                break

        if count > 0:
            result['foreign_net'] = round(foreign_sum / 10000, 2)
            result['institutional_net'] = round(institutional_sum / 10000, 2)

        return result

    def _collect_etf_data_krx(self, code: str) -> SupplyDemandData:
        """KRX API에서 ETF 괴리율 수집"""
        result: SupplyDemandData = {}

        if not self._krx_api_key:
            return result

        today = date.today()

        for attempt in range(5):
            try:
                target_date = today - timedelta(days=attempt)
                bas_dd = target_date.strftime('%Y%m%d')

                url = "https://data-dbg.krx.co.kr/svc/apis/etp/etf_bydd_trd"
                response = _session.get(
                    url,
                    headers={"AUTH_KEY": self._krx_api_key},
                    params={"basDd": bas_dd},
                    timeout=5
                )

                if response.status_code == 200:
                    data = response.json()
                    if 'OutBlock_1' in data:
                        for row in data['OutBlock_1']:
                            isu_cd = str(row.get('ISU_CD', '')).strip()
                            if isu_cd == code or isu_cd.endswith(code) or code in isu_cd:
                                nav_str = row.get('NAV')
                                close_str = row.get('TDD_CLSPRC')

                                if nav_str and close_str:
                                    nav = float(str(nav_str).replace(',', ''))
                                    close = float(str(close_str).replace(',', ''))

                                    if nav > 0 and close > 0:
                                        ratio = close / nav
                                        if 0.5 <= ratio <= 2.0:
                                            disparity = ((close - nav) / nav) * 100
                                            result['disparity_rate'] = round(disparity, 2)
                                            return result

            except Exception as e:
                logger.debug(f"ETF API 실패: {e}")
                continue

        return result

    def _collect_from_naver(self, code: str) -> SupplyDemandData:
        """네이버 금융 크롤링"""
        result: SupplyDemandData = {}

        try:
            url = f"https://finance.naver.com/item/frgn.naver?code={code}"
            response = _session.get(
                url,
                headers={**HEADERS, 'Referer': 'https://finance.naver.com/'},
                timeout=10
            )

            content = response.content.decode('euc-kr', 'replace')
            soup = BeautifulSoup(content, 'html.parser')

            foreign_sum = 0.0
            inst_sum = 0.0
            count = 0

            tables = soup.select('table')
            for table in tables:
                if '외국인' in table.get_text() or '기관' in table.get_text():
                    rows = table.select('tr')
                    headers = [h.get_text(strip=True) for h in rows[0].select('th, td')]

                    foreign_idx = None
                    inst_idx = None
                    for i, h in enumerate(headers):
                        if '외국인' in h or '외인' in h:
                            foreign_idx = i
                        elif '기관' in h:
                            inst_idx = i

                    if foreign_idx is None and inst_idx is None:
                        continue

                    data_start = 2 if len(rows) > 1 and '순매매량' in rows[1].get_text() else 1

                    for row in rows[data_start:data_start + 3]:
                        tds = row.select('td, th')
                        date_text = tds[0].get_text(strip=True) if tds else ""
                        if not date_text or '.' not in date_text:
                            continue

                        if foreign_idx and foreign_idx < len(tds):
                            val = self._parse_naver_value(tds[foreign_idx].get_text(strip=True))
                            if val is not None:
                                foreign_sum += val
                                if count == 0:
                                    result['foreign_net_1d'] = round(val, 2)

                        if inst_idx and inst_idx < len(tds):
                            val = self._parse_naver_value(tds[inst_idx].get_text(strip=True))
                            if val is not None:
                                inst_sum += val
                                if count == 0:
                                    result['institutional_net_1d'] = round(val, 2)

                        count += 1
                        if count >= 3:
                            break

                    if count > 0:
                        result['foreign_net'] = round(foreign_sum, 2)
                        result['institutional_net'] = round(inst_sum, 2)
                        break

        except Exception as e:
            logger.debug(f"네이버 크롤링 실패: {e}")

        return result

    def _collect_with_yfinance(self, ticker_code: str) -> SupplyDemandData:
        """yfinance를 사용한 해외 주식 데이터 수집"""
        result: SupplyDemandData = {}

        try:
            import yfinance as yf
            stock = yf.Ticker(ticker_code)
            info = stock.info

            if info:
                held = info.get('heldPercentInstitutions')
                if held is not None:
                    result['institutional_net'] = round(float(held) * 100, 2)

                avg_vol = info.get('averageVolume')
                if avg_vol:
                    result['total_volume'] = float(avg_vol)

        except Exception as e:
            logger.debug(f"yfinance 실패: {e}")

        return result

    def _collect_with_finnhub(self, ticker_code: str) -> SupplyDemandData:
        """Finnhub를 사용한 해외 주식 데이터 수집 (Fallback)"""
        result: SupplyDemandData = {}

        try:
            from .finnhub_source import FinnhubSource
            finnhub = FinnhubSource()
            if finnhub._api_key:
                result = finnhub._collect_sync(ticker_code)
                if result:
                    logger.debug(f"{ticker_code}: Finnhub 데이터 보완")
        except Exception as e:
            logger.debug(f"Finnhub fallback 실패: {e}")

        return result

    def _collect_with_fmp(self, ticker_code: str) -> SupplyDemandData:
        """FMP를 사용한 해외 주식 데이터 수집 (Fallback)"""
        result: SupplyDemandData = {}

        try:
            from .fmp_source import FMPSource
            fmp = FMPSource()
            if fmp._api_key:
                result = fmp._collect_sync(ticker_code)
                if result:
                    logger.debug(f"{ticker_code}: FMP 데이터 보완")
        except Exception as e:
            logger.debug(f"FMP fallback 실패: {e}")

        return result

    def _collect_with_twelvedata(self, ticker_code: str) -> SupplyDemandData:
        """Twelve Data를 사용한 해외 주식 데이터 수집 (주요 Fallback)"""
        result: SupplyDemandData = {}

        try:
            from .twelvedata_source import TwelveDataSource
            td = TwelveDataSource()
            if td._api_key:
                result = td._collect_sync(ticker_code)
                if result:
                    logger.debug(f"{ticker_code}: Twelve Data 데이터 보완")
        except Exception as e:
            logger.debug(f"Twelve Data fallback 실패: {e}")

        return result

    def _collect_with_yahoo_chart(self, ticker_code: str) -> SupplyDemandData:
        """Yahoo Chart API 직접 호출 (crumb 불필요, 최우선)"""
        result: SupplyDemandData = {}

        try:
            from .yahoo_chart_source import YahooChartSource
            yahoo = YahooChartSource()
            result = yahoo._collect_sync(ticker_code)
            if result:
                logger.debug(f"{ticker_code}: Yahoo Chart API 성공 (1순위)")
        except Exception as e:
            logger.debug(f"Yahoo Chart API 실패: {e}")

        return result

    def _parse_numeric(self, value) -> float:
        """숫자 파싱"""
        try:
            if isinstance(value, (int, float)):
                return float(value)
            return float(str(value).replace(',', ''))
        except (ValueError, TypeError):
            return 0.0

    def _parse_naver_value(self, text: str) -> Optional[float]:
        """네이버 금융 값 파싱"""
        try:
            clean = text.replace(',', '').replace('+', '').replace('(', '').replace(')', '').strip()
            if clean and clean != '-':
                return float(clean) / 10000  # 만주 변환
        except (ValueError, AttributeError):
            pass
        return None

    def _get_kis_source(self):
        """KISSource 인스턴스 반환 (Lazy init, 재사용)"""
        if self._kis_source is None:
            from .kis_source import KISSource
            self._kis_source = KISSource()
        return self._kis_source

    def _collect_with_kis(self, ticker_code: str) -> SupplyDemandData:
        """KIS API를 사용한 한국 주식 데이터 수집 (선택적)"""
        result: SupplyDemandData = {}

        try:
            kis = self._get_kis_source()
            if kis._token_manager.is_configured():
                result = kis._collect_sync(ticker_code)
                if result:
                    logger.debug(f"{ticker_code}: KIS API 데이터 보완")
        except Exception as e:
            logger.debug(f"KIS API fallback 실패: {e}")

        return result

    def _collect_korean_stock(self, ticker_code: str) -> SupplyDemandData:
        """한국 주식 데이터 수집 (Fallback 체인: KIS → pykrx → KRX API → 네이버)

        주의: ETF의 경우 KIS API가 0을 반환하는 경우가 많으므로,
        0.0 값도 의심스러운 값으로 취급하여 네이버 크롤링으로 교차 검증합니다.
        """
        code = ticker_code.replace('.KS', '').replace('.KQ', '')
        result: SupplyDemandData = {}

        # 1. KIS API 시도 (Primary - 공식 증권사 API)
        kis_data = self._collect_with_kis(ticker_code)
        kis_has_meaningful_data = (
            kis_data.get('foreign_net') is not None and kis_data.get('foreign_net') != 0 or
            kis_data.get('foreign_net_1d') is not None and kis_data.get('foreign_net_1d') != 0 or
            kis_data.get('institutional_net') is not None and kis_data.get('institutional_net') != 0 or
            kis_data.get('institutional_net_1d') is not None and kis_data.get('institutional_net_1d') != 0
        )
        if kis_has_meaningful_data:
            result.update(kis_data)
            logger.debug(f"{ticker_code}: KIS API 성공 (유의미한 데이터)")

        # 2. pykrx 시도 (3일 합계 데이터 전용 - 무료, 안정적)
        # 주의: KIS는 1일 데이터만 제공하므로 pykrx로 3일 합계 보완
        if result.get('foreign_net') is None or result.get('foreign_net') == 0:
            pykrx_data = self._collect_with_pykrx(code)
            pykrx_has_data = (
                pykrx_data.get('foreign_net') is not None and pykrx_data.get('foreign_net') != 0 or
                pykrx_data.get('institutional_net') is not None and pykrx_data.get('institutional_net') != 0
            )
            if pykrx_has_data:
                # 3일 합계 데이터만 업데이트 (KIS의 1일 데이터 보존)
                if pykrx_data.get('foreign_net') is not None:
                    result['foreign_net'] = pykrx_data['foreign_net']
                if pykrx_data.get('institutional_net') is not None:
                    result['institutional_net'] = pykrx_data['institutional_net']
                # 1일 데이터가 없는 경우에만 pykrx 1일 데이터 사용
                if result.get('foreign_net_1d') is None and pykrx_data.get('foreign_net_1d') is not None:
                    result['foreign_net_1d'] = pykrx_data['foreign_net_1d']
                if result.get('institutional_net_1d') is None and pykrx_data.get('institutional_net_1d') is not None:
                    result['institutional_net_1d'] = pykrx_data['institutional_net_1d']
                logger.debug(f"{ticker_code}: pykrx 3일 합계 데이터 보완")

        # 3. KRX API 시도 (Fallback 2 - 3일 합계 데이터 보완)
        if result.get('foreign_net') is None or result.get('foreign_net') == 0:
            krx_data = self._collect_with_krx_api(code)
            krx_has_data = (
                krx_data.get('foreign_net') is not None and krx_data.get('foreign_net') != 0 or
                krx_data.get('institutional_net') is not None and krx_data.get('institutional_net') != 0
            )
            if krx_has_data:
                # 3일 합계 데이터만 업데이트 (기존 1일 데이터 보존)
                if krx_data.get('foreign_net') is not None:
                    result['foreign_net'] = krx_data['foreign_net']
                if krx_data.get('institutional_net') is not None:
                    result['institutional_net'] = krx_data['institutional_net']
                # 1일 데이터가 없는 경우에만 KRX 1일 데이터 사용
                if result.get('foreign_net_1d') is None and krx_data.get('foreign_net_1d') is not None:
                    result['foreign_net_1d'] = krx_data['foreign_net_1d']
                if result.get('institutional_net_1d') is None and krx_data.get('institutional_net_1d') is not None:
                    result['institutional_net_1d'] = krx_data['institutional_net_1d']
                logger.debug(f"{ticker_code}: KRX API 3일 합계 보완")

        # 4. 네이버 크롤링 (최종 폴백 + 교차 검증)
        # ETF의 경우 다른 API가 0을 반환해도 네이버에서 실제 데이터 수집 가능
        needs_naver_fallback = (
            result.get('foreign_net') is None or
            result.get('foreign_net') == 0 or
            result.get('institutional_net') is None or
            result.get('institutional_net') == 0
        )
        if needs_naver_fallback:
            naver_data = self._collect_from_naver(code)
            naver_has_data = (
                naver_data.get('foreign_net') is not None or
                naver_data.get('institutional_net') is not None
            )
            if naver_has_data:
                # 3일 합계 데이터 보완 (기존 0 값 또는 None 덮어쓰기)
                for key in ['foreign_net', 'institutional_net']:
                    if naver_data.get(key) is not None:
                        if result.get(key) is None or result.get(key) == 0:
                            result[key] = naver_data[key]
                # 1일 데이터는 없는 경우에만 업데이트 (기존 데이터 보존)
                if result.get('foreign_net_1d') is None and naver_data.get('foreign_net_1d') is not None:
                    result['foreign_net_1d'] = naver_data['foreign_net_1d']
                if result.get('institutional_net_1d') is None and naver_data.get('institutional_net_1d') is not None:
                    result['institutional_net_1d'] = naver_data['institutional_net_1d']
                logger.debug(f"{ticker_code}: 네이버 크롤링으로 데이터 보완")

        # 5. ETF 괴리율
        etf_data = self._collect_etf_data_krx(code)
        if etf_data.get('disparity_rate') is not None:
            result['disparity_rate'] = etf_data['disparity_rate']

        return result

    def _collect_overseas_stock(self, ticker_code: str) -> SupplyDemandData:
        """해외 주식 데이터 수집 (최적화된 Fallback 체인)

        우선순위 기준:
        1. Yahoo Chart API: crumb 불필요, 빠름 (~250ms), 안정적
        2. yfinance: 기관보유 데이터 전용 (crumb 필요하지만 필수 데이터)
        3. Twelve Data: 800 calls/day, 안정적 백업
        4. Finnhub: 60 calls/min
        5. FMP: 250 calls/day, 기관보유 백업
        """
        result: SupplyDemandData = {}

        # 1. Yahoo Chart API (Primary - crumb 불필요, 빠름, 안정적)
        yahoo_data = self._collect_with_yahoo_chart(ticker_code)
        if yahoo_data:
            result.update(yahoo_data)

        # 2. yfinance (기관보유 데이터 전용 - Chart API 미제공)
        if result.get('institutional_net') is None:
            yfinance_data = self._collect_with_yfinance(ticker_code)
            if yfinance_data:
                for k, v in yfinance_data.items():
                    if result.get(k) is None:
                        result[k] = v
                if yfinance_data.get('institutional_net') is not None:
                    logger.debug(f"{ticker_code}: yfinance 기관보유 데이터 획득")

        # 3. Twelve Data (거래량 백업 - 800/day)
        if result.get('total_volume_1d') is None:
            td_data = self._collect_with_twelvedata(ticker_code)
            if td_data:
                for k, v in td_data.items():
                    if result.get(k) is None:
                        result[k] = v

        # 4. Finnhub (추가 백업 - 60/min)
        if result.get('total_volume_1d') is None:
            finnhub_data = self._collect_with_finnhub(ticker_code)
            if finnhub_data:
                for k, v in finnhub_data.items():
                    if result.get(k) is None:
                        result[k] = v

        # 5. FMP (기관보유 최종 백업 - 250/day)
        if result.get('institutional_net') is None:
            fmp_data = self._collect_with_fmp(ticker_code)
            if fmp_data:
                for k, v in fmp_data.items():
                    if result.get(k) is None:
                        result[k] = v

        return result

    def _collect_sync(self, ticker_code: str) -> SupplyDemandData:
        """동기 방식으로 데이터 수집"""
        if self._is_korean_stock(ticker_code):
            return self._collect_korean_stock(ticker_code)
        else:
            return self._collect_overseas_stock(ticker_code)

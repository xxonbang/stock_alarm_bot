"""
Agentic Screenshot 기반 데이터 소스 (Source A)

Playwright로 웹 페이지를 렌더링 → 스크린샷 캡처 → Gemini Vision AI로 데이터 추출

장점:
- CSS 셀렉터 하드코딩 불필요
- 웹사이트 구조 변경에 자동 적응
- JavaScript 렌더링 후 데이터 수집 가능

단점:
- 상대적으로 느림 (5-10초/요청)
- Vision AI API 비용 발생
"""
import asyncio
import base64
import json
import logging
import os
import re
from typing import Optional, Dict, Any

from .base import DataSourceBase
from ..types import SupplyDemandData

logger = logging.getLogger(__name__)

# gRPC DNS 리졸버 설정
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")
os.environ.setdefault("GRPC_VERBOSITY", "ERROR")

# 배치 처리용 프롬프트 (여러 스크린샷 동시 처리)
BATCH_EXTRACTION_PROMPT_TEMPLATE = """아래는 여러 종목의 네이버 금융 스크린샷입니다.
각 이미지는 순서대로 다음 종목에 해당합니다:
{ticker_list}

각 종목의 스크린샷에서 다음 데이터를 추출해주세요:
1. 외국인 순매매량 - 최근 1거래일 (테이블 첫 번째 행)
2. 외국인 순매매량 - 최근 3거래일 합계 (테이블 상위 3개 행의 합)
3. 기관 순매매량 - 최근 1거래일 (테이블 첫 번째 행)
4. 기관 순매매량 - 최근 3거래일 합계 (테이블 상위 3개 행의 합)
5. ETF인 경우 NAV 괴리율 (%)

반드시 아래 JSON 배열 형식으로만 응답하세요. 다른 텍스트 없이 JSON만 출력:
[
  {{"ticker": "종목코드1", "foreign_net_1d": 숫자또는null, "foreign_net_3d": 숫자또는null, "institutional_net_1d": 숫자또는null, "institutional_net_3d": 숫자또는null, "disparity_rate": 숫자또는null}},
  {{"ticker": "종목코드2", "foreign_net_1d": 숫자또는null, "foreign_net_3d": 숫자또는null, "institutional_net_1d": 숫자또는null, "institutional_net_3d": 숫자또는null, "disparity_rate": 숫자또는null}}
]

주의사항:
- 숫자에서 쉼표(,)는 제거하고 순수 숫자만
- 매도가 많으면 음수(-)로 표시
- 찾을 수 없는 데이터는 null
- 단위는 주(株) 단위로 반환 (만주 아님)
- 3거래일 합계는 테이블의 상위 3개 행 값을 직접 더해서 계산
- 이미지 순서와 종목 순서가 정확히 일치해야 함
"""

# 한국 주식 수급 데이터 추출 프롬프트
KOREA_STOCK_EXTRACTION_PROMPT = """이 네이버 금융 스크린샷에서 다음 데이터를 추출해주세요.

테이블에는 날짜별 외국인/기관 순매매량이 표시됩니다.

추출할 데이터:
1. 외국인 순매매량 - 최근 1거래일 (테이블 첫 번째 행)
2. 외국인 순매매량 - 최근 3거래일 합계 (테이블 상위 3개 행의 합)
3. 기관 순매매량 - 최근 1거래일 (테이블 첫 번째 행)
4. 기관 순매매량 - 최근 3거래일 합계 (테이블 상위 3개 행의 합)
5. ETF인 경우 NAV 괴리율 (%)

반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트 없이 JSON만 출력:
{
  "foreign_net_1d": 숫자 또는 null,
  "foreign_net_3d": 숫자 또는 null,
  "institutional_net_1d": 숫자 또는 null,
  "institutional_net_3d": 숫자 또는 null,
  "disparity_rate": 숫자 또는 null
}

주의사항:
- 숫자에서 쉼표(,)는 제거하고 순수 숫자만
- 매도가 많으면 음수(-)로 표시
- 찾을 수 없는 데이터는 null
- 단위는 주(株) 단위로 반환 (만주 아님)
- 3거래일 합계는 테이블의 상위 3개 행 값을 직접 더해서 계산
"""

# 해외 주식 데이터 추출 프롬프트
US_STOCK_EXTRACTION_PROMPT = """Extract the following data from this Yahoo Finance screenshot.

Data to extract:
1. Institutional Holdings percentage (%)
2. Any available supply/demand indicators

Respond ONLY in this JSON format, no other text:
{
  "institutional_held": number or null,
  "raw_text": "original text found"
}

Notes:
- Remove commas from numbers
- Return null if data not found
"""


class AgenticScreenshotSource(DataSourceBase):
    """Agentic Screenshot 기반 데이터 소스 (Source A)"""

    def __init__(self, google_api_key: Optional[str] = None):
        """
        Args:
            google_api_key: Google AI API Key (Gemini Vision용) - 무시됨, 공유 키 매니저 사용
        """
        super().__init__()
        self._browser = None
        self._playwright = None
        self._client = None
        self._key_manager = None  # 지연 초기화

    @property
    def source_name(self) -> str:
        return "agentic_screenshot"

    @property
    def priority(self) -> int:
        return 1  # Source A: 최우선

    def is_supported(self, ticker_code: str) -> bool:
        """한국 주식과 해외 주식 모두 지원"""
        return True

    def _is_korean_stock(self, ticker_code: str) -> bool:
        """한국 주식인지 확인"""
        return '.KS' in ticker_code or '.KQ' in ticker_code

    async def _init_browser(self):
        """Playwright 브라우저 초기화"""
        if self._browser is not None:
            return

        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                ]
            )
            logger.debug("Playwright 브라우저 초기화 완료")
        except Exception as e:
            logger.error(f"Playwright 초기화 실패: {e}")
            raise

    def _init_gemini_client(self):
        """Gemini 클라이언트 초기화 (공유 키 매니저 사용)"""
        # 키 매니저 초기화
        if self._key_manager is None:
            from config.settings import get_api_key_manager
            self._key_manager = get_api_key_manager()

        # 현재 키로 클라이언트 생성
        api_key, key_number = self._key_manager.get_current_key()

        try:
            from google import genai
            self._client = genai.Client(api_key=api_key)
            logger.debug(f"Gemini 클라이언트 초기화 완료 (키 #{key_number:02d})")
        except Exception as e:
            logger.error(f"Gemini 클라이언트 초기화 실패: {e}")
            raise

    async def _capture_screenshot(self, url: str, wait_selector: Optional[str] = None) -> bytes:
        """
        웹 페이지 스크린샷 캡처

        Args:
            url: 캡처할 URL
            wait_selector: 대기할 CSS 선택자 (선택사항)

        Returns:
            PNG 이미지 바이트
        """
        await self._init_browser()

        context = await self._browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

        try:
            page = await context.new_page()

            # 페이지 로드
            await page.goto(url, wait_until='networkidle', timeout=30000)

            # 특정 요소 대기 (있는 경우)
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=10000)
                except Exception:
                    logger.debug(f"선택자 대기 타임아웃: {wait_selector}")

            # 추가 대기 (동적 콘텐츠 로딩)
            await asyncio.sleep(2)

            # 스크린샷 캡처
            screenshot = await page.screenshot(full_page=False, type='png')
            logger.debug(f"스크린샷 캡처 완료: {url}")

            return screenshot

        finally:
            await context.close()

    def _extract_data_with_vision(self, screenshot: bytes, prompt: str) -> Dict[str, Any]:
        """
        Gemini Vision AI로 스크린샷에서 데이터 추출 (할당량 초과 시 자동 fallback)

        Args:
            screenshot: PNG 이미지 바이트
            prompt: 추출 프롬프트

        Returns:
            추출된 데이터 딕셔너리
        """
        from google.genai import types

        # 키 매니저 초기화
        if self._key_manager is None:
            from config.settings import get_api_key_manager
            self._key_manager = get_api_key_manager()

        max_attempts = self._key_manager.total_keys
        last_error = None

        for attempt in range(max_attempts):
            try:
                # 클라이언트 초기화 (현재 키 사용)
                self._init_gemini_client()

                # Vision API 호출
                response = self._client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=[
                        types.Part.from_bytes(
                            data=screenshot,
                            mime_type='image/png'
                        ),
                        prompt
                    ],
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=65536,
                    )
                )

                response_text = response.text if hasattr(response, 'text') else ""
                logger.debug(f"Vision API 응답 (키 #{self._key_manager.current_key_number:02d}): {response_text[:500]}")

                # JSON 파싱
                return self._parse_json_response(response_text)

            except Exception as e:
                error_str = str(e)
                last_error = e

                # 할당량 초과 에러 감지
                is_quota_exceeded = (
                    'quota' in error_str.lower() or
                    'Quota exceeded' in error_str or
                    '429' in error_str
                )

                if is_quota_exceeded:
                    logger.warning(f"⚠️ Vision API 키 #{self._key_manager.current_key_number:02d} 할당량 초과")
                    # 다음 키로 전환 시도
                    if self._key_manager.mark_key_exhausted():
                        self._client = None  # 클라이언트 재초기화 필요
                        continue
                    else:
                        logger.error("❌ 모든 API 키 할당량 초과")
                        break
                else:
                    # 기타 에러는 바로 실패
                    logger.error(f"Vision API 에러: {error_str}")
                    break

        # 모든 시도 실패
        logger.error(f"Vision API 호출 최종 실패: {last_error}")
        return {}

    def _parse_json_response(self, response_text: str) -> Dict[str, Any]:
        """
        Gemini Vision 응답에서 JSON 추출 및 파싱

        마크다운 코드 블록, 불완전한 응답 등을 처리합니다.

        Args:
            response_text: Gemini Vision API 응답 텍스트

        Returns:
            파싱된 딕셔너리 (실패 시 빈 딕셔너리)
        """
        if not response_text:
            return {}

        json_str = response_text.strip()

        # 1. 완전한 마크다운 코드 블록 처리 (```json ... ```)
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', json_str)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            # 2. 시작만 있는 코드 블록 처리 (응답 잘림)
            if json_str.startswith('```'):
                # ```json 또는 ``` 제거
                json_str = re.sub(r'^```(?:json)?\s*', '', json_str)
                # 끝에 ``` 있으면 제거
                json_str = re.sub(r'\s*```\s*$', '', json_str)

        # 3. JSON 객체 범위 추출 ({ 로 시작해서 } 로 끝나는 부분)
        brace_match = re.search(r'\{[\s\S]*\}', json_str)
        if brace_match:
            json_str = brace_match.group(0)

        # 4. 불완전한 JSON 복구 시도
        json_str = self._fix_incomplete_json(json_str)

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 파싱 실패: {e}, 응답: {response_text[:300]}")
            return {}

    def _fix_incomplete_json(self, json_str: str) -> str:
        """
        불완전한 JSON 문자열 복구 시도

        Args:
            json_str: 파싱할 JSON 문자열

        Returns:
            복구된 JSON 문자열
        """
        if not json_str:
            return "{}"

        json_str = json_str.strip()

        # { 로 시작하지 않으면 반환
        if not json_str.startswith('{'):
            return json_str

        # 이미 완전한 JSON인지 확인
        try:
            json.loads(json_str)
            return json_str
        except json.JSONDecodeError:
            pass

        # 중괄호 균형 맞추기
        open_braces = json_str.count('{')
        close_braces = json_str.count('}')

        if open_braces > close_braces:
            # 마지막 완전한 key-value 쌍 찾기
            # "key": value, 또는 "key": value 형태
            last_complete = json_str

            # 마지막 쉼표 이후 불완전한 부분 제거
            last_comma_idx = json_str.rfind(',')
            if last_comma_idx > 0:
                # 쉼표 이후 부분이 불완전한지 확인
                after_comma = json_str[last_comma_idx + 1:].strip()
                # "key": 형태로 시작하고 값이 없으면 불완전
                if re.match(r'"[^"]+"\s*:\s*$', after_comma) or re.match(r'"[^"]+"\s*:\s*-?\d*$', after_comma):
                    last_complete = json_str[:last_comma_idx]

            # 닫는 중괄호 추가
            missing_braces = open_braces - last_complete.count('}')
            last_complete = last_complete.rstrip().rstrip(',')
            last_complete += '}' * missing_braces

            return last_complete

        return json_str

    async def _collect_korean_stock(self, ticker_code: str) -> SupplyDemandData:
        """
        한국 주식 데이터 수집 (네이버 금융)

        Args:
            ticker_code: 티커 코드 (예: '005930.KS')

        Returns:
            수급 데이터
        """
        result: SupplyDemandData = {}

        code = ticker_code.replace('.KS', '').replace('.KQ', '')

        # 네이버 금융 외국인/기관 페이지
        url = f"https://finance.naver.com/item/frgn.naver?code={code}"

        try:
            screenshot = await self._capture_screenshot(
                url,
                wait_selector='table'
            )

            extracted = self._extract_data_with_vision(screenshot, KOREA_STOCK_EXTRACTION_PROMPT)

            if extracted:
                # 외국인 순매매량 - 1일 (주 → 만주 변환)
                foreign_1d_raw = extracted.get('foreign_net_1d')
                if foreign_1d_raw is not None:
                    result['foreign_net_1d'] = round(float(foreign_1d_raw) / 10000, 2)

                # 외국인 순매매량 - 3일 합계 (주 → 만주 변환)
                foreign_3d_raw = extracted.get('foreign_net_3d')
                if foreign_3d_raw is not None:
                    result['foreign_net'] = round(float(foreign_3d_raw) / 10000, 2)

                # 기관 순매매량 - 1일 (주 → 만주 변환)
                inst_1d_raw = extracted.get('institutional_net_1d')
                if inst_1d_raw is not None:
                    result['institutional_net_1d'] = round(float(inst_1d_raw) / 10000, 2)

                # 기관 순매매량 - 3일 합계 (주 → 만주 변환)
                inst_3d_raw = extracted.get('institutional_net_3d')
                if inst_3d_raw is not None:
                    result['institutional_net'] = round(float(inst_3d_raw) / 10000, 2)

                # ETF 괴리율
                disparity = extracted.get('disparity_rate')
                if disparity is not None:
                    result['disparity_rate'] = float(disparity)

                logger.info(
                    f"{ticker_code} Agentic 수집 완료: "
                    f"외인(1일)={result.get('foreign_net_1d')}만주, "
                    f"외인(3일)={result.get('foreign_net')}만주, "
                    f"기관(1일)={result.get('institutional_net_1d')}만주, "
                    f"기관(3일)={result.get('institutional_net')}만주"
                )

        except Exception as e:
            logger.warning(f"{ticker_code} Agentic 수집 실패: {e}")

        return result

    async def _collect_us_stock(self, ticker_code: str) -> SupplyDemandData:
        """
        미국 주식 데이터 수집 (Yahoo Finance)

        Args:
            ticker_code: 티커 코드 (예: 'AAPL')

        Returns:
            수급 데이터
        """
        result: SupplyDemandData = {}

        # Yahoo Finance 기관 보유 페이지
        url = f"https://finance.yahoo.com/quote/{ticker_code}/holders"

        try:
            screenshot = await self._capture_screenshot(
                url,
                wait_selector='table'
            )

            extracted = self._extract_data_with_vision(screenshot, US_STOCK_EXTRACTION_PROMPT)

            if extracted:
                inst_held = extracted.get('institutional_held')
                if inst_held is not None:
                    result['institutional_net'] = float(inst_held)

                logger.info(f"{ticker_code} Agentic 수집 완료: 기관보유={result.get('institutional_net')}%")

        except Exception as e:
            logger.warning(f"{ticker_code} Agentic 수집 실패: {e}")

        return result

    def _collect_sync(self, ticker_code: str) -> SupplyDemandData:
        """
        동기 방식으로 데이터 수집 (내부적으로 비동기 실행)

        Args:
            ticker_code: 티커 코드

        Returns:
            수급 데이터
        """
        async def _async_collect():
            if self._is_korean_stock(ticker_code):
                return await self._collect_korean_stock(ticker_code)
            else:
                return await self._collect_us_stock(ticker_code)

        # 새 이벤트 루프에서 실행
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 이미 실행 중인 루프가 있으면 새 스레드에서 실행
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, _async_collect())
                    return future.result(timeout=60)
            else:
                return loop.run_until_complete(_async_collect())
        except RuntimeError:
            return asyncio.run(_async_collect())

    async def cleanup(self):
        """리소스 정리"""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    def __del__(self):
        """소멸자"""
        if self._browser or self._playwright:
            try:
                asyncio.run(self.cleanup())
            except Exception:
                pass

    # ===== 배치 처리 메서드 (Vision API 1회 호출) =====

    async def capture_screenshots_batch(
        self, ticker_codes: list[str]
    ) -> dict[str, bytes]:
        """
        여러 티커의 스크린샷을 병렬로 캡처

        Args:
            ticker_codes: 티커 코드 리스트

        Returns:
            {ticker_code: screenshot_bytes} 딕셔너리
        """
        screenshots = {}

        # 한국 주식과 해외 주식 분리
        kr_tickers = [t for t in ticker_codes if self._is_korean_stock(t)]
        us_tickers = [t for t in ticker_codes if not self._is_korean_stock(t)]

        # 한국 주식 스크린샷 캡처
        for ticker in kr_tickers:
            try:
                code = ticker.replace('.KS', '').replace('.KQ', '')
                url = f"https://finance.naver.com/item/frgn.naver?code={code}"
                screenshot = await self._capture_screenshot(url, wait_selector='table')
                screenshots[ticker] = screenshot
                logger.debug(f"스크린샷 캡처 완료: {ticker}")
            except Exception as e:
                logger.warning(f"스크린샷 캡처 실패 ({ticker}): {e}")

        # 해외 주식 스크린샷 캡처
        for ticker in us_tickers:
            try:
                url = f"https://finance.yahoo.com/quote/{ticker}/holders"
                screenshot = await self._capture_screenshot(url, wait_selector='table')
                screenshots[ticker] = screenshot
                logger.debug(f"스크린샷 캡처 완료: {ticker}")
            except Exception as e:
                logger.warning(f"스크린샷 캡처 실패 ({ticker}): {e}")

        logger.info(f"배치 스크린샷 캡처 완료: {len(screenshots)}/{len(ticker_codes)}개 성공")
        return screenshots

    def extract_batch_with_vision(
        self, screenshots: dict[str, bytes]
    ) -> dict[str, SupplyDemandData]:
        """
        여러 스크린샷을 한 번의 Vision API 호출로 처리 (API 호출 정확히 1회)

        한국 주식과 해외 주식을 모두 하나의 API 호출로 처리합니다.

        Args:
            screenshots: {ticker_code: screenshot_bytes} 딕셔너리

        Returns:
            {ticker_code: SupplyDemandData} 딕셔너리
        """
        if not screenshots:
            return {}

        from google.genai import types

        # 키 매니저 초기화
        if self._key_manager is None:
            from config.settings import get_api_key_manager
            self._key_manager = get_api_key_manager()

        # 한국 주식과 해외 주식 분리 (프롬프트 구성용)
        kr_tickers = [k for k in screenshots.keys() if self._is_korean_stock(k)]
        us_tickers = [k for k in screenshots.keys() if not self._is_korean_stock(k)]
        all_tickers = kr_tickers + us_tickers  # 순서 유지: 한국 → 해외

        if not all_tickers:
            return {}

        # 통합 프롬프트 생성 (한국 + 해외)
        prompt = self._build_unified_batch_prompt(kr_tickers, us_tickers)

        # 이미지 순서: 한국 주식 먼저, 해외 주식 나중
        results: dict[str, SupplyDemandData] = {}
        max_attempts = self._key_manager.total_keys
        last_error = None

        for attempt in range(max_attempts):
            try:
                self._init_gemini_client()

                # 요청 내용 구성: 이미지들 (한국→해외 순서) + 프롬프트
                contents = []
                for ticker in all_tickers:
                    contents.append(types.Part.from_bytes(
                        data=screenshots[ticker],
                        mime_type='image/png'
                    ))
                contents.append(prompt)

                response = self._client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=contents,
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=65536,
                    )
                )

                response_text = response.text if hasattr(response, 'text') else ""
                logger.info(f"🎯 배치 Vision API 1회 호출 완료 (한국 {len(kr_tickers)}개 + 해외 {len(us_tickers)}개 = 총 {len(all_tickers)}개)")
                logger.debug(f"배치 Vision 응답: {response_text[:1500]}")

                # 통합 응답 파싱
                parsed = self._parse_unified_batch_response(response_text, kr_tickers, us_tickers)

                # 결과 변환
                for ticker, data in parsed.items():
                    result: SupplyDemandData = {}

                    if self._is_korean_stock(ticker):
                        # 한국 주식: 주 → 만주 변환
                        if data.get('foreign_net_1d') is not None:
                            result['foreign_net_1d'] = round(float(data['foreign_net_1d']) / 10000, 2)
                        if data.get('foreign_net_3d') is not None:
                            result['foreign_net'] = round(float(data['foreign_net_3d']) / 10000, 2)
                        if data.get('institutional_net_1d') is not None:
                            result['institutional_net_1d'] = round(float(data['institutional_net_1d']) / 10000, 2)
                        if data.get('institutional_net_3d') is not None:
                            result['institutional_net'] = round(float(data['institutional_net_3d']) / 10000, 2)
                        if data.get('disparity_rate') is not None:
                            result['disparity_rate'] = float(data['disparity_rate'])
                    else:
                        # 해외 주식
                        if data.get('institutional_held') is not None:
                            result['institutional_net'] = float(data['institutional_held'])

                    results[ticker] = result

                return results

            except Exception as e:
                error_str = str(e)
                last_error = e

                if 'quota' in error_str.lower() or '429' in error_str:
                    logger.warning(f"⚠️ 배치 Vision API 할당량 초과")
                    if self._key_manager.mark_key_exhausted():
                        self._client = None
                        continue
                    else:
                        break
                else:
                    logger.error(f"배치 Vision API 에러: {error_str}")
                    break

        logger.error(f"배치 Vision API 호출 실패: {last_error}")
        return results

    def _build_unified_batch_prompt(self, kr_tickers: list, us_tickers: list) -> str:
        """한국+해외 통합 배치 프롬프트 생성"""
        prompt_parts = []

        prompt_parts.append("아래는 여러 종목의 금융 스크린샷입니다. 이미지 순서대로 데이터를 추출해주세요.\n")

        # 이미지 순서 설명
        idx = 1
        if kr_tickers:
            prompt_parts.append("=== 한국 주식 (네이버 금융) ===")
            for t in kr_tickers:
                code = t.replace('.KS', '').replace('.KQ', '')
                prompt_parts.append(f"{idx}. {code} ({t})")
                idx += 1
            prompt_parts.append("")

        if us_tickers:
            prompt_parts.append("=== 해외 주식 (Yahoo Finance) ===")
            for t in us_tickers:
                prompt_parts.append(f"{idx}. {t}")
                idx += 1
            prompt_parts.append("")

        # 추출 지시사항
        prompt_parts.append("""각 종목에서 추출할 데이터:

[한국 주식]
- foreign_net_1d: 외국인 순매매량 (최근 1거래일, 주 단위)
- foreign_net_3d: 외국인 순매매량 (최근 3거래일 합계, 주 단위)
- institutional_net_1d: 기관 순매매량 (최근 1거래일, 주 단위)
- institutional_net_3d: 기관 순매매량 (최근 3거래일 합계, 주 단위)
- disparity_rate: ETF 괴리율 (%, 해당 시)

[해외 주식]
- institutional_held: 기관 보유 비중 (%)

반드시 아래 JSON 배열 형식으로만 응답하세요:
[
  {"ticker": "005930", "type": "kr", "foreign_net_1d": 숫자, "foreign_net_3d": 숫자, "institutional_net_1d": 숫자, "institutional_net_3d": 숫자, "disparity_rate": 숫자또는null},
  {"ticker": "AAPL", "type": "us", "institutional_held": 숫자또는null}
]

주의:
- 숫자에서 쉼표 제거
- 매도는 음수(-) 표시
- 없는 데이터는 null
- 이미지 순서와 응답 순서 일치
""")

        return "\n".join(prompt_parts)

    def _parse_unified_batch_response(
        self, response_text: str, kr_tickers: list, us_tickers: list
    ) -> dict[str, dict]:
        """통합 배치 응답 파싱"""
        results = {}
        all_tickers = kr_tickers + us_tickers

        if not response_text:
            return results

        json_str = response_text.strip()

        # 마크다운 코드 블록 처리
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', json_str)
        if json_match:
            json_str = json_match.group(1).strip()

        # JSON 배열 추출
        array_match = re.search(r'\[[\s\S]*\]', json_str)
        if array_match:
            json_str = array_match.group(0)

        try:
            data_list = json.loads(json_str)

            if isinstance(data_list, list):
                for item in data_list:
                    if isinstance(item, dict):
                        ticker = item.get('ticker', '')

                        # 티커 매칭
                        matched_ticker = None
                        for t in all_tickers:
                            code = t.replace('.KS', '').replace('.KQ', '')
                            if ticker == t or ticker == code:
                                matched_ticker = t
                                break

                        if matched_ticker:
                            results[matched_ticker] = item

        except json.JSONDecodeError as e:
            logger.warning(f"통합 배치 JSON 파싱 실패: {e}")

        return results

    def _extract_batch_korean(
        self, screenshots: dict[str, bytes]
    ) -> dict[str, SupplyDemandData]:
        """한국 주식 배치 Vision 추출 (1회 API 호출)"""
        from google.genai import types

        results: dict[str, SupplyDemandData] = {}
        ticker_list = list(screenshots.keys())

        if not ticker_list:
            return results

        # 프롬프트 생성
        ticker_list_str = "\n".join([
            f"{i+1}. {t.replace('.KS', '').replace('.KQ', '')} ({t})"
            for i, t in enumerate(ticker_list)
        ])
        prompt = BATCH_EXTRACTION_PROMPT_TEMPLATE.format(ticker_list=ticker_list_str)

        # API 호출 (이미지 + 프롬프트)
        max_attempts = self._key_manager.total_keys
        last_error = None

        for attempt in range(max_attempts):
            try:
                self._init_gemini_client()

                # 요청 내용 구성: 이미지들 + 프롬프트
                contents = []
                for ticker in ticker_list:
                    contents.append(types.Part.from_bytes(
                        data=screenshots[ticker],
                        mime_type='image/png'
                    ))
                contents.append(prompt)

                response = self._client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=contents,
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=65536,
                    )
                )

                response_text = response.text if hasattr(response, 'text') else ""
                logger.info(f"배치 Vision API 호출 완료 (한국 주식 {len(ticker_list)}개)")
                logger.debug(f"배치 Vision 응답: {response_text[:1000]}")

                # JSON 파싱
                parsed = self._parse_batch_json_response(response_text, ticker_list)

                # 결과 변환
                for ticker, data in parsed.items():
                    result: SupplyDemandData = {}

                    if data.get('foreign_net_1d') is not None:
                        result['foreign_net_1d'] = round(float(data['foreign_net_1d']) / 10000, 2)
                    if data.get('foreign_net_3d') is not None:
                        result['foreign_net'] = round(float(data['foreign_net_3d']) / 10000, 2)
                    if data.get('institutional_net_1d') is not None:
                        result['institutional_net_1d'] = round(float(data['institutional_net_1d']) / 10000, 2)
                    if data.get('institutional_net_3d') is not None:
                        result['institutional_net'] = round(float(data['institutional_net_3d']) / 10000, 2)
                    if data.get('disparity_rate') is not None:
                        result['disparity_rate'] = float(data['disparity_rate'])

                    results[ticker] = result

                return results

            except Exception as e:
                error_str = str(e)
                last_error = e

                if 'quota' in error_str.lower() or '429' in error_str:
                    logger.warning(f"⚠️ 배치 Vision API 할당량 초과")
                    if self._key_manager.mark_key_exhausted():
                        self._client = None
                        continue
                    else:
                        break
                else:
                    logger.error(f"배치 Vision API 에러: {error_str}")
                    break

        logger.error(f"배치 Vision API 호출 실패: {last_error}")
        return results

    def _extract_batch_us(
        self, screenshots: dict[str, bytes]
    ) -> dict[str, SupplyDemandData]:
        """해외 주식 배치 Vision 추출 (1회 API 호출)"""
        from google.genai import types

        results: dict[str, SupplyDemandData] = {}
        ticker_list = list(screenshots.keys())

        if not ticker_list:
            return results

        # 해외 주식용 배치 프롬프트
        ticker_list_str = "\n".join([f"{i+1}. {t}" for i, t in enumerate(ticker_list)])
        prompt = f"""Below are Yahoo Finance screenshots for multiple stocks.
Images are in order for these tickers:
{ticker_list_str}

Extract institutional holdings percentage from each screenshot.

Respond ONLY in this JSON array format:
[
  {{"ticker": "TICKER1", "institutional_held": number_or_null}},
  {{"ticker": "TICKER2", "institutional_held": number_or_null}}
]

Notes:
- Remove commas from numbers
- Return null if not found
- Match image order with ticker order exactly
"""

        max_attempts = self._key_manager.total_keys
        last_error = None

        for attempt in range(max_attempts):
            try:
                self._init_gemini_client()

                contents = []
                for ticker in ticker_list:
                    contents.append(types.Part.from_bytes(
                        data=screenshots[ticker],
                        mime_type='image/png'
                    ))
                contents.append(prompt)

                response = self._client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=contents,
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=65536,
                    )
                )

                response_text = response.text if hasattr(response, 'text') else ""
                logger.info(f"배치 Vision API 호출 완료 (해외 주식 {len(ticker_list)}개)")

                parsed = self._parse_batch_json_response(response_text, ticker_list)

                for ticker, data in parsed.items():
                    result: SupplyDemandData = {}
                    if data.get('institutional_held') is not None:
                        result['institutional_net'] = float(data['institutional_held'])
                    results[ticker] = result

                return results

            except Exception as e:
                error_str = str(e)
                last_error = e

                if 'quota' in error_str.lower() or '429' in error_str:
                    if self._key_manager.mark_key_exhausted():
                        self._client = None
                        continue
                    else:
                        break
                else:
                    break

        logger.error(f"배치 Vision API 호출 실패 (해외): {last_error}")
        return results

    def _parse_batch_json_response(
        self, response_text: str, ticker_list: list[str]
    ) -> dict[str, dict]:
        """배치 Vision 응답 JSON 파싱"""
        results = {}

        if not response_text:
            return results

        json_str = response_text.strip()

        # 마크다운 코드 블록 처리
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', json_str)
        if json_match:
            json_str = json_match.group(1).strip()

        # JSON 배열 추출
        array_match = re.search(r'\[[\s\S]*\]', json_str)
        if array_match:
            json_str = array_match.group(0)

        try:
            data_list = json.loads(json_str)

            if isinstance(data_list, list):
                for item in data_list:
                    if isinstance(item, dict):
                        ticker = item.get('ticker', '')
                        # ticker 매칭 (코드만 또는 전체 티커)
                        matched_ticker = None
                        for t in ticker_list:
                            code = t.replace('.KS', '').replace('.KQ', '')
                            if ticker == t or ticker == code:
                                matched_ticker = t
                                break

                        if matched_ticker:
                            results[matched_ticker] = item

        except json.JSONDecodeError as e:
            logger.warning(f"배치 JSON 파싱 실패: {e}")

        return results

    def collect_batch_sync(self, ticker_codes: list[str]) -> dict[str, SupplyDemandData]:
        """
        동기 방식 배치 수집 (Vision API 1회 호출)

        Args:
            ticker_codes: 티커 코드 리스트

        Returns:
            {ticker_code: SupplyDemandData} 딕셔너리
        """
        async def _async_batch():
            screenshots = await self.capture_screenshots_batch(ticker_codes)
            return self.extract_batch_with_vision(screenshots)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, _async_batch())
                    return future.result(timeout=120)
            else:
                return loop.run_until_complete(_async_batch())
        except RuntimeError:
            return asyncio.run(_async_batch())

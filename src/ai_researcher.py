"""
AI 리서치 모듈
Python이 수집한 데이터를 바탕으로 요약 코멘트 작성
"""
import os
# gRPC DNS 리졸버 설정 (DNS 해석 실패 문제 해결)
# c-ares 대신 OS의 기본 DNS 리졸버 사용
os.environ["GRPC_DNS_RESOLVER"] = "native"
os.environ["GRPC_VERBOSITY"] = "ERROR"  # 불필요한 gRPC 로그 끄기

from google import genai
import time
import logging
from typing import Optional, Tuple, Dict
from pathlib import Path

logger = logging.getLogger(__name__)


class AIResearcher:
    """AI 리서처 클래스 - 수집된 텍스트를 요약만 수행"""
    
    def __init__(self, api_key: str, fallback_api_key: str = None):
        """
        Args:
            api_key: Google AI API Key (기본 키)
            fallback_api_key: Fallback API Key (기본 키 실패 시 사용)
        """
        self.api_key = api_key
        self.fallback_api_key = fallback_api_key
        self.current_api_key = api_key
        self._initialize_client(api_key)
    
    def _initialize_client(self, api_key: str):
        """클라이언트 초기화"""
        try:
            self.client = genai.Client(api_key=api_key)
            # 현재 지원되는 최신 모델 사용
            self.model_name = 'gemini-2.5-flash'
            self.current_api_key = api_key
            # 현재 사용 중인 키가 기본 키인지 fallback 키인지 확인
            if api_key == self.api_key:
                key_label = "기본"
            elif api_key == self.fallback_api_key:
                key_label = "Fallback"
            else:
                key_label = "알 수 없음"
            logger.info(f"✅ Google GenAI v2 클라이언트 초기화 완료 ({key_label} 키): {self.model_name}")
            print(f"✅ Google GenAI v2 클라이언트 초기화 완료 ({key_label} 키): {self.model_name}")
        except Exception as e:
            error_msg = f"Google GenAI 클라이언트 초기화 실패: {str(e)[:200]}"
            logger.error(error_msg)
            print(f"❌ {error_msg}")
            raise RuntimeError(error_msg)
    
    def _switch_to_fallback(self):
        """
        Fallback API 키로 전환 (양방향 지원)
        
        - 현재 기본 키를 사용 중이고 fallback 키가 있으면 → fallback 키로 전환
        - 현재 fallback 키를 사용 중이고 기본 키가 있으면 → 기본 키로 전환
        """
        # 현재 기본 키를 사용 중이고 fallback 키가 있으면 fallback 키로 전환
        if self.current_api_key == self.api_key and self.fallback_api_key:
            logger.warning("⚠️ 기본 API 키 실패, Fallback API 키로 전환 시도...")
            print("⚠️ 기본 API 키 실패, Fallback API 키로 전환 시도...")
            self._initialize_client(self.fallback_api_key)
            return True
        # 현재 fallback 키를 사용 중이고 기본 키가 있으면 기본 키로 전환
        elif self.current_api_key == self.fallback_api_key and self.api_key:
            logger.warning("⚠️ Fallback API 키 실패, 기본 API 키로 전환 시도...")
            print("⚠️ Fallback API 키 실패, 기본 API 키로 전환 시도...")
            self._initialize_client(self.api_key)
            return True
        return False
    
    def _call_ai(
        self,
        prompt: str,
        max_retries: int = 5,
        temperature: float = 0.4,
        max_output_tokens: int = 4000,
        system_instruction: str = None
    ) -> Tuple[str, Dict]:
        """
        AI API 호출 (Exponential Backoff 적용, Rate Limit vs Quota 초과 구분)

        Args:
            prompt: 프롬프트
            max_retries: 최대 재시도 횟수 (기본값: 5)
            temperature: 응답 다양성 (0.0~1.0, 낮을수록 일관성 높음, 기본값: 0.4)
            max_output_tokens: 최대 출력 토큰 수 (기본값: 4000)
            system_instruction: 시스템 인스트럭션 (선택사항)

        Returns:
            (AI 응답 텍스트, 토큰 사용량 정보 딕셔너리)
        """
        from google.genai import types

        # 프롬프트 길이 로깅 (할당량 관리용)
        prompt_length = len(prompt)
        estimated_tokens = prompt_length // 4  # 대략적인 토큰 수 추정 (1 토큰 ≈ 4자)
        logger.info(f"API 호출 준비: 프롬프트 {prompt_length}자 (예상 토큰: ~{estimated_tokens}개)")
        logger.info(f"모델 설정: temperature={temperature}, max_output_tokens={max_output_tokens}")

        # 생성 설정 (google-genai v2는 camelCase 사용)
        config_params = {
            'temperature': temperature,
            'maxOutputTokens': max_output_tokens,
            'topP': 0.9,
        }
        if system_instruction:
            config_params['systemInstruction'] = system_instruction
            logger.info("시스템 인스트럭션 적용됨")

        generation_config = types.GenerateContentConfig(**config_params)

        for attempt in range(max_retries):
            try:
                # API 호출 전 짧은 지연 (Rate Limit 방지)
                if attempt > 0:
                    time.sleep(2)

                # Google GenAI v2 API 호출
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=generation_config,
                )
                
                # 응답 텍스트 추출 (google-genai v2는 response.text 속성 제공)
                response_text = response.text if hasattr(response, 'text') else ""

                # 응답 완료 이유 확인 (비정상 종료 시 경고)
                if hasattr(response, 'candidates') and response.candidates:
                    candidate = response.candidates[0]
                    finish_reason = getattr(candidate, 'finish_reason', 'UNKNOWN')
                    # STOP(1) 또는 "STOP" 문자열이 아니면 경고
                    if str(finish_reason) not in ('STOP', 'FinishReason.STOP', '1'):
                        logger.warning(f"⚠️ 응답 비정상 종료: {finish_reason} - maxOutputTokens 증가 필요")

                # 토큰 사용량 정보 추출
                usage_info = {}
                if hasattr(response, 'usage_metadata'):
                    usage_metadata = response.usage_metadata
                    usage_info = {
                        'prompt_tokens': getattr(usage_metadata, 'prompt_token_count', 0),
                        'completion_tokens': getattr(usage_metadata, 'candidates_token_count', 0),
                        'total_tokens': getattr(usage_metadata, 'total_token_count', 0)
                    }
                elif hasattr(response, 'usage'):
                    usage = response.usage
                    usage_info = {
                        'prompt_tokens': getattr(usage, 'prompt_token_count', 0),
                        'completion_tokens': getattr(usage, 'candidates_token_count', 0),
                        'total_tokens': getattr(usage, 'total_token_count', 0)
                    }
                
                return response_text, usage_info
            except Exception as e:
                import traceback
                error_str = str(e)
                error_type = type(e).__name__
                error_traceback = traceback.format_exc()
                
                # 상세 에러 로깅
                logger.error(f"=== LLM API 호출 에러 발생 (시도 {attempt + 1}/{max_retries}) ===")
                logger.error(f"에러 타입: {error_type}")
                logger.error(f"에러 메시지: {error_str}")
                logger.error(f"전체 Traceback:\n{error_traceback}")
                
                # response 객체가 있는 경우 추가 정보 로깅
                if hasattr(e, 'response'):
                    try:
                        logger.error(f"Response 상태 코드: {getattr(e.response, 'status_code', 'N/A')}")
                        logger.error(f"Response 헤더: {getattr(e.response, 'headers', {})}")
                        logger.error(f"Response 본문: {str(getattr(e.response, 'text', 'N/A'))[:500]}")
                    except:
                        pass
                
                # DNS 해석 실패 에러 감지
                is_dns_error = (
                    'DNS resolution failed' in error_str or
                    'DNS' in error_str or
                    '503' in error_str and 'DNS' in error_str or
                    'C-ares' in error_str
                )
                
                # 타임아웃 에러 감지
                is_timeout = (
                    'Timeout' in error_str or
                    'timeout' in error_str.lower()
                )

                # 503 서버 과부하 에러 감지
                is_server_overloaded = (
                    '503' in error_str or
                    'overloaded' in error_str.lower() or
                    'UNAVAILABLE' in error_str
                )

                # 429 에러 타입 구분
                is_quota_exceeded = (
                    'quota' in error_str.lower() or 
                    'Quota exceeded' in error_str or
                    'exceeded your current quota' in error_str.lower() or
                    '429' in error_str
                )
                is_rate_limit = (
                    '429' in error_str and 
                    'rate limit' in error_str.lower() and
                    not is_quota_exceeded and
                    not is_dns_error
                )
                
                # API 키 fallback 시도 (429 에러 또는 할당량 초과 시)
                if is_quota_exceeded and attempt == 0:
                    # 첫 시도에서 할당량 초과 시
                    # 현재 기본 키를 사용 중이면 fallback 키로 전환
                    if self.current_api_key == self.api_key and self.fallback_api_key:
                        if self._switch_to_fallback():
                            logger.info("Fallback API 키로 재시도...")
                            print("🔄 Fallback API 키로 재시도...")
                            continue
                elif is_quota_exceeded and attempt == 1:
                    # 두 번째 시도에서도 할당량 초과 시
                    # 현재 fallback 키를 사용 중이면 기본 키로 전환
                    if self.current_api_key == self.fallback_api_key and self.api_key:
                        if self._switch_to_fallback():
                            logger.info("기본 API 키로 재시도...")
                            print("🔄 기본 API 키로 재시도...")
                            continue
                
                if is_quota_exceeded and attempt >= max_retries - 1:
                    # 모든 재시도 실패 후 최종 실패
                    error_msg = f"❌ API 할당량 초과 (Quota Exceeded): 모든 API 키의 할당량을 모두 사용했습니다. 다음 청구 주기까지 대기하거나 유료 플랜으로 업그레이드하세요."
                    print(error_msg)
                    logger.error(error_msg)
                    logger.error(f"에러 상세: {error_str}")
                    logger.error(f"전체 에러 정보:\n{error_traceback}")
                    # 텔레그램 메시지에는 간단한 메시지만 포함
                    return "API 할당량 초과(429 Error)", {}
                
                elif (is_dns_error or is_timeout or is_server_overloaded) and attempt < max_retries - 1:
                    # DNS 해석 실패, 타임아웃, 서버 과부하: Exponential Backoff 적용
                    # 5초 -> 10초 -> 20초 -> 30초 -> 60초
                    wait_times = [5, 10, 20, 30, 60]
                    wait_time = wait_times[min(attempt, len(wait_times) - 1)]

                    if is_dns_error:
                        error_type = "DNS 해석 실패"
                    elif is_timeout:
                        error_type = "타임아웃"
                    else:
                        error_type = "서버 과부하 (503)"

                    print(f"⚠️ {error_type} 에러 발생 (시도 {attempt + 1}/{max_retries})")
                    print(f"⏳ {wait_time}초 대기 후 재시도합니다...")
                    logger.warning(f"⚠️ {error_type} 에러 발생 (시도 {attempt + 1}/{max_retries}): {error_str[:200]}")
                    logger.info(f"⏳ {wait_time}초 대기 후 재시도합니다...")
                    time.sleep(wait_time)
                    continue
                
                elif is_rate_limit and attempt < max_retries - 1:
                    # Rate Limit: Exponential Backoff 적용
                    # 10초 -> 30초 -> 60초 -> 120초 -> 180초
                    wait_times = [10, 30, 60, 120, 180]
                    wait_time = wait_times[min(attempt, len(wait_times) - 1)]
                    
                    print(f"⚠️ Rate Limit 에러 발생 (시도 {attempt + 1}/{max_retries})")
                    print(f"⏳ Exponential Backoff: {wait_time}초 대기 후 재시도합니다...")
                    logger.warning(f"⚠️ Rate Limit 에러 발생 (시도 {attempt + 1}/{max_retries})")
                    logger.info(f"⏳ Exponential Backoff: {wait_time}초 대기 후 재시도합니다...")
                    time.sleep(wait_time)
                    continue
                
                elif attempt < max_retries - 1:
                    # 기타 에러는 5초 대기 후 재시도
                    logger.warning(f"AI API 호출 실패 (시도 {attempt + 1}/{max_retries}): {error_str}")
                    logger.warning(f"에러 타입: {error_type}")
                    logger.debug(f"전체 Traceback:\n{error_traceback}")
                    time.sleep(5)
                    continue
                else:
                    # 최종 실패
                    logger.error(f"=== AI API 호출 최종 실패 (모든 재시도 실패) ===")
                    logger.error(f"에러 타입: {error_type}")
                    logger.error(f"에러 메시지: {error_str}")
                    logger.error(f"전체 Traceback:\n{error_traceback}")
                    return f"오류: {error_str[:500]}", {}
        
        return "오류: 최대 재시도 횟수 초과", {}
    
    def generate_briefing(self, collected_data: str) -> Tuple[str, str, Dict]:
        """
        Python이 수집한 데이터를 바탕으로 두 가지 포맷의 리포트 생성 (Compact + Detailed)
        각 리포트는 별도의 API 호출로 생성하여 품질과 안정성 향상

        Args:
            collected_data: Python이 수집한 주가 데이터와 뉴스 헤드라인 텍스트

        Returns:
            (Compact 리포트, Detailed 리포트, 토큰 사용량 정보 딕셔너리)
        """
        logger.info("=== AI 요약 코멘트 생성 시작 (분리 호출 방식) ===")

        # 현재 날짜/시간 정보 생성 (KST 기준)
        from datetime import datetime
        from zoneinfo import ZoneInfo
        kst = ZoneInfo('Asia/Seoul')
        now = datetime.now(kst)
        current_date_str = now.strftime("%Y년 %m월 %d일")
        current_datetime_str = now.strftime("%H시 %M분")
        current_weekday = now.strftime("%A")
        weekday_kr = {
            'Monday': '월요일',
            'Tuesday': '화요일',
            'Wednesday': '수요일',
            'Thursday': '목요일',
            'Friday': '금요일',
            'Saturday': '토요일',
            'Sunday': '일요일'
        }
        current_weekday_kr = weekday_kr.get(current_weekday, current_weekday)

        logger.info(f"현재 날짜/시간 (KST): {current_date_str} {current_datetime_str} ({current_weekday_kr})")

        # collected_data 내용 로깅 (디버깅용)
        logger.info("=" * 80)
        logger.info(f"[collected_data 통계] 총 {len(collected_data)}자, {len(collected_data.splitlines())}줄")
        logger.info("=" * 80)

        # 프롬프트 파일 읽기
        prompts_dir = Path(__file__).parent.parent / "config" / "prompts"
        compact_prompt_path = prompts_dir / "gemini_briefing_prompt_compact.txt"
        detailed_prompt_path = prompts_dir / "gemini_briefing_prompt.txt"

        try:
            with open(compact_prompt_path, 'r', encoding='utf-8') as f:
                compact_template = f.read()
            with open(detailed_prompt_path, 'r', encoding='utf-8') as f:
                detailed_template = f.read()
        except FileNotFoundError as e:
            logger.error(f"프롬프트 파일을 찾을 수 없습니다: {e}")
            raise FileNotFoundError(f"프롬프트 파일을 찾을 수 없습니다: {e}")
        except Exception as e:
            logger.error(f"프롬프트 파일 읽기 실패: {e}")
            raise

        # ========================================
        # 통합 프롬프트 구성 (1회 API 호출, XML 태그로 분리)
        # collected_data를 1회만 포함하여 토큰 효율성 극대화
        # ========================================

        # 프롬프트 템플릿에서 데이터 참조 표시로 치환 (실제 데이터는 상단에 1회만 포함)
        compact_instructions = compact_template.format(
            current_date_str=current_date_str,
            current_weekday_kr=current_weekday_kr,
            current_datetime_str=current_datetime_str,
            collected_data="[위 INPUT DATA 섹션 참조]"
        )

        detailed_instructions = detailed_template.format(
            current_date_str=current_date_str,
            current_weekday_kr=current_weekday_kr,
            current_datetime_str=current_datetime_str,
            collected_data="[위 INPUT DATA 섹션 참조]"
        )

        combined_prompt = f"""# 작업 지시

두 개의 독립적인 리포트를 작성하십시오. 각 리포트는 반드시 지정된 XML 태그로 감싸야 합니다.

━━━━━━━━━━━━━━━━━━━━━━
# INPUT DATA (두 리포트 공통 사용)
━━━━━━━━━━━━━━━━━━━━━━
{collected_data}

━━━━━━━━━━━━━━━━━━━━━━
# 요청 1: Compact 리포트
# 반드시 <COMPACT_REPORT> 태그 안에 작성
━━━━━━━━━━━━━━━━━━━━━━
{compact_instructions}

━━━━━━━━━━━━━━━━━━━━━━
# 요청 2: Detailed 리포트
# 반드시 <DETAILED_REPORT> 태그 안에 작성
━━━━━━━━━━━━━━━━━━━━━━
{detailed_instructions}

━━━━━━━━━━━━━━━━━━━━━━
# 출력 형식 (필수)
━━━━━━━━━━━━━━━━━━━━━━

<COMPACT_REPORT>
(여기에 Compact 리포트 전체 내용)
</COMPACT_REPORT>

<DETAILED_REPORT>
(여기에 Detailed 리포트 전체 내용)
</DETAILED_REPORT>
"""

        logger.info("=" * 40)
        logger.info("통합 리포트 생성 중 (Compact + Detailed, 1회 API 호출)...")
        logger.info(f"입력 데이터: {len(collected_data)}자, Compact 지시: {len(compact_instructions)}자, Detailed 지시: {len(detailed_instructions)}자")
        logger.info(f"통합 프롬프트 총 길이: {len(combined_prompt)}자 (데이터 1회 포함)")

        # 시스템 인스트럭션: XML 형식 강제
        system_instruction = """당신은 금융 분석 전문가입니다.
반드시 아래 XML 형식으로 출력하십시오:

<COMPACT_REPORT>
Compact 리포트 내용
</COMPACT_REPORT>

<DETAILED_REPORT>
Detailed 리포트 내용
</DETAILED_REPORT>

XML 태그 없이 출력하면 안 됩니다. 반드시 <COMPACT_REPORT>와 <DETAILED_REPORT> 태그로 감싸십시오."""

        # 단일 API 호출
        # Gemini 2.5는 thinking 토큰이 maxOutputTokens에 포함됨
        result, usage_info = self._call_ai(
            prompt=combined_prompt,
            temperature=0.4,
            max_output_tokens=16000,
            system_instruction=system_instruction
        )

        # XML 태그로 리포트 분리
        compact_report, detailed_report = self._parse_xml_reports(result)

        logger.info(f"Compact 리포트 길이: {len(compact_report)}자")
        logger.info(f"Detailed 리포트 길이: {len(detailed_report)}자")

        # 종목명 후처리 로직 적용
        if compact_report:
            compact_report = self._add_stock_names_to_codes(compact_report)
        if detailed_report:
            detailed_report = self._add_stock_names_to_codes(detailed_report)

        # 최종 통계 로깅
        logger.info("=" * 40)
        if usage_info:
            logger.info(f"[토큰 사용량] 입력: {usage_info.get('prompt_tokens', 0)}, 출력: {usage_info.get('completion_tokens', 0)}, 합계: {usage_info.get('total_tokens', 0)}")
        logger.info(f"[최종 리포트] Compact: {len(compact_report)}자, Detailed: {len(detailed_report)}자")
        logger.info("=== AI 요약 코멘트 생성 완료 ===")

        return compact_report, detailed_report, usage_info

    def _parse_xml_reports(self, text: str) -> tuple:
        """
        XML 태그로 감싸진 응답에서 Compact/Detailed 리포트 추출

        Args:
            text: AI 응답 전체 텍스트

        Returns:
            (compact_report, detailed_report) 튜플
        """
        import re

        compact_report = ""
        detailed_report = ""


        # <COMPACT_REPORT> 태그 추출
        compact_match = re.search(
            r'<COMPACT_REPORT>(.*?)</COMPACT_REPORT>',
            text,
            re.DOTALL
        )
        if compact_match:
            compact_report = compact_match.group(1).strip()
        else:
            logger.warning("⚠️ <COMPACT_REPORT> 태그를 찾을 수 없습니다.")

        # <DETAILED_REPORT> 태그 추출
        detailed_match = re.search(
            r'<DETAILED_REPORT>(.*?)</DETAILED_REPORT>',
            text,
            re.DOTALL
        )
        if detailed_match:
            detailed_report = detailed_match.group(1).strip()
        else:
            logger.warning("⚠️ <DETAILED_REPORT> 태그를 찾을 수 없습니다.")
            # 폴백: 태그가 없으면 전체를 Detailed로 처리
            if not compact_report and not detailed_report:
                logger.warning("모든 태그 누락. 전체 응답을 Detailed 리포트로 처리합니다.")
                detailed_report = text.strip()

        return compact_report, detailed_report
    
    def _add_stock_names_to_codes(self, text: str) -> str:
        """
        AI 응답에서 종목 코드만 있는 경우 종목명을 추가하는 후처리 함수
        웹 검색(yfinance)을 통해 종목명을 조회하여 추가
        
        Args:
            text: AI 응답 텍스트
        
        Returns:
            종목명이 추가된 텍스트
        """
        import re
        import yfinance as yf
        
        # 종목 코드 패턴 찾기
        # 한국 주식: 6자리 숫자 + .KS 또는 .KQ (예: 005930.KS)
        # 해외 주식: 2-5자리 대문자 (예: NVDA, TSLA, AAPL)
        # 암호화폐: BTC-USD, ETH-USD 등
        
        # 알려진 종목 코드 목록 (포트폴리오 및 일반적인 종목)
        known_tickers = {
            # 한국 주식
            '005930.KS', '000660.KS', '035720.KS', '035420.KS',
            # 해외 주식
            'NVDA', 'TSLA', 'AAPL', 'GOOGL', 'MSFT', 'META', 'AMZN',
            'SPY', 'QQQ', 'VTI', 'GLD', 'SLV',
            # 암호화폐
            'BTC-USD', 'ETH-USD'
        }
        
        # 한국 주식 패턴: 6자리 숫자 + .KS 또는 .KQ (한글 문자 고려하여 \b 제거)
        korean_pattern = r'(\d{6}\.(?:KS|KQ))'
        # 해외 주식 패턴: 알려진 티커만 매칭 (한글 문자 고려하여 \b 제거)
        overseas_tickers = [t for t in known_tickers if '.' not in t and '-' not in t]
        if overseas_tickers:
            # 티커 앞뒤에 단어 경계가 아닌 문자나 공백이 있는 경우만 매칭
            overseas_pattern = r'(?<![A-Za-z0-9])(' + '|'.join(re.escape(t) for t in overseas_tickers) + r')(?![A-Za-z0-9])'
        else:
            overseas_pattern = r'(?!)'  # 매칭 안 되는 패턴
        # 암호화폐 패턴
        crypto_pattern = r'([A-Z]{2,4}-USD)'
        
        logger.debug(f"해외 주식 패턴: {overseas_pattern}")
        logger.debug(f"알려진 해외 티커: {overseas_tickers}")
        
        ticker_cache = {}  # 조회한 티커 정보 캐시
        
        def get_stock_name(ticker: str, ticker_type: str) -> Optional[str]:
            """yfinance를 사용하여 종목명 조회"""
            if ticker in ticker_cache:
                return ticker_cache[ticker]
            
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                
                if info and len(info) > 0:
                    # 종목명 추출 (우선순위: longName > shortName > symbol)
                    name = info.get('longName') or info.get('shortName') or info.get('symbol', ticker)
                    
                    ticker_cache[ticker] = name
                    logger.info(f"종목명 조회 성공: {ticker} -> {name}")
                    return name
                else:
                    logger.warning(f"종목명 조회 실패: {ticker} (정보 없음)")
                    return None
            except Exception as e:
                logger.warning(f"종목명 조회 실패: {ticker} - {e}")
                return None
        
        def should_replace(match, ticker: str) -> bool:
            """종목 코드를 종목명으로 교체해야 하는지 확인"""
            start_pos = match.start()
            end_pos = match.end()
            
            # 이미 종목명이 있는 경우 제외 (예: "삼성전자(005930.KS)", "엔비디아(NVDA)")
            # 앞뒤 30자 확인
            context_start = max(0, start_pos - 30)
            context_end = min(len(text), end_pos + 30)
            context = text[context_start:context_end]
            
            # 패턴: 한글/영어 + (티커) 형식이 이미 있는지 확인
            if re.search(r'[가-힣A-Za-z\s]+\([^)]*' + re.escape(ticker) + r'[^)]*\)', context):
                logger.debug(f"종목명 추가 스킵: {ticker} (이미 종목명 있음)")
                return False
            
            # 티커 앞에 한글이나 영어 단어가 바로 있는 경우는 허용 (예: "NVDA가" -> "NVIDIA Corporation(NVDA)가")
            # 단, 괄호 안에 있는 경우는 제외
            if start_pos > 0 and start_pos < len(text):
                prev_char = text[start_pos - 1]
                # 괄호 안에 있으면 제외
                if prev_char == '(':
                    logger.debug(f"종목명 추가 스킵: {ticker} (괄호 안에 있음)")
                    return False
            
            logger.debug(f"종목명 추가 대상: {ticker} (위치: {start_pos}-{end_pos})")
            return True
        
        result_text = text
        
        # 한국 주식 처리
        korean_matches = list(re.finditer(korean_pattern, result_text))
        logger.debug(f"한국 주식 패턴 매칭: {len(korean_matches)}개 발견")
        for match in reversed(korean_matches):
            ticker = match.group(1)
            logger.debug(f"한국 주식 처리 중: {ticker}")
            if not should_replace(match, ticker):
                continue
            
            stock_name = get_stock_name(ticker, 'korean')
            if stock_name and stock_name != ticker:
                replacement = f"{stock_name}({ticker})"
                result_text = result_text[:match.start()] + replacement + result_text[match.end():]
                logger.info(f"종목명 추가: {ticker} -> {replacement}")
        
        # 해외 주식 처리
        overseas_matches = list(re.finditer(overseas_pattern, result_text))
        logger.debug(f"해외 주식 패턴 매칭: {len(overseas_matches)}개 발견")
        for match in reversed(overseas_matches):
            ticker = match.group(1)
            logger.debug(f"해외 주식 처리 중: {ticker}")
            if not should_replace(match, ticker):
                continue
            
            stock_name = get_stock_name(ticker, 'overseas')
            if stock_name and stock_name != ticker:
                replacement = f"{stock_name}({ticker})"
                result_text = result_text[:match.start()] + replacement + result_text[match.end():]
                logger.info(f"종목명 추가: {ticker} -> {replacement}")
        
        # 암호화폐 처리
        crypto_matches = list(re.finditer(crypto_pattern, result_text))
        logger.debug(f"암호화폐 패턴 매칭: {len(crypto_matches)}개 발견")
        for match in reversed(crypto_matches):
            ticker = match.group(1)
            logger.debug(f"암호화폐 처리 중: {ticker}")
            if not should_replace(match, ticker):
                continue
            
            stock_name = get_stock_name(ticker, 'crypto')
            if stock_name and stock_name != ticker:
                replacement = f"{stock_name}({ticker})"
                result_text = result_text[:match.start()] + replacement + result_text[match.end():]
                logger.info(f"종목명 추가: {ticker} -> {replacement}")
        
        return result_text


def create_researcher(api_key: str, fallback_api_key: str = None) -> AIResearcher:
    """
    AIResearcher 인스턴스 생성 헬퍼 함수 (fallback 키 지원)
    
    Args:
        api_key: Google AI API Key (기본 키)
        fallback_api_key: Fallback API Key (기본 키 실패 시 사용)
    
    Returns:
        AIResearcher 인스턴스
    """
    return AIResearcher(api_key, fallback_api_key)

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
            key_label = "01" if api_key == self.api_key else "02"
            logger.info(f"✅ Google GenAI v2 클라이언트 초기화 완료 ({key_label}번 키): {self.model_name}")
            print(f"✅ Google GenAI v2 클라이언트 초기화 완료 ({key_label}번 키): {self.model_name}")
        except Exception as e:
            error_msg = f"Google GenAI 클라이언트 초기화 실패: {str(e)[:200]}"
            logger.error(error_msg)
            print(f"❌ {error_msg}")
            raise RuntimeError(error_msg)
    
    def _switch_to_fallback(self):
        """Fallback API 키로 전환"""
        if self.fallback_api_key and self.current_api_key != self.fallback_api_key:
            logger.warning("⚠️ 기본 API 키 실패, Fallback API 키(02번)로 전환 시도...")
            print("⚠️ 기본 API 키 실패, Fallback API 키(02번)로 전환 시도...")
            self._initialize_client(self.fallback_api_key)
            return True
        elif self.api_key and self.current_api_key != self.api_key:
            logger.warning("⚠️ Fallback API 키 실패, 기본 API 키(01번)로 전환 시도...")
            print("⚠️ Fallback API 키 실패, 기본 API 키(01번)로 전환 시도...")
            self._initialize_client(self.api_key)
            return True
        return False
    
    def _call_ai(self, prompt: str, max_retries: int = 5) -> Tuple[str, Dict]:
        """
        AI API 호출 (Exponential Backoff 적용, Rate Limit vs Quota 초과 구분)
        Google Search 도구 비활성화 (tools 파라미터 미사용)
        
        Args:
            prompt: 프롬프트
            max_retries: 최대 재시도 횟수 (기본값: 5)
        
        Returns:
            (AI 응답 텍스트, 토큰 사용량 정보 딕셔너리)
        """
        # 프롬프트 길이 로깅 (할당량 관리용)
        prompt_length = len(prompt)
        estimated_tokens = prompt_length // 4  # 대략적인 토큰 수 추정 (1 토큰 ≈ 4자)
        logger.info(f"API 호출 준비: 프롬프트 {prompt_length}자 (예상 토큰: ~{estimated_tokens}개)")
        
        for attempt in range(max_retries):
            try:
                # API 호출 전 짧은 지연 (Rate Limit 방지)
                if attempt > 0:
                    time.sleep(2)
                
                # Google GenAI v2 API 호출 (웹 검색 도구 명시적으로 비활성화)
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    # tools 파라미터를 명시적으로 전달하지 않음 (웹 검색 비활성화)
                )
                
                # 응답 텍스트 추출 (google-genai v2는 response.text 속성 제공)
                response_text = response.text if hasattr(response, 'text') else ""
                
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
                    # 첫 시도에서 할당량 초과 시 fallback 키로 전환 시도
                    if self._switch_to_fallback():
                        logger.info("Fallback API 키로 재시도...")
                        print("🔄 Fallback API 키로 재시도...")
                        continue
                elif is_quota_exceeded and attempt == 1 and self.current_api_key == self.fallback_api_key:
                    # Fallback 키도 실패 시 기본 키로 다시 시도
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
                
                elif (is_dns_error or is_timeout) and attempt < max_retries - 1:
                    # DNS 해석 실패 또는 타임아웃: Exponential Backoff 적용 (더 짧은 간격)
                    # 5초 -> 10초 -> 20초 -> 30초 -> 60초
                    wait_times = [5, 10, 20, 30, 60]
                    wait_time = wait_times[min(attempt, len(wait_times) - 1)]
                    
                    error_type = "DNS 해석 실패" if is_dns_error else "타임아웃"
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
    
    def generate_briefing(self, collected_data: str) -> Tuple[str, Dict]:
        """
        Python이 수집한 데이터를 바탕으로 투자자용 요약 코멘트 작성
        
        Args:
            collected_data: Python이 수집한 주가 데이터와 뉴스 헤드라인 텍스트
        
        Returns:
            (투자자용 요약 코멘트, 토큰 사용량 정보 딕셔너리)
        """
        logger.info("=== AI 요약 코멘트 생성 시작 ===")
        
        # collected_data 내용 로깅 (디버깅용)
        logger.info("=" * 80)
        logger.info("[LLM에 전달되는 collected_data 내용]")
        logger.info("=" * 80)
        logger.info(collected_data)
        logger.info("=" * 80)
        logger.info(f"[collected_data 통계] 총 {len(collected_data)}자, {len(collected_data.splitlines())}줄")
        logger.info("=" * 80)
        
        prompt = f"""
        [ ROLE: CHIEF MARKET STRATEGIST ]
당신은 월스트리트에서 20년 이상의 경력을 가진 수석 마켓 스트래티지스트(Chief Market Strategist)입니다.
당신의 임무는 제공된 [입력 데이터](주가/기술적 지표, 매크로 지표, 뉴스 데이터 등)를 심층 분석하고, 
WEB을 통해 가장 최신의 실시간 정보를 검색 후 양질의 정보를 선별하고 연구하여 투자자에게 실질적인 도움이 되는 고품질의 투자 리포트를 작성하는 것입니다.

[ INPUT DATA ]
{collected_data}

■ 데이터 활용 규칙
- 입력되는 내용에 포함된 지표 및 수치를 그대로 활용하지 말고, 웹 검색 및 신뢰성 있는 출처를 통해 정확성을 반복해서 10회 검증한 뒤 분석에 활용하십시오.
- 입력 데이터에 있는 내용에서 각 섹션별 주요 키워드를 최소 3개 이상 뽑고, 이를 기반으로 실시간 WEB 검색 광범위하게 수행하시오. 이를 통해 가장 최신의 정보를 활용하여 분석하고 결과를 반영하십시오.


[ ANALYSIS PRINCIPLES ]

1. 인과관계 중심 서술: 
   - 단순히 "주가가 올랐다"고 하지 말고, "어떤 뉴스나 거시경제 요인이 수급을 자극하여 상승을 이끌었는지" 논리적으로 설명하십시오.

2. 뉴스 활용: 
   - 뉴스 제목을 기계적으로 나열하지 마십시오. 분석 내용 중에 "~라는 보도에 따르면", "~이슈가 부각되며"와 같이 자연스럽게 내용을 인용하여 근거를 강화하십시오.

3. 데이터 기반: 
   - RSI, 이격도, 환율, 금리 등 구체적인 수치를 언급하며 주장을 뒷받침하십시오. 
   - 특히 제공된 외인/기관 순매매량(만주 단위), ETF 괴리율, 52주 신고가 위치, 해외 주식 기관 보유 비중 데이터를 분석의 핵심 근거로 삼으십시오.

4. 종목 코드 언급 시 종목명 필수: 
   - 종목 코드(예: "005930.KS", "NVDA", "TSLA")를 언급할 때는 반드시 종목명도 함께 언급하십시오. 웹 검색을 통해 정확한 종목명을 확인하십시오.
   - 올바른 예: "삼성전자(005930.KS)", "엔비디아(NVDA)", "테슬라(TSLA)"
   - 잘못된 예: "005930.KS가 상승", "NVDA 급등" (종목명 없음)

5. 인과관계 상세 설명:
   - 뉴스(A)를 인용할 경우, 주가(B)와의 인과관계를 설명하세요.
   - 예: "마두로 체포 뉴스로 인해 유가가 상승($57)하여 에너지 ETF 강세가 예상됩니다"
   - 예: "CES 기대감으로 엔비디아가 상승하면서 국내 반도체주(하이닉스) 동반 상승 가능성이 높습니다"

6. 필터링 원칙:
   - 포트폴리오(기술주, 금, 지수 ETF)와 관련 없는 잡다한 뉴스(화장품, 건설, 개별 소비재 등)는 무시하세요.

7. 기술적 지표 판단 기준:
   - 주장 논리에 필요할 경우, 기술적 지표(RSI, 이격도)를 활용하여 판단하시오.
   - RSI 30 이하: 과매도 → 단기 반등 기회
   - RSI 70 이상: 과매수 → 단기 과열 경계
   - 이격도 95% 이하: 침체 → 기술적 반등 가능
   - 이격도 105% 이상: 과열 → 차익 실현 고려
   - ETF 괴리율 +0.5% 이상: 고평가(추격 매수 위험) / -0.5% 이하: 저평가(매수 기회) 판단
   - 52주 신고가 위치 95% 이상: 전고점 돌파(Breakout) 임박 여부 진단
   - 수급 데이터: 외국인/기관의 '쌍끌이 매수' 혹은 '동반 매도' 여부를 추세의 지속성 근거로 활용
   - 눌림목(Pullback) 진단: 상승 정배열 상태에서 주가가 20일 이동평균선에 근접(이격도 100~103%)하고 거래량이 평소 대비 급감했다면, 이를 '세력이 이탈하지 않은 건강한 눌림목'으로 판단하여 기술적 반등 가능성을 리포트에 강력히 명시하십시오. 만약 20일선을 하향 이탈했다면 '추세 붕괴 위험'으로 경고하십시오.

8. 당신이 학습을 끝마친 날짜와 현실의 오늘 날짜 사이에 괴리가 있을 수 있으므로, WEB 검색을 통해 오늘이 정확히 며칠인지 확인하고, 반드시 오늘 날짜 기준으로 모든 분석을 진행하십시오.

9. WEB 검색 결과, 나의 보유 종목, 관심 종목과 상관없이 눈에 띄는 종목이 있다면, 이를 반드시 활용하고, 적극적으로 언급하십시오.


[ WRITING GUIDELINES ]

▶ 가이드라인
- 서론 금지: "안녕하세요", "월스트리트 경력...", "종합하여 분석합니다" 같은 문장은 절대 포함하지 마십시오. 바로 '🔥 금일 급등 예상 섹터'부터 시작하십시오.
- 강조 표시 금지: 결과물에 강조를 위한 별표(**)는 절대 사용하지 마십시오.
- 핵심 위주 서술:
  - 장황하게 뉴스를 나열하지 말고, 시장 움직임의 직접적인 원인(Trigger)만 콕 집어서 한 문장으로 설명하십시오.
  - '트리거 분석', '수급 진단'이 너무 장황하게 서술되는 것을 막고, [핵심 키워드] + [간결한 인과관계 문장] 형태로 압축하십시오.
- 지역 구분 서술 (필수): 모든 분석은 [🇰🇷 국내]와 [🌎 해외]로 명확히 구분하여 서술하십시오.
- 가독성 최적화:
  - 문단이 너무 길어지지 않게 하십시오.
  - 문장 및 문단의 가독성을 높이기 위해 쉬운 표현과 쉬운 문장 구조를 사용하십시오.
  - 가독성을 최대로 높일 수 있도록 적절한 줄바꿈과 이모티콘, 문장 부호를 사용하십시오.


[ REPORT FORMAT ]
다음 여섯 가지 섹션으로 구분하여 작성하되, 각 섹션은 요약식이 아닌 핵심내용 위주의 서술형(Paragraph) 문단으로 작성해야 합니다.

---

### 🧐 포트폴리오 진단 및 분석
▶ 작성목표: input data 중 나의 포트폴리오 종목(보유종목)을 진단 및 분석하여, 현재까지의 상황 및 향후 전망에 대해 진단하고 연구하십시오.

▶ 포함해야 할 상세 내용:
- 포트폴리오 종목 분석 및 진단: 나의 포트폴리오 종목을 분석하고 진단하십시오. 이때 국내 종목은 최근 3거래일 수급(외인/기관) 흐름을, 해외 종목은 기관 보유 비중(Institutional Held)을 반드시 포함하여 진단하십시오.
- 포트폴리오 종목 향후 전망 및 예측: 나의 포트폴리오 종목의 향후 전망을 예측하십시오. 52주 신고가 위치 및 MA 이격도를 기반으로 현재 주가의 기술적 부담감이나 돌파 에너지를 정밀 평가하십시오.
- 포트폴리오 리밸런싱 및 조정 권장 사항: 나의 포트폴리오 종목을 리밸런싱하고 조정하는 권장 사항을 제시하십시오. 리밸런싱 및 조정이 불필요할 경우 포트폴리오 유지 권장 사항을 제시하십시오. 특히 ETF 종목의 경우 NAV 괴리율이 비정상적으로 벌어졌다면 가격 정합성에 따른 주의 의견을 추가하십시오.
- 보유 종목 중 '눌림목 발생' 데이터가 확인된 경우, 공포에 의한 매도가 아닌 추가 매수 또는 보유 관점의 전략을 구체적으로 제시하십시오. 눌림목은 상승 추세 중 건강한 조정으로, 거래량 급감과 20일선 지지가 확인되면 기술적 반등 가능성이 높다는 점을 인과관계와 함께 설명하십시오.
- 항목의 설명을 통합하지말고, 각각의 항목의 섹션을 구분할 수 있는 머릿말과 함께 개별적으로 내용을 구성하시오.
- 각 항목별로 한 줄 요약을 제시하십시오.

▶ 중요 지침:
- 웹 검색을 통해 오늘이 며칠인지 확인하고, 반드시 오늘 날짜 기준으로 분석하십시오.
- 입력 데이터 및 실시간 웹 검색 내용, AI의 지식을 활용하여 동적으로 매핑하십시오.
- 논리적으로 설명하고, 과도한 추측과 부정확한 내용은 피하시오.
- 시장에서 실제로 거래되는 종목명을 정확히 언급하십시오.

---

### 🔥 금일 급등 예상 섹터 (나비 효과)
▶ 작성 목표: 밤사이 미국 시장에서 급등한 상위 종목들을 분석하여, 오늘 한국 주식시장에서 갭상승 출발이 유력한 '관련 테마'와 '수혜주'를 AI의 지능으로 동적 매핑하여 추론하십시오.(입력 데이터 및 실시간 웹 검색 기반)

▶ 입력 데이터 확인: 제공된 데이터에 "🔥 미국 시장 Top Movers" 섹션이 있다면, 이를 반드시 활용하십시오. 해당 섹션이 없으면 이 섹션을 생략하십시오.

▶ 포함해야 할 상세 내용:
- 미국 주도주 분석: 밤사이 미국 시장에서 급등한 상위 종목들의 섹터를 분석하십시오. (예: 바이오텍, 반도체, AI 등)
- 나비 효과 추론: 각 미국 급등주가 한국 시장에 미칠 영향을 인과관계 중심으로 서술하십시오.
  - 예: "미국 모더나(MRNA) 급등 → 한국 삼성바이오로직스, 셀트리온 등 바이오테마 갭상승 예상"
  - 예: "엔비디아(NVDA) 급등 → 한국 삼성전자, SK하이닉스 등 반도체주 동반 상승 유력"
- 🎯 Action Plan: 오늘 한국 시장 개장 시 주목해야 할 테마와 종목을 구체적으로 제시하십시오.
- 한 줄 요약 : 금일 급등 예상 섹터 전체 내용에 대한 한 줄 요약을 제시하십시오.

▶ 중요 지침:
- 하드코딩된 종목 매핑을 사용하지 말고, 입력 데이터 및 실시간 웹 검색 내용, AI의 지식을 활용하여 동적으로 매핑하십시오.
- 섹터별 연관성을 논리적으로 설명하되, 과도한 추측은 피하십시오.
- 한국 시장에서 실제로 거래되는 종목명을 정확히 언급하십시오.

---

### 🚀 오늘의 핫 테마 (Korea Hot Themes)
▶ 작성 목표: 제공된 데이터에 "[TODAYS_HOT_THEMES]" 섹션이 있다면, 이를 분석하여 오늘 한국 시장의 주도 테마를 설명하십시오.
- 이 섹션의 테마들은 오늘 한국 시장의 주인공입니다.
- 뉴스 섹션에 있는 기사(예: 현대차 로봇, CES, HBM 공급 계약 등)와 이 테마주들을 연결하여, 왜 이 테마가 떴는지 인과관계를 설명하십시오.
  - 예: "CES에서 로봇 테마가 부각되며 지능형로봇/모빌리티 테마가 +5.2% 상승, 현대오토에버(+15.2%)가 주도주로 급등"
- 테마별 주도주 정보를 활용하여, 관심 종목에 없는 종목이라도 시장 흐름 파악을 위해 언급하십시오.
- 한 줄 요약 : 오늘의 핫 테마 전체 내용에 대한 한 줄 요약을 제시하십시오.

---

### 🧑🏻‍🍳 오늘의 재료
▶ 작성 목표: 오늘 시장을 움직인 핵심 재료(상승 원인, 뉴스, 루머, 근거)를 요약하여 정리하십시오. 입력 데이터와 웹 검색 내용을 바탕으로 가장 Essential한 내용을 선별하십시오.

▶ 작성 양식 (아래 양식을 엄격히 준수하십시오):
[🇰🇷 국내]
- '재료 관련 제목': 재료에 대한 essential한 설명
[🌎 해외]
- '재료 관련 제목': 재료에 대한 essential한 설명

---

### ⚡ 단기 인사이트 (Tactical Action: 0~24시간 내 대응)
▶ 작성 목표: 시장 심리(Sentiment)와 기술적 위치(Technicals)를 분석하여 당장의 매매 전략 제시.

▶ 대상: 당장 오늘/내일 시장에 반영될 이슈, 기술적 반등/조정 위치

▶ 판단 로직:
- RSI가 30 이하이거나 뉴스가 과도한 공포를 조장하면 → "단기 과매도에 따른 기술적 반등 기회(Trading Buy)"
- RSI가 70 이상이거나 호재가 만발하면 → "단기 과열 경계 및 차익 실현(Profit Taking)"
- 오늘 예정된 경제 캘린더 이벤트가 있다면 변동성 경고
- VIX 급등락, Pre-market 선물 지수 등락 등 즉각적 이벤트 반영

▶ 포함해야 할 상세 내용:
- 트리거 분석: 최근 24시간 내 시장을 움직인 핵심 뉴스를 국내와 해외로 나누어 구체적으로 서술하십시오.
  - 🇰🇷 국내: (반도체, 2차전지 등 주요 섹터 이슈)
  - 🌎 해외: (미국 빅테크 실적, 연준 발언 등)
- 수급 및 기술적 진단: RSI, 이격도 수치를 근거로 과열/침체 여부를 지역별로 구분하여 진단하십시오. 최근 유입된 외국인/기관 수급의 강도와 MA 이격도(105% 이상 등)를 결합하여 실제 매수 유효성을 평가하십시오.
  - 🇰🇷 국내: (예: 삼성전자 RSI 75로 과열권 진입...)
  - 🌎 해외: (예: 엔비디아 RSI 80이나 모멘텀 지속...)
- 🎯 Action Plan: 그래서 지금 당장 어떻게 해야 하는지 명확한 행동 지침(매수/분할매도/관망 등)을 제시하십시오.
- 한 줄 요약 : 단기 인사이트 전체 내용에 대한 한 줄 요약을 제시하십시오.

---

### 🔭 장기 인사이트 (Strategic View: 분기/년)
▶ 작성 목표: 거시경제(Macro) 환경과 산업 트렌드(Trend)를 연결하여 자산 배분 전략 제시.

▶ 대상: 산업 트렌드(AI, 방산, 유가, 반도체, 전력 등), 금리 사이클, 인플레이션 헤지

▶ 판단 로직:
- 단기적인 등락(노이즈)을 배제하고, 펀더멘털과 거시경제 흐름에 집중
- 10년물 국채 금리 추세, 달러 인덱스 방향성 분석
- 산업 사이클: AI 혁명, 금리 인하 사이클, 원자재 슈퍼 사이클
- 기업의 성장성, 시장 점유율, 배당 매력도

▶ 포함해야 할 상세 내용:
- 매크로 환경: 미국 국채 금리, 환율, 유가 등의 흐름이 주식(위험자산)과 금(안전자산)에 어떤 환경을 조성하고 있는지 설명하십시오.
- 산업의 구조적 변화 (지역별 구분):
  - 🇰🇷 국내: (예: 메모리 반도체 사이클 회복, 수출 데이터 등)
  - 🌎 해외: (예: AI 인프라 투자 지속, 미국 금리 정책 방향성 등)
- 🎯 Action Plan: 중장기적인 포트폴리오 비중 조절(포트폴리오 확대/축소/유지/조정 시 매집/리밸런싱 등) 의견을 제시하십시오. 종목별 52주 신고가 위치 데이터를 활용하여 장기 추세 정배열 진입 여부를 고려하십시오.
- 한 줄 요약 : 장기 인사이트 전체 내용에 대한 한 줄 요약을 제시하십시오.
"""
        
        logger.info("요약 코멘트 생성 중... (단 1회 API 호출, 검색 도구 비활성화)")
        logger.info(f"프롬프트 길이: {len(prompt)}자, 입력 데이터 길이: {len(collected_data)}자")
        result, usage_info = self._call_ai(prompt)
        
        # 후처리: 종목 코드만 있는 경우 종목명 추가
        result = self._add_stock_names_to_codes(result)
        
        if usage_info:
            logger.info(f"토큰 사용량: 입력 {usage_info.get('prompt_tokens', 0)}개, 출력 {usage_info.get('completion_tokens', 0)}개, 총 {usage_info.get('total_tokens', 0)}개")
        
        logger.info("=== AI 요약 코멘트 생성 완료 ===")
        return result, usage_info
    
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

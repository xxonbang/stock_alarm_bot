"""
AI 리서치 모듈
Python이 수집한 데이터를 바탕으로 요약 코멘트 작성
"""
import os
# gRPC DNS 리졸버 설정 (DNS 해석 실패 문제 해결)
# c-ares 대신 OS의 기본 DNS 리졸버 사용
os.environ["GRPC_DNS_RESOLVER"] = "native"
os.environ["GRPC_VERBOSITY"] = "ERROR"  # 불필요한 gRPC 로그 끄기

import google.generativeai as genai
import time
import logging
from typing import Optional, Tuple, Dict

logger = logging.getLogger(__name__)


class AIResearcher:
    """AI 리서처 클래스 - 수집된 텍스트를 요약만 수행"""
    
    def __init__(self, api_key: str):
        """
        Args:
            api_key: Google AI API Key
        """
        genai.configure(api_key=api_key)
        self.api_key = api_key
        
        # 현재 지원되는 최신 모델 사용 (gemini-1.5-flash는 Deprecated)
        # gemini-2.5-flash가 현재 표준 모델
        model_name = 'models/gemini-2.5-flash'
        
        try:
            self.model = genai.GenerativeModel(model_name)
            logger.info(f"✅ 모델 선택: {model_name} (현재 지원되는 최신 모델)")
            print(f"✅ 모델 선택: {model_name} (현재 지원되는 최신 모델)")
        except Exception as e:
            # Fallback: gemini-2.0-flash 시도
            error_msg = str(e)
            logger.warning(f"모델 {model_name} 초기화 실패, fallback 시도: {error_msg[:200]}")
            print(f"⚠️ 모델 {model_name} 초기화 실패, fallback 시도 중...")
            try:
                model_name = 'models/gemini-2.0-flash'
                self.model = genai.GenerativeModel(model_name)
                logger.info(f"✅ 모델 선택 (fallback): {model_name}")
                print(f"✅ 모델 선택 (fallback): {model_name}")
            except Exception as e2:
                error_msg = f"모델 초기화 최종 실패: {str(e2)[:200]}"
                logger.error(error_msg)
                print(f"❌ {error_msg}")
                raise RuntimeError(error_msg)
    
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
        for attempt in range(max_retries):
            try:
                # Google Search 도구 비활성화: tools 파라미터를 전달하지 않음
                response = self.model.generate_content(prompt)
                
                # 토큰 사용량 정보 추출
                usage_info = {}
                if hasattr(response, 'usage_metadata'):
                    usage_metadata = response.usage_metadata
                    usage_info = {
                        'prompt_tokens': getattr(usage_metadata, 'prompt_token_count', 0),
                        'completion_tokens': getattr(usage_metadata, 'candidates_token_count', 0),
                        'total_tokens': getattr(usage_metadata, 'total_token_count', 0)
                    }
                elif hasattr(response, 'candidates') and len(response.candidates) > 0:
                    # candidates를 통해 토큰 정보 확인
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'usage_metadata'):
                        usage_metadata = candidate.usage_metadata
                        usage_info = {
                            'prompt_tokens': getattr(usage_metadata, 'prompt_token_count', 0),
                            'completion_tokens': getattr(usage_metadata, 'candidates_token_count', 0),
                            'total_tokens': getattr(usage_metadata, 'total_token_count', 0)
                        }
                
                return response.text, usage_info
            except Exception as e:
                error_str = str(e)
                
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
                    'exceeded your current quota' in error_str.lower()
                )
                is_rate_limit = (
                    '429' in error_str and 
                    not is_quota_exceeded and
                    not is_dns_error
                )
                
                if is_quota_exceeded:
                    # Quota 초과: 할당량이 모두 소진됨 (재시도해도 소용없음)
                    error_msg = f"❌ API 할당량 초과 (Quota Exceeded): 무료 티어 할당량을 모두 사용했습니다. 다음 청구 주기까지 대기하거나 유료 플랜으로 업그레이드하세요."
                    print(error_msg)
                    logger.error(error_msg)
                    logger.error(f"에러 상세: {error_str[:300]}")
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
                    logger.warning(f"AI API 호출 실패 (시도 {attempt + 1}/{max_retries}): {error_str[:200]}")
                    time.sleep(5)
                    continue
                else:
                    # 최종 실패
                    logger.error(f"AI API 호출 최종 실패: {error_str[:200]}")
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
        
        prompt = f"""당신은 월스트리트에서 20년 이상의 경력을 가진 수석 마켓 스트래티지스트(Chief Market Strategist)입니다.
당신의 임무는 제공된 [주가/기술적 지표], [매크로 지표], [뉴스 데이터]를 심층 분석하여, 투자자에게 실질적인 도움이 되는 고품질의 투자 리포트를 작성하는 것입니다.

[입력 데이터]
{collected_data}

**[분석 원칙]**
1. 인과관계 중심 서술: 단순히 "주가가 올랐다"고 하지 말고, "어떤 뉴스나 거시경제 요인이 수급을 자극하여 상승을 이끌었는지" 논리적으로 설명하십시오.
2. 뉴스 활용: 뉴스 제목을 기계적으로 나열하지 마십시오. 분석 내용 중에 "~라는 보도에 따르면", "~이슈가 부각되며"와 같이 자연스럽게 내용을 인용하여 근거를 강화하십시오.
3. 데이터 기반: RSI, 이격도, 환율, 금리 등 구체적인 수치를 언급하며 주장을 뒷받침하십시오.
4. 뉴스(A)를 인용할 경우, 주가(B)와의 인과관계를 설명하세요.
   - 예: "마두로 체포 뉴스로 인해 유가가 상승($57)하여 에너지 ETF 강세가 예상됩니다"
   - 예: "CES 기대감으로 엔비디아가 상승하면서 국내 반도체주(하이닉스) 동반 상승 가능성이 높습니다"
5. 포트폴리오(기술주, 금, 지수 ETF)와 관련 없는 잡다한 뉴스(화장품, 건설, 개별 소비재 등)는 무시하세요.
6. 주장 논리에 필요할 경우, 기술적 지표(RSI, 이격도)를 활용하여 판단하시오.
   - RSI 30 이하: 과매도 → 단기 반등 기회
   - RSI 70 이상: 과매수 → 단기 과열 경계
   - 이격도 95% 이하: 침체 → 기술적 반등 가능
   - 이격도 105% 이상: 과열 → 차익 실현 고려

**[작성 포맷 및 가이드라인]**
[가이드라인]
1. 서론 금지: "안녕하세요", "월스트리트 경력...", "종합하여 분석합니다" 같은 문장은 절대 포함하지 마십시오. 바로 '⚡ 단기 인사이트'부터 시작하십시오.
2. 핵심 위주 서술
  - 장황하게 뉴스를 나열하지 말고, 시장 움직임의 직접적인 원인(Trigger)만 콕 집어서 한 문장으로 설명하십시오.
  - '트리거 분석', '수급 진단'이 너무 장황하게 서술되는 것을 막고, [핵심 키워드] + [간결한 인과관계 문장] 형태로 압축하십시오.
3. 지역 구분 서술 (필수): 모든 분석은 [🇰🇷 국내]와 [🌎 해외]로 명확히 구분하여 서술하십시오.
4. 가독성 최적화: 
  - 불필요한 강조(**) 기호를 남발하지 마십시오.
  - 문단이 너무 길어지지 않게 하십시오.
  - 문장 및 문단의 가독성을 높이기 위해 쉬운 표현과 쉬운 문장 구조를 사용하십시오.
  - 가독성을 최대로 높일 수 있도록 적절한 줄바꿈과 이모티콘, 문장 부호를 사용하십시오.

[포멧]
다음 세 가지 섹션으로 구분하여 작성하되, 각 섹션은 요약식이 아닌 핵심내용 위주의 서술형(Paragraph) 문단으로 작성해야 합니다.

---

### 🔥 **금일 급등 예상 섹터 (나비 효과)**
**[작성 목표]**
밤사이 미국 시장에서 급등한 상위 종목들을 분석하여, 오늘 한국 주식시장에서 갭상승 출발이 유력한 '관련 테마'와 '수혜주'를 AI의 지능으로 동적 매핑하여 추론하십시오.

**[입력 데이터 확인]**
제공된 데이터에 "🔥 미국 시장 Top Movers" 섹션이 있다면, 이를 반드시 활용하십시오. 해당 섹션이 없으면 이 섹션을 생략하십시오.

**[포함해야 할 상세 내용]**
- **미국 주도주 분석:** 밤사이 미국 시장에서 급등한 상위 종목들의 섹터를 분석하십시오. (예: 바이오텍, 반도체, AI 등)
- **나비 효과 추론:** 각 미국 급등주가 한국 시장에 미칠 영향을 인과관계 중심으로 서술하십시오.
  - 예: "미국 모더나(MRNA) 급등 → 한국 삼성바이오로직스, 셀트리온 등 바이오테마 갭상승 예상"
  - 예: "엔비디아(NVDA) 급등 → 한국 삼성전자, SK하이닉스 등 반도체주 동반 상승 유력"
- **Action Plan:** 오늘 한국 시장 개장 시 주목해야 할 테마와 종목을 구체적으로 제시하십시오.

**[중요 지침]**
- 하드코딩된 종목 매핑을 사용하지 말고, AI의 지식을 활용하여 동적으로 매핑하십시오.
- 섹터별 연관성을 논리적으로 설명하되, 과도한 추측은 피하십시오.
- 한국 시장에서 실제로 거래되는 종목명을 정확히 언급하십시오.

---

### ⚡ **단기 인사이트 (Tactical Action: 0~24시간 내 대응)**
**[작성 목표]**
시장 심리(Sentiment)와 기술적 위치(Technicals)를 분석하여 당장의 매매 전략 제시.
**[대상]**
당장 오늘/내일 시장에 반영될 이슈, 기술적 반등/조정 위치
**[판단 로직]**
  - RSI가 30 이하이거나 뉴스가 과도한 공포를 조장하면 → "단기 과매도에 따른 기술적 반등 기회(Trading Buy)"
  - RSI가 70 이상이거나 호재가 만발하면 → "단기 과열 경계 및 차익 실현(Profit Taking)"
  - 오늘 예정된 경제 캘린더 이벤트가 있다면 변동성 경고
  - VIX 급등락, Pre-market 선물 지수 등락 등 즉각적 이벤트 반영
**[포함해야 할 상세 내용(아래 포멧을 반드시 준수하세요)]**
- 트리거 분석: 최근 24시간 내 시장을 움직인 핵심 뉴스를 국내와 해외로 나누어 구체적으로 서술하십시오.
  - 🇰🇷 국내: (반도체, 2차전지 등 주요 섹터 이슈)
  - 🌎 해외: (미국 빅테크 실적, 연준 발언 등)
- 수급 및 기술적 진단: RSI, 이격도 수치를 근거로 과열/침체 여부를 지역별로 구분하여 진단하십시오.
  - 🇰🇷 국내: (예: 삼성전자 RSI 75로 과열권 진입...)
  - 🌎 해외: (예: 엔비디아 RSI 80이나 모멘텀 지속...)
- Action Plan: 그래서 지금 당장 어떻게 해야 하는지 명확한 행동 지침(매수/분할매도/관망 등)을 제시하십시오.

### 🔭 **장기 인사이트 (Strategic View: 분기/년)**
**[작성 목표]**
거시경제(Macro) 환경과 산업 트렌드(Trend)를 연결하여 자산 배분 전략 제시.
**[대상]:**
AI 산업 트렌드, 금리 사이클, 인플레이션 헤지
**[판단 로직]**
  - 단기적인 등락(노이즈)을 배제하고, 펀더멘털과 거시경제 흐름에 집중
  - 10년물 국채 금리 추세, 달러 인덱스 방향성 분석
  - 산업 사이클: AI 혁명, 금리 인하 사이클, 원자재 슈퍼 사이클
  - 기업의 성장성, 시장 점유율, 배당 매력도
**[포함해야 할 상세 내용(아래 포멧을 반드시 준수하세요)]**
- 매크로 환경: 미국 국채 금리, 환율, 유가 등의 흐름이 주식(위험자산)과 금(안전자산)에 어떤 환경을 조성하고 있는지 설명하십시오.
- 산업의 구조적 변화 (지역별 구분):
  - 🇰🇷 국내: (예: 메모리 반도체 사이클 회복, 수출 데이터 등)
  - 🌎 해외: (예: AI 인프라 투자 지속, 미국 금리 정책 방향성 등)
- Action Plan: 중장기적인 포트폴리오 비중 조절(포트폴리오 확대/축소/유지/조정 시 매집/리밸런싱 등) 의견을 제시하십시오.
"""
        
        logger.info("요약 코멘트 생성 중... (단 1회 API 호출, 검색 도구 비활성화)")
        result, usage_info = self._call_ai(prompt)
        
        if usage_info:
            logger.info(f"토큰 사용량: 입력 {usage_info.get('prompt_tokens', 0)}개, 출력 {usage_info.get('completion_tokens', 0)}개, 총 {usage_info.get('total_tokens', 0)}개")
        
        logger.info("=== AI 요약 코멘트 생성 완료 ===")
        return result, usage_info


def create_researcher(api_key: str) -> AIResearcher:
    """
    AIResearcher 인스턴스 생성 헬퍼 함수
    
    Args:
        api_key: Google AI API Key
    
    Returns:
        AIResearcher 인스턴스
    """
    return AIResearcher(api_key)

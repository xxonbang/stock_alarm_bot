"""
AI 리서치 모듈
Python이 수집한 데이터를 바탕으로 요약 코멘트 작성
"""
import google.generativeai as genai
import time
import logging
from typing import Optional

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
    
    def _call_ai(self, prompt: str, max_retries: int = 5) -> str:
        """
        AI API 호출 (Exponential Backoff 적용, Rate Limit vs Quota 초과 구분)
        Google Search 도구 비활성화 (tools 파라미터 미사용)
        
        Args:
            prompt: 프롬프트
            max_retries: 최대 재시도 횟수 (기본값: 5)
        
        Returns:
            AI 응답 텍스트
        """
        for attempt in range(max_retries):
            try:
                # Google Search 도구 비활성화: tools 파라미터를 전달하지 않음
                response = self.model.generate_content(prompt)
                return response.text
            except Exception as e:
                error_str = str(e)
                
                # 429 에러 타입 구분
                is_quota_exceeded = (
                    'quota' in error_str.lower() or 
                    'Quota exceeded' in error_str or
                    'exceeded your current quota' in error_str.lower()
                )
                is_rate_limit = (
                    '429' in error_str and 
                    not is_quota_exceeded
                )
                
                if is_quota_exceeded:
                    # Quota 초과: 할당량이 모두 소진됨 (재시도해도 소용없음)
                    error_msg = f"❌ API 할당량 초과 (Quota Exceeded): 무료 티어 할당량을 모두 사용했습니다. 다음 청구 주기까지 대기하거나 유료 플랜으로 업그레이드하세요."
                    print(error_msg)
                    logger.error(error_msg)
                    logger.error(f"에러 상세: {error_str[:300]}")
                    # 텔레그램 메시지에는 간단한 메시지만 포함
                    return "API 할당량 초과(429 Error)"
                
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
                    return f"오류: {error_str[:500]}"
        
        return "오류: 최대 재시도 횟수 초과"
    
    def generate_briefing(self, collected_data: str) -> str:
        """
        Python이 수집한 데이터를 바탕으로 투자자용 요약 코멘트 작성
        
        Args:
            collected_data: Python이 수집한 주가 데이터와 뉴스 헤드라인 텍스트
        
        Returns:
            투자자용 요약 코멘트
        """
        logger.info("=== AI 요약 코멘트 생성 시작 ===")
        
        prompt = f"""당신은 골드만삭스 출신의 수석 애널리스트입니다. 아래 데이터를 바탕으로 '매수/매도/관망'에 대한 명확한 의견을 포함한 전문가 수준의 투자 리포트를 작성하세요.

[제약 조건]
1. 단순한 사실 나열을 금지합니다.
   - 금지: "주가가 올랐습니다", "하락했습니다" 같은 사후 해설
   - 권장: "매수세가 유입되어 상승 모멘텀이 지속되고 있습니다", "이익 실현 매물이 증가하여 단기 조정 가능성이 있습니다"
2. 뉴스(A)와 주가(B)의 인과관계를 반드시 설명하세요.
   - 예: "마두로 체포 뉴스로 인해 유가가 상승($57)하여 에너지 ETF 강세가 예상됩니다"
   - 예: "CES 기대감으로 엔비디아가 상승하면서 국내 반도체주(하이닉스) 동반 상승 가능성이 높습니다"
3. 포트폴리오(기술주, 금, 지수 ETF)와 관련 없는 잡다한 뉴스(화장품, 건설, 개별 소비재 등)는 무시하세요.
4. 결론에는 반드시 'Action Plan'을 한 줄로 요약하세요.
   - 예: "Action Plan: 단기적으로 기술주 비중을 10% 축소하고 현금을 확보하는 것이 유리합니다"
   - 예: "Action Plan: 금리 하락 기대감이 커지고 있어 채권 ETF 비중을 늘리는 것을 고려하세요"

[입력 데이터]
{collected_data}

[출력 형식]
<b>시장 개요:</b>
주가 움직임을 바탕으로 한 시장 전반의 흐름 분석 (2-3문장)
- 단순 상승/하락이 아닌, 매수세/매도세, 모멘텀, 트렌드 관점에서 분석

<b>뉴스 분석 및 인과관계:</b>
주요 뉴스와 주가 변동의 인과관계를 명확히 설명 (2-3문장)
- "뉴스 A → 시장 영향 B → 포트폴리오 영향 C" 형식으로 설명
- 경제 캘린더 일정이 있다면, 그 영향도 예측

<b>투자 인사이트 및 Action Plan:</b>
구체적인 투자 의견과 실행 계획 (2-3문장)
- 매수/매도/관망 중 하나를 명확히 제시
- 구체적인 비중 조정이나 타이밍 제안
- 마지막 줄에 반드시 "Action Plan: [구체적 행동]" 포함

한국어로 작성하되, 전문가 수준의 깊이 있는 분석을 제공하세요:
"""
        
        logger.info("요약 코멘트 생성 중... (단 1회 API 호출, 검색 도구 비활성화)")
        result = self._call_ai(prompt)
        
        logger.info("=== AI 요약 코멘트 생성 완료 ===")
        return result


def create_researcher(api_key: str) -> AIResearcher:
    """
    AIResearcher 인스턴스 생성 헬퍼 함수
    
    Args:
        api_key: Google AI API Key
    
    Returns:
        AIResearcher 인스턴스
    """
    return AIResearcher(api_key)

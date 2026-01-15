"""
텔레그램 알림 모듈
메시지 포맷팅 및 발송 기능
"""
import requests
import logging
from typing import List, Dict
import html

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """텔레그램 알림 클래스"""
    
    def __init__(self, token: str, chat_id: str):
        """
        Args:
            token: 텔레그램 봇 토큰
            chat_id: 채팅 ID
        """
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
    
    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        텔레그램 메시지 발송
        
        Args:
            text: 발송할 메시지 텍스트
            parse_mode: 파싱 모드 ('HTML' 또는 'Markdown')
        
        Returns:
            성공 여부
        """
        # 텔레그램 메시지 최대 길이: 4096자
        max_length = 4096
        
        # HTML 파싱 모드인 경우 지원되지 않는 태그 제거
        if parse_mode == "HTML":
            text = self._clean_html_tags(text)
        
        if len(text) <= max_length:
            # 먼저 단일 메시지로 시도
            success = self._send_single_message(text, parse_mode)
            # 400 오류로 실패했고 메시지가 충분히 길면 분할 시도
            if not success and len(text) > 3000:
                logger.info(f"단일 메시지 발송 실패, 분할 발송으로 재시도: {len(text)}자")
                return self._send_split_messages(text, parse_mode)
            return success
        else:
            # 메시지가 길면 분할 발송
            return self._send_split_messages(text, parse_mode)
    
    def _clean_html_tags(self, text: str) -> str:
        """텔레그램에서 지원하지 않는 HTML 태그 제거"""
        import re
        
        # 텔레그램이 지원하는 HTML 태그만 허용
        # 지원 태그: <b>, <i>, <u>, <s>, <code>, <pre>, <a>
        # 지원하지 않는 태그 제거: <body>, <p>, <div>, <span>, <html> 등
        
        # 지원하지 않는 태그 제거 (태그와 내용은 유지)
        unsupported_tags = ['body', 'p', 'div', 'span', 'html', 'head', 'title', 'meta', 'link', 'script', 'style']
        for tag in unsupported_tags:
            # 여는 태그 제거
            text = re.sub(rf'<{tag}[^>]*>', '', text, flags=re.IGNORECASE)
            # 닫는 태그 제거
            text = re.sub(rf'</{tag}>', '', text, flags=re.IGNORECASE)
        
        return text
    
    def _send_single_message(self, text: str, parse_mode: str) -> bool:
        """단일 메시지 발송"""
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("텔레그램 메시지 발송 성공")
            return True
        except requests.exceptions.HTTPError as e:
            # 400 Bad Request 오류인 경우 메시지 길이 또는 HTML 파싱 문제일 수 있음
            if response.status_code == 400:
                error_detail = response.text
                logger.warning(f"400 Bad Request 오류 발생: {error_detail[:200]}")
                # 메시지가 너무 길거나 HTML 파싱 오류인 경우 분할 시도
                if len(text) > 3000:  # 충분히 긴 메시지인 경우
                    logger.info(f"메시지가 길어서 분할 발송 시도: {len(text)}자")
                    return False  # False를 반환하여 상위에서 분할 처리하도록
            logger.error(f"텔레그램 메시지 발송 실패: {e}")
            return False
        except Exception as e:
            logger.error(f"텔레그램 메시지 발송 실패: {e}")
            return False
    
    def _send_split_messages(self, text: str, parse_mode: str) -> bool:
        """긴 메시지를 분할하여 발송 (HTML 태그 고려)"""
        max_length = 4096
        # 헤더 공간 확보 (분할 헤더 + 여유 공간)
        header_length = 50  # "<b>(1/3)</b>\n\n" 형태
        chunk_size = max_length - header_length - 100  # 안전 마진
        
        parts = []
        
        if parse_mode == "HTML":
            # HTML 태그를 고려한 스마트 분할
            parts = self._split_html_message(text, chunk_size)
        else:
            # 일반 텍스트 분할
            for i in range(0, len(text), chunk_size):
                chunk = text[i:i + chunk_size]
                parts.append(chunk)
        
        success = True
        for i, part in enumerate(parts):
            # 분할 헤더 추가 (간단한 형식)
            part_text = f"<b>({i+1}/{len(parts)})</b>\n\n{part}"
            
            # 최종 길이 확인
            if len(part_text) > max_length:
                logger.warning(f"분할 메시지 {i+1}이 여전히 너무 깁니다 ({len(part_text)}자). 추가 분할 시도...")
                # 추가 분할 필요
                sub_parts = self._split_html_message(part, chunk_size - header_length) if parse_mode == "HTML" else [part[j:j+chunk_size-header_length] for j in range(0, len(part), chunk_size-header_length)]
                for j, sub_part in enumerate(sub_parts):
                    sub_part_text = f"<b>({i+1}-{j+1}/{len(parts)})</b>\n\n{sub_part}"
                    if not self._send_single_message(sub_part_text, parse_mode):
                        success = False
                    import time
                    time.sleep(1)
            else:
                if not self._send_single_message(part_text, parse_mode):
                    success = False
                # 연속 발송 방지를 위한 짧은 대기
                import time
                time.sleep(1)
        
        return success
    
    def _split_html_message(self, text: str, chunk_size: int) -> List[str]:
        """HTML 태그를 고려한 메시지 분할 (줄 단위 분할로 HTML 태그 보존)"""
        import re
        
        parts = []
        current_chunk = ""
        current_length = 0
        
        # 줄 단위로 분할 (HTML 태그가 줄 단위로 완성되도록)
        lines = text.split('\n')
        
        for line in lines:
            line_with_newline = line + '\n'
            line_length = len(line_with_newline)
            
            # 현재 청크에 추가할 수 있는지 확인
            if current_length + line_length > chunk_size and current_chunk:
                # 현재 청크 저장
                parts.append(current_chunk.rstrip())
                # 새 청크 시작
                current_chunk = line_with_newline
                current_length = line_length
            else:
                current_chunk += line_with_newline
                current_length += line_length
        
        # 마지막 청크 추가
        if current_chunk:
            parts.append(current_chunk.rstrip())
        
        # 각 청크의 HTML 유효성 검증 및 수정
        validated_parts = []
        for part in parts:
            # 열린 태그와 닫힌 태그 개수 확인
            open_tags = re.findall(r'<([^/>][^>]*)>', part)
            close_tags = re.findall(r'</([^>]+)>', part)
            
            # 주요 태그만 추적 (b, i, u, code, pre 등)
            major_tags = ['b', 'i', 'u', 'code', 'pre', 'strong', 'em']
            open_major = [tag.split()[0] for tag in open_tags if tag.split()[0] in major_tags]
            close_major = [tag.split()[0] for tag in close_tags if tag.split()[0] in major_tags]
            
            # 열린 태그가 더 많으면 닫기
            if len(open_major) > len(close_major):
                diff = len(open_major) - len(close_major)
                # 열린 순서의 역순으로 닫기
                tags_to_close = open_major[-diff:]
                for tag in reversed(tags_to_close):
                    part += f'</{tag}>'
            
            validated_parts.append(part)
        
        return validated_parts if validated_parts else [text]
    
    def format_stock_report(self, analysis_results: List[Dict]) -> str:
        """
        주식 분석 결과를 텔레그램 메시지 형식으로 포맷팅
        
        Args:
            analysis_results: analysis.py의 analyze_all_tickers 결과
        
        Returns:
            포맷팅된 메시지 텍스트
        """
        message = "<b>📊 나의 보유 종목 현황</b>\n\n"
        
        for result in analysis_results:
            ticker = result['ticker']
            current_price = result['current_price']
            returns = result['returns']
            
            # 현재가 포맷팅
            if isinstance(current_price, (int, float)):
                price_str = f"${current_price:.2f}" if current_price >= 1 else f"${current_price:.4f}"
            else:
                price_str = str(current_price)
            
            message += f"<b>{ticker}</b>: {price_str}\n"
            
            # 수익률 표시
            if returns:
                # 주요 기간만 표시
                key_periods = ['1D', '1W', '1M', '3M', '6M', '1Y']
                return_strs = []
                for period in key_periods:
                    if period in returns:
                        val = returns[period]
                        if isinstance(val, (int, float)):
                            sign = "📈" if val >= 0 else "📉"
                            return_strs.append(f"{sign} {val:+.2f}% ({period})")
                
                if return_strs:
                    message += "  " + " / ".join(return_strs) + "\n"
            
            message += "\n"
        
        return message
    
    def format_ai_report(self, ai_report: str) -> str:
        """
        AI 리포트를 텔레그램 메시지 형식으로 포맷팅
        
        Args:
            ai_report: AI 리포트 텍스트
        
        Returns:
            포맷팅된 메시지 텍스트
        """
        message = "<b>🤖 AI 일일 리포트</b>\n\n"
        message += "<i>Google Gemini Pro 기반 전문가 수준 분석</i>\n\n"
        message += "─" * 30 + "\n\n"
        
        # HTML 이스케이프 처리
        escaped_report = html.escape(ai_report)
        
        # 섹션별로 포맷팅 개선
        lines = escaped_report.split('\n')
        formatted_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                formatted_lines.append("")
                continue
            
            # 제목 감지 및 포맷팅
            if any(keyword in line.upper() for keyword in ['SUMMARY', 'SENTIMENT', 'SECTORS', 'RISK', 'CONCLUSION', 'EXECUTIVE']):
                formatted_lines.append(f"\n<b>{line}</b>\n")
            elif line.startswith('-') or line.startswith('•'):
                formatted_lines.append(f"  {line}")
            elif any(line.startswith(str(i) + '.') for i in range(1, 10)):
                formatted_lines.append(f"<b>{line}</b>")
            else:
                formatted_lines.append(line)
        
        message += "\n".join(formatted_lines)
        return message
    
    def send_daily_report(self, stock_results: List[Dict], ai_report: str) -> bool:
        """
        일일 리포트 전체 발송
        
        Args:
            stock_results: 주식 분석 결과
            ai_report: AI 리포트
        
        Returns:
            성공 여부
        """
        # 1부: 주식 현황
        stock_message = self.format_stock_report(stock_results)
        success1 = self.send_message(stock_message)
        
        # 짧은 대기
        import time
        time.sleep(1)
        
        # 2부: AI 리포트
        ai_message = self.format_ai_report(ai_report)
        success2 = self.send_message(ai_message)
        
        return success1 and success2


def create_notifier(token: str, chat_id: str) -> TelegramNotifier:
    """
    TelegramNotifier 인스턴스 생성 헬퍼 함수
    
    Args:
        token: 텔레그램 봇 토큰
        chat_id: 채팅 ID
    
    Returns:
        TelegramNotifier 인스턴스
    """
    return TelegramNotifier(token, chat_id)



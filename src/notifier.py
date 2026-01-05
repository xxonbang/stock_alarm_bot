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
        
        if len(text) <= max_length:
            return self._send_single_message(text, parse_mode)
        else:
            # 메시지가 길면 분할 발송
            return self._send_split_messages(text, parse_mode)
    
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
        except Exception as e:
            logger.error(f"텔레그램 메시지 발송 실패: {e}")
            return False
    
    def _send_split_messages(self, text: str, parse_mode: str) -> bool:
        """긴 메시지를 분할하여 발송"""
        max_length = 4096
        parts = []
        
        # 메시지를 4000자 단위로 분할 (여유 공간 확보)
        chunk_size = 4000
        for i in range(0, len(text), chunk_size):
            chunk = text[i:i + chunk_size]
            parts.append(chunk)
        
        success = True
        for i, part in enumerate(parts):
            part_text = f"<b>[{i+1}/{len(parts)}]</b>\n\n{part}"
            if not self._send_single_message(part_text, parse_mode):
                success = False
            # 연속 발송 방지를 위한 짧은 대기
            import time
            time.sleep(1)
        
        return success
    
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



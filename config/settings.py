"""
설정 로더 모듈
환경변수와 config.yaml을 로드하여 사용
"""
import os
import yaml
from pathlib import Path

# .env 파일 로드 (로컬 개발용)
try:
    from dotenv import load_dotenv
    # 프로젝트 루트의 .env 파일 로드
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    # python-dotenv가 설치되지 않은 경우 무시 (GitHub Actions에서는 환경변수 사용)
    pass


def load_config():
    """config.yaml 파일을 로드"""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_env_var(key: str, default: str = None) -> str:
    """환경변수에서 값을 가져옴 (GitHub Secrets 또는 .env 파일)"""
    value = os.getenv(key, default)
    if value is None:
        raise ValueError(f"환경변수 {key}가 설정되지 않았습니다. GitHub Secrets 또는 .env 파일을 확인하세요.")
    return value


class Settings:
    """애플리케이션 설정 클래스"""
    
    def __init__(self):
        config = load_config()
        
        # 카테고리별로 티커 저장 (빈 리스트는 None 또는 빈 리스트로 유지)
        self.tickers_possession_domestic = config.get('tickers_possession_domestic', []) or []
        self.tickers_possession_overseas = config.get('tickers_possession_overseas', []) or []
        self.tickers_interest_domestic = config.get('tickers_interest_domestic', []) or []
        self.tickers_interest_overseas = config.get('tickers_interest_overseas', []) or []
        
        # 전체 티커 리스트 (분석용)
        all_tickers = []
        all_tickers.extend(self.tickers_possession_domestic)
        all_tickers.extend(self.tickers_possession_overseas)
        all_tickers.extend(self.tickers_interest_domestic)
        all_tickers.extend(self.tickers_interest_overseas)
        
        # 중복 제거 및 정렬
        self.tickers = sorted(list(set(all_tickers)))
        self.schedule_times = config.get('schedule_times', [])
        
        # API Keys (환경변수에서 로드)
        # 주의: 실제 키는 GitHub Secrets 또는 .env 파일에 저장
        self.telegram_token = get_env_var('TELEGRAM_TOKEN')
        self.chat_id = get_env_var('CHAT_ID')
        
        # Google API Keys (01, 02로 구분)
        # 01번 키 (기존), 02번 키 (신규)
        self.google_api_key_01 = get_env_var('GOOGLE_API_KEY_01')
        self.google_api_key_02 = get_env_var('GOOGLE_API_KEY_02')
        
        # 기본값은 01번 키 (하위 호환성)
        self.google_api_key = self.google_api_key_01
    
    def __repr__(self):
        return f"Settings(tickers={len(self.tickers)}개, schedule_times={len(self.schedule_times)}개)"


# 싱글톤 인스턴스
settings = Settings()


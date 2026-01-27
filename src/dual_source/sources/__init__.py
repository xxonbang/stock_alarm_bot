"""
듀얼 소스 시스템 - 데이터 소스 모듈

Source A: Agentic Screenshot (Playwright + Gemini Vision AI)
Source B: 전통적 API (pykrx, KRX API, 네이버 크롤링, yfinance)
추가 소스:
  - KIS API: 한국투자증권 공식 API (한국 주식)
  - Finnhub: 글로벌 주식 시세 (미국 주식 Fallback)
  - FMP: Financial Modeling Prep (미국 주식 Fallback, 재무데이터)
"""
from .base import DataSourceBase
from .agentic_source import AgenticScreenshotSource
from .api_source import TraditionalAPISource
from .kis_source import KISSource, get_kis_token_manager
from .finnhub_source import FinnhubSource
from .fmp_source import FMPSource
from .twelvedata_source import TwelveDataSource

__all__ = [
    'DataSourceBase',
    'AgenticScreenshotSource',
    'TraditionalAPISource',
    'KISSource',
    'FinnhubSource',
    'FMPSource',
    'TwelveDataSource',
    'get_kis_token_manager',
]

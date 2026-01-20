"""
듀얼 소스 시스템 - 데이터 소스 모듈

Source A: Agentic Screenshot (Playwright + Gemini Vision AI)
Source B: 전통적 API (pykrx, KRX API, 네이버 크롤링, yfinance)
"""
from .base import DataSourceBase
from .agentic_source import AgenticScreenshotSource
from .api_source import TraditionalAPISource

__all__ = [
    'DataSourceBase',
    'AgenticScreenshotSource',
    'TraditionalAPISource',
]

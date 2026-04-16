"""
포트폴리오 관리 모듈
Supabase CRUD + config.yaml fallback
"""
import os
import logging
from typing import Optional, Dict, List
from datetime import date

logger = logging.getLogger(__name__)


def _detect_market(ticker: str) -> str:
    """종목코드로 국내/해외 자동판별"""
    if ticker.endswith('.KS') or ticker.endswith('.KQ'):
        return 'domestic'
    return 'overseas'


ALLOWED_UPDATE_FIELDS = {'buy_price', 'buy_quantity', 'buy_date', 'name'}


class PortfolioManager:
    """Supabase 기반 포트폴리오 CRUD"""

    def __init__(self):
        self._client = None
        self._available = False
        self._init_supabase()

    def _init_supabase(self):
        try:
            from config.supabase_credentials import get_supabase_credentials_manager
            manager = get_supabase_credentials_manager()
            if manager.is_supabase_available:
                self._client = manager._client
                self._available = True
        except Exception as e:
            logger.warning(f"Supabase 연결 실패: {e}")

    @property
    def is_available(self) -> bool:
        return self._available

    def add(self, ticker: str, name: str, category: str,
            buy_price: Optional[float] = None,
            buy_quantity: Optional[int] = None,
            buy_date: Optional[date] = None) -> bool:
        """종목 추가"""
        if not self._available:
            logger.error("Supabase 미연결")
            return False

        try:
            data = {
                'ticker': ticker,
                'name': name,
                'category': category,
                'market': _detect_market(ticker),
            }
            if buy_price is not None:
                data['buy_price'] = buy_price
            if buy_quantity is not None:
                data['buy_quantity'] = buy_quantity
            if buy_date is not None:
                data['buy_date'] = buy_date.isoformat()

            self._client.table('portfolio').insert(data).execute()
            logger.info(f"포트폴리오 추가: {name} ({ticker})")
            return True
        except Exception as e:
            logger.error(f"포트폴리오 추가 실패: {e}")
            return False

    def update(self, portfolio_id: str, field: str, value) -> bool:
        """
        포트폴리오 단일 필드 업데이트

        Args:
            portfolio_id: Supabase id (uuid)
            field: 'buy_price' | 'buy_quantity' | 'buy_date' | 'name'
            value: 새 값 (buy_date는 date 또는 None)
        """
        if not self._available:
            logger.error("Supabase 미연결")
            return False

        if field not in ALLOWED_UPDATE_FIELDS:
            logger.error(f"허용되지 않은 필드: {field}")
            return False

        try:
            if field == 'buy_date':
                payload = {field: value.isoformat() if value is not None else None}
            else:
                payload = {field: value}

            self._client.table('portfolio') \
                .update(payload) \
                .eq('id', portfolio_id) \
                .execute()
            logger.info(f"포트폴리오 업데이트: {portfolio_id} {field}={value}")
            return True
        except Exception as e:
            logger.error(f"포트폴리오 업데이트 실패: {e}")
            return False

    def delete(self, portfolio_id: str) -> bool:
        """종목 삭제 (id 기준)"""
        if not self._available:
            return False

        try:
            self._client.table('portfolio').delete().eq('id', portfolio_id).execute()
            logger.info(f"포트폴리오 삭제: {portfolio_id}")
            return True
        except Exception as e:
            logger.error(f"포트폴리오 삭제 실패: {e}")
            return False

    def list_by_category(self, category: str) -> List[Dict]:
        """카테고리별 종목 조회"""
        if not self._available:
            return []

        try:
            response = self._client.table('portfolio') \
                .select('*') \
                .eq('category', category) \
                .order('created_at') \
                .execute()
            return response.data or []
        except Exception as e:
            logger.error(f"포트폴리오 조회 실패: {e}")
            return []

    def list_all(self) -> List[Dict]:
        """전체 종목 조회"""
        if not self._available:
            return []

        try:
            response = self._client.table('portfolio') \
                .select('*') \
                .order('category,created_at') \
                .execute()
            return response.data or []
        except Exception as e:
            logger.error(f"포트폴리오 조회 실패: {e}")
            return []

    def get_tickers_by_category(self) -> Optional[Dict[str, List[str]]]:
        """
        settings.py 연동용: 카테고리별 티커 리스트 반환

        Returns:
            {
                'possession_domestic': ['000660.KS', ...],
                'possession_overseas': ['AAPL', ...],
                'interest_domestic': [...],
                'interest_overseas': [...],
            }
            또는 Supabase 미연결 시 None
        """
        if not self._available:
            return None

        try:
            response = self._client.table('portfolio') \
                .select('ticker, category, market') \
                .execute()

            if not response.data:
                return None

            result = {
                'possession_domestic': [],
                'possession_overseas': [],
                'interest_domestic': [],
                'interest_overseas': [],
            }

            for row in response.data:
                key = f"{row['category']}_{row['market']}"
                if key in result:
                    result[key].append(row['ticker'])

            return result
        except Exception as e:
            logger.error(f"포트폴리오 티커 조회 실패: {e}")
            return None

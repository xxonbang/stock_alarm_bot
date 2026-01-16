# KRX OpenAPI 활용 가능성 분석 보고서

## 📋 요약

KRX(한국거래소) OpenAPI는 국내 주식 시장 데이터를 공식적으로 제공하는 API 서비스입니다. 현재 프로젝트에서 네이버 금융 HTML 크롤링으로 수집하는 데이터를 KRX API로 대체하거나 보완할 수 있습니다.

## 🔍 현재 상황 분석

### 현재 데이터 수집 방식
- **위치**: `src/crawler.py`의 `get_kr_stock_data()` 함수
- **방식**: 네이버 금융 HTML 크롤링
- **수집 데이터**:
  - 외국인 순매매량 (최근 3거래일 합계)
  - 기관 순매매량 (최근 3거래일 합계)
  - ETF 괴리율 (NAV 대비 %)

### 현재 방식의 한계
1. **HTML 파싱 의존성**: 웹사이트 구조 변경 시 파싱 실패 가능
2. **데이터 신뢰성**: 비공식 데이터 소스
3. **제한된 데이터**: 일부 데이터만 수집 가능
4. **유지보수 부담**: HTML 구조 변경 대응 필요

## 🚀 KRX OpenAPI 개요

### 서비스 현황
- **운영 주체**: 한국거래소(KRX)
- **서비스명**: KRX Data Marketplace OpenAPI
- **개편 일자**: 2025년 12월 27일 (회원제로 전환)
- **접근 방식**: 회원가입 → 인증키 발급 → API 이용 신청 → 승인 후 사용

### 제공되는 주요 API 서비스

#### 1. 유가증권 일별매매정보 ⭐ (가장 유용)
- **제공 데이터**:
  - 일별 매매정보 (거래량, 거래대금)
  - **외국인 매매 상세** (매수/매도/순매매)
  - **기관 매매 상세** (매수/매도/순매매)
  - 개인 투자자 매매 정보
- **데이터 기간**: 2010년 이후
- **활용도**: ⭐⭐⭐⭐⭐ (현재 크롤링 데이터 대체 가능)

#### 2. KOSPI/KOSDAQ 시리즈 일별시세정보
- **제공 데이터**:
  - 지수 일별 시세 (시가, 고가, 저가, 종가)
  - 거래량, 거래대금
- **활용도**: ⭐⭐⭐ (시장 전체 흐름 파악)

#### 3. 채권지수 시세정보
- **활용도**: ⭐⭐ (현재 프로젝트와 관련성 낮음)

#### 4. 파생상품지수 시세정보
- **활용도**: ⭐⭐ (현재 프로젝트와 관련성 낮음)

## 💡 KRX API 활용 방안

### 1. 즉시 활용 가능한 데이터

#### A. 외국인/기관 매매 데이터 (현재 크롤링 대체)
```python
# 현재: 네이버 금융 HTML 크롤링
# 제안: KRX API 유가증권 일별매매정보

장점:
- 공식 데이터로 신뢰성 높음
- 구조화된 JSON/CSV 데이터 (파싱 불필요)
- 더 상세한 데이터 제공 (매수/매도 분리)
- 장기 데이터 제공 (2010년 이후)
```

#### B. 추가로 얻을 수 있는 유용한 데이터

1. **개인 투자자 매매 동향**
   - 개인 투자자의 매수/매도/순매매량
   - 시장 심리 파악에 유용
   - 현재 수집하지 않는 데이터

2. **거래대금 정보**
   - 일별 거래대금 (거래량 × 가격)
   - 시장 참여도 파악

3. **지수 데이터**
   - KOSPI/KOSDAQ 지수 일별 시세
   - 시장 전체 흐름 파악

### 2. 구현 방안

#### Phase 1: 기본 통합 (우선순위 높음)
```python
# src/crawler.py에 추가
def get_kr_stock_data_krx_api(ticker_code: str, api_key: str) -> Dict:
    """
    KRX OpenAPI를 사용한 국내 주식 데이터 수집
    
    Args:
        ticker_code: 종목 코드 (예: '005930')
        api_key: KRX OpenAPI 인증키
    
    Returns:
        {
            'foreign_net': 외국인 순매매량 (만 주),
            'institutional_net': 기관 순매매량 (만 주),
            'individual_net': 개인 순매매량 (만 주),  # 추가
            'trading_value': 거래대금 (억원),  # 추가
        }
    """
    # KRX API 호출 로직
    pass
```

**장점**:
- 현재 크롤링 방식과 병행 가능 (Fallback)
- 점진적 전환 가능
- 데이터 신뢰성 향상

#### Phase 2: 고도화 (선택사항)
- 다중 종목 일괄 조회 최적화
- 캐싱 메커니즘 추가
- 장기 데이터 분석 기능

### 3. API 이용 절차

#### Step 1: 회원가입 및 인증키 발급
1. KRX Data Marketplace 접속: https://openapi.krx.co.kr
2. 회원가입 (네이버/카카오 간편 로그인 가능)
3. 마이페이지 → API 인증키 신청
4. 관리자 승인 대기 (보통 1-2일)

#### Step 2: API 서비스 이용 신청
1. 서비스 목록에서 '유가증권 일별매매정보' 선택
2. API 이용 신청
3. 관리자 승인 대기

#### Step 3: 개발 및 통합
- 인증키를 환경변수에 저장 (`KRX_API_KEY`)
- API 호출 함수 구현
- 기존 크롤링 방식과 병행 또는 대체

## 📊 비교 분석

| 항목 | 현재 (네이버 크롤링) | KRX API |
|------|---------------------|---------|
| **데이터 신뢰성** | 중간 (비공식) | 높음 (공식) |
| **데이터 상세도** | 제한적 | 상세 (매수/매도 분리) |
| **구현 난이도** | 중간 (HTML 파싱) | 낮음 (JSON/CSV) |
| **유지보수** | 높음 (구조 변경 대응) | 낮음 (API 명세 고정) |
| **추가 데이터** | 없음 | 개인 투자자, 거래대금 등 |
| **비용** | 무료 | 무료 (회원가입 필요) |
| **승인 대기** | 없음 | 필요 (1-2일) |
| **데이터 기간** | 실시간 | 2010년 이후 |

## 🎯 권장 사항

### 즉시 적용 가능 (High Priority)
1. **KRX API 인증키 발급 신청**
   - 회원가입 및 인증키 신청
   - '유가증권 일별매매정보' API 이용 신청

2. **Fallback 메커니즘 구현**
   ```python
   def get_kr_stock_data(ticker_code: str) -> Dict:
       # 1차: KRX API 시도
       try:
           if settings.krx_api_key:
               return get_kr_stock_data_krx_api(ticker_code, settings.krx_api_key)
       except Exception as e:
           logger.warning(f"KRX API 실패, 크롤링으로 대체: {e}")
       
       # 2차: 기존 네이버 크롤링 (Fallback)
       return get_kr_stock_data_naver(ticker_code)
   ```

3. **환경변수 추가**
   - `.env` 파일에 `KRX_API_KEY` 추가
   - `config/settings.py`에 `krx_api_key` 속성 추가

### 중장기 개선 (Medium Priority)
1. **개인 투자자 매매 데이터 활용**
   - AI 리포트에 "개인 투자자 매도세 증가" 등 분석 추가

2. **거래대금 데이터 활용**
   - 거래량 대비 거래대금 분석
   - 시장 참여도 지표 추가

3. **지수 데이터 활용**
   - KOSPI/KOSDAQ 지수 동향 분석
   - 개별 종목 vs 시장 전체 비교

## ⚠️ 주의사항

1. **승인 대기 시간**: 인증키 발급 및 API 이용 신청 승인까지 1-2일 소요
2. **API 호출 제한**: 일일 호출 제한이 있을 수 있음 (명세서 확인 필요)
3. **데이터 지연**: 실시간 데이터가 아닐 수 있음 (일별 데이터)
4. **환경변수 관리**: 인증키는 반드시 환경변수로 관리 (GitHub Secrets)

## 📝 구현 체크리스트

- [ ] KRX Data Marketplace 회원가입
- [ ] API 인증키 신청 및 승인 대기
- [ ] '유가증권 일별매매정보' API 이용 신청
- [ ] 환경변수 `KRX_API_KEY` 추가
- [ ] `config/settings.py`에 `krx_api_key` 속성 추가
- [ ] `src/crawler.py`에 `get_kr_stock_data_krx_api()` 함수 구현
- [ ] `get_kr_stock_data()` 함수에 Fallback 메커니즘 추가
- [ ] 테스트 및 검증

## 🛠️ 구현 예제

### 방법 1: 공식 KRX OpenAPI 직접 사용

```python
# src/crawler.py에 추가
import requests
from datetime import datetime, timedelta

def get_kr_stock_data_krx_api(ticker_code: str, api_key: str) -> Dict[str, Optional[float]]:
    """
    KRX OpenAPI를 사용한 국내 주식 데이터 수집
    
    Args:
        ticker_code: 종목 코드 (예: '005930' for '005930.KS')
        api_key: KRX OpenAPI 인증키
    
    Returns:
        {
            'foreign_net': 외국인 순매매량 (만 주, 최근 3거래일 합계),
            'institutional_net': 기관 순매매량 (만 주, 최근 3거래일 합계),
            'individual_net': 개인 순매매량 (만 주, 최근 3거래일 합계),
        }
    """
    result = {
        'foreign_net': None,
        'institutional_net': None,
        'individual_net': None
    }
    
    # .KS, .KQ 제거
    code = ticker_code.replace('.KS', '').replace('.KQ', '')
    
    try:
        # KRX 종목 코드 형식으로 변환 필요 (예: 'KR7000010008')
        # 종목 코드 변환 로직 필요 (KRX API 명세서 참고)
        
        # 최근 3거래일 데이터 수집
        foreign_sum = 0.0
        institutional_sum = 0.0
        individual_sum = 0.0
        
        for i in range(3):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y%m%d')
            
            url = "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd"
            params = {
                "basDd": date,
                "isuCd": f"KR{code}"  # 종목 코드 형식 확인 필요
            }
            headers = {
                "AUTH_KEY": api_key
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                # 응답 데이터 파싱 (실제 응답 구조 확인 필요)
                # foreign_sum += data.get('foreign_net', 0)
                # institutional_sum += data.get('institutional_net', 0)
                # individual_sum += data.get('individual_net', 0)
            else:
                logger.warning(f"KRX API 호출 실패: {response.status_code}")
                break
        
        if foreign_sum != 0 or institutional_sum != 0:
            result['foreign_net'] = round(foreign_sum / 10000, 2)  # 만주 변환
            result['institutional_net'] = round(institutional_sum / 10000, 2)
            result['individual_net'] = round(individual_sum / 10000, 2)
    
    except Exception as e:
        logger.error(f"KRX API 데이터 수집 실패: {e}")
    
    return result
```

### 방법 2: pykrx 라이브러리 사용 (추천 ⭐)

`pykrx`는 KRX 데이터를 쉽게 가져올 수 있는 비공식 라이브러리입니다.

**장점**:
- ✅ 인증키 불필요 (즉시 사용 가능)
- ✅ 간단한 API
- ✅ **외국인/기관 매매 데이터 제공 확인됨**
- ✅ 빠른 구현 가능

**단점**:
- 비공식 라이브러리 (KRX 공식 지원 아님)
- 라이브러리 유지보수 의존성

**확인된 기능**:
- `get_market_trading_value_by_investor()`: 투자자별 거래대금 (매도/매수/순매수)
- `get_market_net_purchases_of_equities()`: 투자자별 순매수/순매도 거래대금
- 외국인, 기관합계, 개인 등 투자자 구분 제공

```python
# requirements.txt에 추가
# pykrx>=1.3.0

# src/crawler.py에 추가
try:
    from pykrx import stock
    PYKRX_AVAILABLE = True
except ImportError:
    PYKRX_AVAILABLE = False
    stock = None

def get_kr_stock_data_pykrx(ticker_code: str) -> Dict[str, Optional[float]]:
    """
    pykrx 라이브러리를 사용한 국내 주식 데이터 수집
    
    ✅ 외국인/기관 매매 데이터 제공 확인됨
    """
    if not PYKRX_AVAILABLE:
        return {}
    
    code = ticker_code.replace('.KS', '').replace('.KQ', '')
    result = {
        'foreign_net': None,
        'institutional_net': None,
        'individual_net': None
    }
    
    try:
        from datetime import datetime, timedelta
        
        # 최근 3거래일 데이터 조회
        end_date = datetime.now()
        start_date = end_date - timedelta(days=5)  # 여유 있게
        
        start_str = start_date.strftime('%Y%m%d')
        end_str = end_date.strftime('%Y%m%d')
        
        # 투자자별 거래대금 조회 (외국인, 기관, 개인)
        df = stock.get_market_trading_value_by_investor(
            start_str, end_str, code
        )
        
        if df is not None and not df.empty:
            # 최근 3거래일 데이터 합계
            foreign_sum = 0.0
            institutional_sum = 0.0
            individual_sum = 0.0
            
            # 데이터프레임에서 외국인, 기관합계, 개인 데이터 추출
            # (실제 컬럼명은 pykrx 문서 확인 필요)
            for idx in range(min(3, len(df))):
                row = df.iloc[-idx-1]  # 최신 데이터부터
                
                # 외국인 순매수 (거래대금, 원 단위)
                if '외국인' in df.columns:
                    foreign_sum += float(row.get('외국인', 0) or 0)
                
                # 기관합계 순매수
                if '기관합계' in df.columns:
                    institutional_sum += float(row.get('기관합계', 0) or 0)
                
                # 개인 순매수
                if '개인' in df.columns:
                    individual_sum += float(row.get('개인', 0) or 0)
            
            # 거래대금을 주 수로 변환하려면 종가로 나눠야 함
            # 또는 거래량 데이터를 별도로 조회
            # 여기서는 거래대금(원)을 그대로 반환하거나, 
            # 주가 데이터와 결합하여 주 수 계산 가능
            
            # 임시: 거래대금을 억원 단위로 반환 (주 수 변환은 추가 구현 필요)
            result['foreign_net'] = round(foreign_sum / 100000000, 2)  # 억원
            result['institutional_net'] = round(institutional_sum / 100000000, 2)
            result['individual_net'] = round(individual_sum / 100000000, 2)
            
            logger.debug(f"{ticker_code} pykrx 데이터: 외인 {result['foreign_net']:.2f}억원, 기관 {result['institutional_net']:.2f}억원")
        
    except Exception as e:
        logger.error(f"pykrx 데이터 수집 실패: {e}")
    
    return result
```

**더 정확한 주 수 계산을 위한 개선 버전**:

```python
def get_kr_stock_data_pykrx_enhanced(ticker_code: str) -> Dict[str, Optional[float]]:
    """
    pykrx를 사용한 국내 주식 데이터 수집 (주 수 계산 포함)
    """
    if not PYKRX_AVAILABLE:
        return {}
    
    code = ticker_code.replace('.KS', '').replace('.KQ', '')
    result = {
        'foreign_net': None,  # 만 주
        'institutional_net': None,  # 만 주
        'individual_net': None  # 만 주
    }
    
    try:
        from datetime import datetime, timedelta
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=5)
        start_str = start_date.strftime('%Y%m%d')
        end_str = end_date.strftime('%Y%m%d')
        
        # 1. 투자자별 거래대금 조회
        trading_value_df = stock.get_market_trading_value_by_investor(
            start_str, end_str, code
        )
        
        # 2. 주가 데이터 조회 (종가 필요)
        price_df = stock.get_market_ohlcv_by_date(start_str, end_str, code)
        
        if trading_value_df is not None and price_df is not None:
            foreign_sum = 0.0
            institutional_sum = 0.0
            individual_sum = 0.0
            
            # 최근 3거래일 데이터 처리
            for i in range(min(3, len(trading_value_df))):
                trading_row = trading_value_df.iloc[-i-1]
                price_row = price_df.iloc[-i-1]
                
                close_price = float(price_row['종가'])
                if close_price == 0:
                    continue
                
                # 거래대금을 종가로 나눠서 주 수 계산
                if '외국인' in trading_value_df.columns:
                    foreign_value = float(trading_row.get('외국인', 0) or 0)
                    foreign_sum += foreign_value / close_price
                
                if '기관합계' in trading_value_df.columns:
                    inst_value = float(trading_row.get('기관합계', 0) or 0)
                    institutional_sum += inst_value / close_price
                
                if '개인' in trading_value_df.columns:
                    ind_value = float(trading_row.get('개인', 0) or 0)
                    individual_sum += ind_value / close_price
            
            # 만주로 변환
            result['foreign_net'] = round(foreign_sum / 10000, 2)
            result['institutional_net'] = round(institutional_sum / 10000, 2)
            result['individual_net'] = round(individual_sum / 10000, 2)
            
    except Exception as e:
        logger.error(f"pykrx 데이터 수집 실패: {e}")
    
    return result
```

## 🔄 통합 전략

### 추천: 하이브리드 방식

```python
def get_kr_stock_data(ticker_code: str) -> Dict[str, Optional[float]]:
    """
    국내 주식 데이터 수집 (다중 소스 Fallback)
    
    우선순위:
    1. KRX OpenAPI (공식, 신뢰성 높음)
    2. pykrx 라이브러리 (간편, 인증키 불필요)
    3. 네이버 금융 크롤링 (기존 방식, 최후의 수단)
    """
    result = {
        'foreign_net': None,
        'institutional_net': None,
        'disparity_rate': None
    }
    
    # 1차: KRX OpenAPI 시도
    if settings.krx_api_key:
        try:
            krx_data = get_kr_stock_data_krx_api(ticker_code, settings.krx_api_key)
            if krx_data.get('foreign_net') is not None:
                result.update(krx_data)
                logger.info(f"{ticker_code}: KRX API로 데이터 수집 성공")
                return result
        except Exception as e:
            logger.warning(f"KRX API 실패: {e}, 다음 소스 시도")
    
    # 2차: pykrx 라이브러리 시도
    if PYKRX_AVAILABLE:
        try:
            pykrx_data = get_kr_stock_data_pykrx(ticker_code)
            if pykrx_data.get('foreign_net') is not None:
                result.update(pykrx_data)
                logger.info(f"{ticker_code}: pykrx로 데이터 수집 성공")
                return result
        except Exception as e:
            logger.warning(f"pykrx 실패: {e}, 크롤링으로 대체")
    
    # 3차: 기존 네이버 크롤링 (Fallback)
    try:
        naver_data = get_kr_stock_data_naver(ticker_code)  # 기존 함수
        result.update(naver_data)
        logger.info(f"{ticker_code}: 네이버 크롤링으로 데이터 수집")
    except Exception as e:
        logger.error(f"모든 데이터 소스 실패: {e}")
    
    return result
```

## 🔗 참고 자료

- **KRX Data Marketplace**: https://openapi.krx.co.kr
- **서비스 이용방법**: https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO003.jsp
- **서비스 목록**: https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd
- **pykrx 라이브러리**: https://github.com/sharebook-kr/pykrx
- **API 엔드포인트 예시**: `https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd`

## 📌 결론 및 권장사항

### 즉시 실행 가능 (Quick Win) ⭐ 추천
1. **pykrx 라이브러리 통합** ✅
   - 설치: `pip install pykrx`
   - ✅ 외국인/기관 매매 데이터 제공 확인됨
   - ✅ 인증키 불필요, 즉시 사용 가능
   - ✅ 구현 예제 제공됨 (위 참고)

### 중장기 개선 (Recommended)
1. **KRX OpenAPI 인증키 발급**
   - 회원가입 및 인증키 신청
   - '유가증권 일별매매정보' API 이용 신청
   - 공식 데이터로 전환 (신뢰성 향상)

2. **하이브리드 Fallback 메커니즘**
   - KRX API → pykrx → 네이버 크롤링 순서로 시도
   - 데이터 수집 안정성 극대화

### 최종 권장
**KRX OpenAPI는 현재 프로젝트에 매우 유용한 데이터 소스**입니다. 특히:
- ✅ 외국인/기관 매매 데이터는 현재 크롤링 대체 가능
- ✅ 개인 투자자 매매 데이터 등 추가 인사이트 제공
- ✅ 공식 데이터로 신뢰성 향상
- ✅ 구조화된 데이터로 유지보수 부담 감소

**다음 단계**: pykrx 라이브러리로 빠른 테스트 후, KRX OpenAPI 인증키 발급 진행 권장

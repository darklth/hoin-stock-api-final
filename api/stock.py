from flask import Flask, request, Response
import requests, yfinance as yf, re, json
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import io
import pandas as pd

app = Flask(__name__)

# 전역 캐시 (메모리)
STOCK_CODE_CACHE = {}
CACHE_TIMESTAMP = None
CACHE_DURATION = timedelta(hours=24)  # 24시간마다 갱신

# ✅ KRX에서 전체 종목 리스트 가져오기
def fetch_all_stock_codes():
    """
    KRX에서 전체 상장 종목의 종목코드와 종목명을 가져와서 캐싱
    하루에 한 번만 업데이트
    """
    global STOCK_CODE_CACHE, CACHE_TIMESTAMP
    
    # 캐시가 유효한 경우
    if CACHE_TIMESTAMP and datetime.now() - CACHE_TIMESTAMP < CACHE_DURATION:
        if STOCK_CODE_CACHE:
            print("✅ 캐시된 종목 리스트 사용")
            return STOCK_CODE_CACHE
    
    print("🔄 KRX에서 최신 종목 리스트 다운로드 중...")
    
    try:
        # KRX KIND 시스템에서 전체 종목 리스트 다운로드
        url = "https://kind.krx.co.kr/corpgeneral/corpList.do"
        params = {
            'method': 'download',
            'orderMode': '1',  # 회사명 오름차순
            'searchType': '13'  # 전체
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        res = requests.get(url, params=params, headers=headers, timeout=30)
        res.encoding = 'euc-kr'
        
        # HTML 테이블을 pandas로 파싱
        df = pd.read_html(io.StringIO(res.text))[0]
        
        # 종목명 → 종목코드 매핑 생성
        stock_dict = {}
        for _, row in df.iterrows():
            name = str(row['회사명']).strip()
            code = str(row['종목코드']).strip().zfill(6)  # 6자리로 맞춤
            
            if name and code:
                # 회사명 그대로
                stock_dict[name] = code
                # 대소문자 구분 없이
                stock_dict[name.upper()] = code
                stock_dict[name.lower()] = code
        
        STOCK_CODE_CACHE = stock_dict
        CACHE_TIMESTAMP = datetime.now()
        
        print(f"✅ {len(stock_dict)} 개 종목 로드 완료")
        return stock_dict
        
    except Exception as e:
        print(f"❌ KRX 종목 리스트 다운로드 실패: {e}")
        # 실패해도 기존 캐시 사용
        return STOCK_CODE_CACHE if STOCK_CODE_CACHE else {}


# ✅ 종목명으로 종목코드 찾기 (캐시 사용)
def get_ticker_by_name_from_cache(name):
    """
    캐시된 KRX 종목 리스트에서 종목명으로 코드 찾기
    """
    stock_dict = fetch_all_stock_codes()
    
    # 정확히 일치하는 종목명 찾기
    code = stock_dict.get(name) or stock_dict.get(name.upper()) or stock_dict.get(name.lower())
    
    if code:
        print(f"✅ [캐시] {name} → {code}")
        return code
    
    # 부분 일치 검색 (예: "삼성" 입력 시 "삼성전자" 찾기)
    for stock_name, stock_code in stock_dict.items():
        if name in stock_name or stock_name in name:
            print(f"✅ [캐시-부분일치] {name} → {stock_code} ({stock_name})")
            return stock_code
    
    print(f"⚠️ 캐시에서 찾을 수 없음: {name}")
    return None


# ✅ 한국 주식 실시간 시세
def get_korean_stock_price(ticker, include_debug=False):
    """네이버 모바일 API로 실시간 주식 시세 조회 (Fallback 포함)"""
    
    # 방법 1: 네이버 폴링 API (가장 빠름)
    url = f"https://polling.finance.naver.com/api/realtime?query=SERVICE_RECENT_ITEM:{ticker}"
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
        "Referer": f"https://m.stock.naver.com/item/main.nhn?code={ticker}",
        "Accept": "application/json"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=5)
        data = res.json()
        items = data.get("result", {}).get("areas", [{}])[0].get("datas", [])
        
        if items:
            item = items[0]
            current_price = item.get("nv")
            
            if current_price:
                result = {
                    "current_price": f"{int(current_price):,}",
                    "change_amount": f"{int(item.get('cv', 0)):,}",
                    "change_rate": float(item.get("cr", 0)),
                    "volume": f"{int(item.get('aq', 0)):,}"
                }
                
                if include_debug:
                    result["debug_info"] = {
                        "prev_close": f"{int(item.get('pcv', 0)):,}" if item.get('pcv') else "N/A",
                        "open": f"{int(item.get('ov', 0)):,}" if item.get('ov') else "N/A",
                        "high": f"{int(item.get('hv', 0)):,}" if item.get('hv') else "N/A",
                        "low": f"{int(item.get('lv', 0)):,}" if item.get('lv') else "N/A",
                        "source": "polling_api"
                    }
                
                return result
    except Exception as e:
        print(f"⚠️ 폴링 API 실패: {e}")
    
    # 방법 2: 네이버 종목 페이지 HTML 파싱 (Fallback)
    try:
        print(f"🔄 Fallback: HTML 파싱 시도 - {ticker}")
        url = f"https://finance.naver.com/item/main.naver?code={ticker}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 현재가 추출
        price_element = soup.select_one(".rate_info .blind")
        if not price_element:
            price_element = soup.select_one("#_nowVal")
        
        if price_element:
            current_price = price_element.text.strip().replace(',', '')
            
            # 전일대비
            change_element = soup.select_one(".rate_info .blind + .blind")
            change_amount = change_element.text.strip() if change_element else "0"
            
            # 등락률
            rate_element = soup.select_one(".rate_info .blind + .blind + .blind")
            change_rate_str = rate_element.text.strip().replace('%', '') if rate_element else "0"
            
            try:
                change_rate = float(change_rate_str)
            except:
                change_rate = 0.0
            
            result = {
                "current_price": f"{int(current_price):,}",
                "change_amount": change_amount,
                "change_rate": change_rate,
                "volume": "N/A"
            }
            
            if include_debug:
                result["debug_info"] = {
                    "source": "html_parsing"
                }
            
            print(f"✅ HTML 파싱 성공: {ticker} = {result['current_price']}")
            return result
            
    except Exception as e:
        print(f"❌ HTML 파싱 실패: {e}")
    
    return None


# ✅ 메인 API 엔드포인트
@app.route("/api/stock", methods=["GET"])
def api_stock():
    """주식 정보 조회 API"""
    val = (request.args.get("name") or "").strip()
    include_debug = request.args.get("debug", "").lower() == "true"
    
    if not val:
        return Response(
            json.dumps({"success": False, "error": "종목명을 입력하세요"}, ensure_ascii=False),
            content_type="application/json; charset=utf-8",
            status=400
        )

    # 🚀 1단계: KRX 캐시에서 검색
    ticker = get_ticker_by_name_from_cache(val)
    
    # ✅ 한국 주식 처리
    if ticker and ticker.isdigit() and len(ticker) == 6:
        rt = get_korean_stock_price(ticker, include_debug)
        market = "KOSPI/KOSDAQ"
        
        if not rt:
            return Response(
                json.dumps({
                    "success": False,
                    "error": f"'{val}'({ticker}) 실시간 시세 조회 실패. 장 마감 또는 일시적 오류일 수 있습니다."
                }, ensure_ascii=False),
                content_type="application/json; charset=utf-8",
                status=503
            )

    # ✅ 미국 주식 처리
    else:
        try:
            ticker = val.upper()
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d")
            
            if hist.empty:
                raise ValueError("데이터 없음")
            
            price = round(float(hist["Close"].iloc[-1]), 2)
            rt = {"current_price": f"{price:,.2f}"}
            market = "NASDAQ/NYSE"
            
            print(f"✅ 미국 주식: {ticker} = ${price}")
            
        except Exception as e:
            print(f"❌ 조회 실패: {val}")
            return Response(
                json.dumps({
                    "success": False,
                    "error": f"'{val}' 종목을 찾을 수 없습니다. 정확한 종목명 또는 티커를 입력해주세요."
                }, ensure_ascii=False),
                content_type="application/json; charset=utf-8",
                status=404
            )

    # 성공 응답
    res = {
        "success": True,
        "company_name": val,
        "ticker": ticker,
        "market": market,
        "real_time_data": rt
    }

    return Response(
        json.dumps(res, ensure_ascii=False),
        content_type="application/json; charset=utf-8"
    )


# ✅ 캐시 갱신 엔드포인트
@app.route("/api/refresh-cache", methods=["GET"])
def refresh_cache():
    """종목 캐시 강제 갱신"""
    global CACHE_TIMESTAMP
    CACHE_TIMESTAMP = None  # 캐시 무효화
    
    stock_dict = fetch_all_stock_codes()
    
    return Response(
        json.dumps({
            "success": True,
            "message": f"{len(stock_dict)} 개 종목 로드 완료",
            "cached_at": CACHE_TIMESTAMP.isoformat() if CACHE_TIMESTAMP else None
        }, ensure_ascii=False),
        content_type="application/json; charset=utf-8"
    )


# ✅ 디버그용 엔드포인트
@app.route("/api/debug", methods=["GET"])
def api_debug():
    """네이버 API 원본 응답 확인"""
    ticker = request.args.get("ticker", "005930")
    
    if not (ticker.isdigit() and len(ticker) == 6):
        return Response(
            json.dumps({"error": "6자리 종목코드를 입력하세요"}, ensure_ascii=False),
            content_type="application/json; charset=utf-8",
            status=400
        )
    
    url = f"https://polling.finance.naver.com/api/realtime?query=SERVICE_RECENT_ITEM:{ticker}"
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
        "Referer": f"https://m.stock.naver.com/item/main.nhn?code={ticker}"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=5)
        data = res.json()
        
        return Response(
            json.dumps(data, indent=2, ensure_ascii=False),
            content_type="application/json; charset=utf-8"
        )
    except Exception as e:
        return Response(
            json.dumps({"error": str(e)}, ensure_ascii=False),
            content_type="application/json; charset=utf-8",
            status=500
        )


# ✅ 헬스체크
@app.route("/api/health", methods=["GET"])
def health_check():
    """서버 상태 확인"""
    cache_info = {
        "cached_stocks": len(STOCK_CODE_CACHE),
        "cache_age_hours": (datetime.now() - CACHE_TIMESTAMP).total_seconds() / 3600 if CACHE_TIMESTAMP else None,
        "cache_valid": CACHE_TIMESTAMP and (datetime.now() - CACHE_TIMESTAMP < CACHE_DURATION)
    }
    
    return Response(
        json.dumps({
            "status": "healthy",
            "service": "stock-api",
            "cache": cache_info
        }, ensure_ascii=False),
        content_type="application/json; charset=utf-8"
    )


# ✅ Vercel 환경 자동 인식
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

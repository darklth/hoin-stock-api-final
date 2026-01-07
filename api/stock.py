from flask import Flask, request, Response
import requests, json, io
import yfinance as yf
from datetime import datetime, timedelta
import pandas as pd

app = Flask(__name__)

# ✅ 캐시 설정 (24시간 동안 KRX 종목 리스트 유지)
STOCK_CODE_CACHE = {}
CACHE_TIMESTAMP = None
CACHE_DURATION = timedelta(hours=24)

# 1. KRX 전체 종목코드 불러오기 및 캐싱
def fetch_all_stock_codes():
    global STOCK_CODE_CACHE, CACHE_TIMESTAMP
    if CACHE_TIMESTAMP and datetime.now() - CACHE_TIMESTAMP < CACHE_DURATION:
        if STOCK_CODE_CACHE: return STOCK_CODE_CACHE

    print("🔄 KRX 종목 리스트 갱신 중...")
    try:
        url = "https://kind.krx.co.kr/corpgeneral/corpList.do"
        params = {"method": "download", "orderMode": "1", "searchType": "13"}
        res = requests.get(url, params=params, timeout=30)
        res.encoding = "euc-kr"
        df = pd.read_html(io.StringIO(res.text))[0]

        stock_dict = {}
        for _, row in df.iterrows():
            name = str(row["회사명"]).strip()
            code = str(row["종목코드"]).zfill(6)
            stock_dict[name] = code
            stock_dict[name.upper()] = code  # 영문 대명 대응 (예: LS ELECTRIC)
            stock_dict[name.replace(" ", "")] = code # 공백 제거 대응
            
        STOCK_CODE_CACHE = stock_dict
        CACHE_TIMESTAMP = datetime.now()
        return stock_dict
    except Exception as e:
        print(f"❌ KRX 로드 실패: {e}")
        return STOCK_CODE_CACHE

# 2. 실시간 주가 조회 (네이버 Polling API - 가장 안정적)
def get_korean_stock_price(ticker):
    try:
        url = f"https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{ticker}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://finance.naver.com/"
        }
        res = requests.get(url, headers=headers, timeout=5)
        data = res.json()
        
        # 네이버 Polling JSON 구조 파싱
        item = data.get('result', {}).get('areas', [{}])[0].get('datas', [])[0]
        
        if not item: return None

        return {
            "current_price": f"{int(item.get('nv', 0)):,}", # nv: 현재가
            "change_amount": f"{int(item.get('cv', 0)):,}", # cv: 전일대비
            "change_rate": float(item.get('cr', 0)),        # cr: 등락률
            "volume": f"{int(item.get('aq', 0)):,}",         # aq: 거래량
        }
    except Exception as e:
        print(f"❌ 실시간 조회 실패 ({ticker}): {e}")
        return None

import yfinance as yf

# ... (Previous imports remain, ensure yf is added)

# 3. 한국 주식 검색 (기존 로직 분리)
def search_korean_stock(name):
    # 종목 코드를 캐시/KRX 리스트에서 찾기
    stock_dict = fetch_all_stock_codes()
    ticker = stock_dict.get(name) or stock_dict.get(name.upper())

    # 별칭(Alias) 처리
    ALIAS_MAP = {
        "현대차": "현대자동차",
    }
    
    if not ticker and name in ALIAS_MAP:
        real_name = ALIAS_MAP[name]
        ticker = stock_dict.get(real_name)

    # 부분 일치 검색
    if not ticker:
        for k, v in stock_dict.items():
            if name in k:
                ticker = v
                break
    
    if not ticker:
        return None

    # 실시간 시세 조회
    rt = get_korean_stock_price(ticker)
    if not rt:
        return None

    return {
        "market": "KOSPI/KOSDAQ",
        "company_name": name,
        "ticker": ticker,
        "real_time_data": rt
    }

# 4. 미국 주식 검색 (Yahoo Finance)
def search_us_stock(name):
    try:
        ticker = yf.Ticker(name)
        # fast_info가 더 빠르고 안정적일 수 있음
        info = ticker.fast_info 
        
        # 유효성 체크: 시가총액이 없으면 없는 주식으로 간주 (혹은 history 체크)
        if not info.market_cap:
             return None

        current_price = info.last_price
        prev_close = info.previous_close
        
        change_amount = current_price - prev_close
        change_rate = (change_amount / prev_close) * 100

        return {
            "market": "US (Yahoo Finance)",
            "company_name": name.upper(),
            "ticker": name.upper(),
            "real_time_data": {
                "current_price": f"{current_price:,.2f}",
                "change_amount": f"{change_amount:,.2f}",
                "change_rate": round(change_rate, 2),
                "volume": f"{int(info.last_volume or 0):,}" 
            }
        }
    except Exception as e:
        print(f"DEBUG: US Stock search failed for {name}: {e}")
        return None

# 5. 메인 API 엔드포인트
@app.route("/api/stock", methods=["GET"])
def api_stock():
    name = (request.args.get("name") or "").strip()
    
    # 인코딩 보정
    try:
        name = name.encode('latin1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass

    if not name:
        return Response(json.dumps({"success": False, "error": "종목명 필요"}), content_type="application/json")

    # 1순위: 한국 주식 검색
    res_data = search_korean_stock(name)
    
    # 2순위: 한국 주식 없으면 미국 주식 검색
    if not res_data:
        res_data = search_us_stock(name)

    if not res_data:
        return Response(json.dumps({"success": False, "error": f"'{name}' 종목을 찾을 수 없습니다. (한국/미국)"}), content_type="application/json")

    res = {
        "success": True,
        **res_data, # merger market, company_name, ticker, real_time_data
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    return Response(json.dumps(res, ensure_ascii=False), content_type="application/json; charset=utf-8")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

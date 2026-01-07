from flask import Flask, request, Response
import requests, json, re, io
import urllib.parse
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

app = Flask(__name__)

# ====== ✅ 전역 캐시 설정 ======
STOCK_CODE_CACHE = {}
CACHE_TIMESTAMP = None
CACHE_DURATION = timedelta(hours=24)  # 하루마다 갱신

# ====== ✅ 1. KRX에서 종목코드 목록 가져오기 ======
def fetch_all_stock_codes():
    """KRX KIND에서 전체 상장 종목 리스트를 가져와 캐싱"""
    global STOCK_CODE_CACHE, CACHE_TIMESTAMP

    if CACHE_TIMESTAMP and datetime.now() - CACHE_TIMESTAMP < CACHE_DURATION:
        if STOCK_CODE_CACHE:
            print("✅ 캐시 사용 중 (KRX 종목 목록)")
            return STOCK_CODE_CACHE

    print("🔄 KRX에서 종목 리스트 갱신 중...")
    try:
        url = "https://kind.krx.co.kr/corpgeneral/corpList.do"
        params = {"method": "download", "orderMode": "1", "searchType": "13"}
        headers = {"User-Agent": "Mozilla/5.0"}

        res = requests.get(url, params=params, headers=headers, timeout=30)
        res.encoding = "euc-kr"

        df = pd.read_html(io.StringIO(res.text))[0]
        stock_dict = {}

        for _, row in df.iterrows():
            name = str(row["회사명"]).strip()
            code = str(row["종목코드"]).zfill(6)
            if name and code:
                stock_dict[name] = code
                stock_dict[name.upper()] = code
                stock_dict[name.lower()] = code

        STOCK_CODE_CACHE = stock_dict
        CACHE_TIMESTAMP = datetime.now()
        print(f"✅ {len(stock_dict)}개 종목 로드 완료")
        return stock_dict

    except Exception as e:
        print(f"❌ KRX 목록 로드 실패: {e}")
        return STOCK_CODE_CACHE or {}

# ====== ✅ 2. 종목명 → 코드 찾기 ======
def get_ticker_by_name(name):
    """캐시 또는 네이버 검색으로 종목코드 찾기"""
    stock_dict = fetch_all_stock_codes()
    code = stock_dict.get(name) or stock_dict.get(name.upper()) or stock_dict.get(name.lower())

    if code:
        return code

    # HTML 검색 보조 (KRX 캐시에 없는 경우)
    try:
        encoded = urllib.parse.quote(name)
        url = f"https://finance.naver.com/search/searchList.naver?query={encoded}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        link = soup.select_one("a[href*='item/main.naver?code=']")
        if link:
            m = re.search(r"code=(\d{6})", link["href"])
            if m:
                return m.group(1)
    except Exception as e:
        print(f"⚠️ 네이버 검색 실패: {e}")
    return None

# ====== ✅ 3. 실시간 시세 조회 ======
def get_korean_stock_price(ticker):
    """네이버 공식 API (api.stock.naver.com) 기반 실시간 시세 조회"""
    try:
        url = f"https://api.stock.naver.com/stock/{ticker}/basic"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=5)
        
        # 일부 환경에서는 403이 떨어질 수 있음 → 모바일 UA fallback
        if res.status_code != 200:
            headers["User-Agent"] = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)"
            res = requests.get(url, headers=headers, timeout=5)
        
        data = res.json()
        price = data.get("now") or data.get("closePrice")
        if price is None:
            return None

        return {
            "current_price": f"{int(price):,}",
            "change_amount": f"{int(data.get('diff', 0)):,}",
            "change_rate": data.get("rate", 0.0),
            "volume": f"{int(data.get('accVolume', 0)):,}"
        }
    except Exception as e:
        print(f"⚠️ 실시간 조회 실패 ({ticker}): {e}")
        return None


# ====== ✅ 4. 메인 API ======
@app.route("/api/stock", methods=["GET"])
def stock_api():
    """주식 실시간 시세 API"""
    name = (request.args.get("name") or "").strip()

    if not name:
        return Response(json.dumps({"success": False, "error": "종목명을 입력하세요"}, ensure_ascii=False),
                        content_type="application/json; charset=utf-8", status=400)

    ticker = get_ticker_by_name(name)
    if not ticker:
        return Response(json.dumps({"success": False, "error": f"'{name}' 종목을 찾을 수 없습니다. (한국/미국 모두 해당 없음)"}, ensure_ascii=False),
                        content_type="application/json; charset=utf-8", status=404)

    rt = get_korean_stock_price(ticker)
    if not rt:
        return Response(json.dumps({"success": False, "error": f"'{name}'({ticker}) 실시간 시세 조회 실패."}, ensure_ascii=False),
                        content_type="application/json; charset=utf-8", status=503)

    result = {
        "success": True,
        "company_name": name,
        "ticker": ticker,
        "market": "KOSPI/KOSDAQ",
        "real_time_data": rt
    }

    return Response(json.dumps(result, ensure_ascii=False), content_type="application/json; charset=utf-8")

# ====== ✅ 캐시 갱신 ======
@app.route("/api/refresh-cache", methods=["GET"])
def refresh_cache():
    global CACHE_TIMESTAMP
    CACHE_TIMESTAMP = None
    stock_dict = fetch_all_stock_codes()
    return Response(json.dumps({"success": True, "count": len(stock_dict)}, ensure_ascii=False),
                    content_type="application/json; charset=utf-8")

# ====== ✅ 헬스체크 ======
@app.route("/api/health", methods=["GET"])
def health_check():
    info = {
        "cached_count": len(STOCK_CODE_CACHE),
        "cache_age_min": (datetime.now() - CACHE_TIMESTAMP).total_seconds() / 60 if CACHE_TIMESTAMP else None
    }
    return Response(json.dumps({"status": "ok", "cache": info}, ensure_ascii=False),
                    content_type="application/json; charset=utf-8")

# ====== ✅ 로컬 실행 ======
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

from flask import Flask, request, Response
import requests, yfinance as yf, re, json, urllib.parse, io, pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

app = Flask(__name__)

# ✅ 캐시 관련 설정
STOCK_CODE_CACHE = {}
CACHE_TIMESTAMP = None
CACHE_DURATION = timedelta(hours=24)


# ✅ [1] KRX 전체 종목 리스트 캐싱
def fetch_all_stock_codes():
    global STOCK_CODE_CACHE, CACHE_TIMESTAMP

    if CACHE_TIMESTAMP and datetime.now() - CACHE_TIMESTAMP < CACHE_DURATION:
        if STOCK_CODE_CACHE:
            print("✅ 캐시된 종목 리스트 사용")
            return STOCK_CODE_CACHE

    print("🔄 KRX 종목 리스트 새로 로드 중...")

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
            stock_dict[name] = code
            stock_dict[name.upper()] = code
            stock_dict[name.lower()] = code

        STOCK_CODE_CACHE = stock_dict
        CACHE_TIMESTAMP = datetime.now()

        print(f"✅ {len(stock_dict)}개 종목 로드 완료")
        return stock_dict
    except Exception as e:
        print(f"❌ 종목 리스트 로드 실패: {e}")
        return STOCK_CODE_CACHE if STOCK_CODE_CACHE else {}


# ✅ [2] 캐시에서 종목명으로 코드 찾기
def get_ticker_by_name_from_cache(name):
    stock_dict = fetch_all_stock_codes()
    code = stock_dict.get(name) or stock_dict.get(name.upper()) or stock_dict.get(name.lower())

    if code:
        print(f"✅ 캐시 히트: {name} → {code}")
        return code

    for stock_name, stock_code in stock_dict.items():
        if name in stock_name or stock_name in name:
            print(f"✅ 부분 일치: {name} → {stock_code} ({stock_name})")
            return stock_code

    print(f"⚠️ 캐시 미스: {name}")
    return None


# ✅ [3] 한국 주식 실시간 시세 조회 (3중 fallback)
def get_korean_stock_price(ticker, include_debug=False):
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
        "Referer": f"https://m.stock.naver.com/item/main.nhn?code={ticker}",
        "Accept": "application/json"
    }

    # 1️⃣ polling API (SERVICE_RECENT_ITEM → SERVICE_ITEM 순서로 시도)
    for query_type in ["SERVICE_RECENT_ITEM", "SERVICE_ITEM"]:
        try:
            url = f"https://polling.finance.naver.com/api/realtime?query={query_type}:{ticker}"
            res = requests.get(url, headers=headers, timeout=5)
            data = res.json()

            items = data.get("result", {}).get("areas", [{}])[0].get("datas", [])
            if not items:
                continue

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
                        "prev_close": f"{int(item.get('pcv', 0)):,}" if item.get("pcv") else "N/A",
                        "open": f"{int(item.get('ov', 0)):,}" if item.get("ov") else "N/A",
                        "high": f"{int(item.get('hv', 0)):,}" if item.get("hv") else "N/A",
                        "low": f"{int(item.get('lv', 0)):,}" if item.get("lv") else "N/A",
                        "source": query_type
                    }
                print(f"✅ {query_type} 성공: {ticker} = {result['current_price']}")
                return result
        except Exception as e:
            print(f"⚠️ {query_type} 실패: {e}")

    # 2️⃣ HTML 파싱 fallback
    try:
        print(f"🔄 HTML 파싱 시도: {ticker}")
        url = f"https://finance.naver.com/item/main.naver?code={ticker}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")

        price_el = soup.select_one(".rate_info .blind") or soup.select_one("#_nowVal")
        if price_el:
            current_price = price_el.text.strip().replace(",", "")
            result = {
                "current_price": f"{int(current_price):,}",
                "change_amount": "0",
                "change_rate": 0.0,
                "volume": "N/A"
            }
            if include_debug:
                result["debug_info"] = {"source": "html_parsing"}
            print(f"✅ HTML 파싱 성공: {ticker} = {result['current_price']}")
            return result
    except Exception as e:
        print(f"❌ HTML 파싱 실패: {e}")

    return None


# ✅ [4] 메인 API 엔드포인트
@app.route("/api/stock", methods=["GET"])
def api_stock():
    val = (request.args.get("name") or "").strip()
    include_debug = request.args.get("debug", "").lower() == "true"

    if not val:
        return Response(json.dumps({"success": False, "error": "종목명을 입력하세요"}, ensure_ascii=False),
                        content_type="application/json; charset=utf-8", status=400)

    # 한국 종목 우선 검색
    ticker = get_ticker_by_name_from_cache(val)
    if ticker and ticker.isdigit() and len(ticker) == 6:
        rt = get_korean_stock_price(ticker, include_debug)
        market = "KOSPI/KOSDAQ"
        if not rt:
            return Response(json.dumps({
                "success": False,
                "error": f"'{val}'({ticker}) 실시간 시세 조회 실패. 장 마감 또는 네이버 API 차단일 수 있습니다."
            }, ensure_ascii=False),
                content_type="application/json; charset=utf-8", status=503)
    else:
        # 해외 종목

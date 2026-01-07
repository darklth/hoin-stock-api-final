from flask import Flask, request, Response
import requests, json, urllib.parse
from datetime import datetime, timedelta
import io
import pandas as pd

app = Flask(__name__)

# 캐시 설정
STOCK_CODE_CACHE = {}
CACHE_TIMESTAMP = None
CACHE_DURATION = timedelta(hours=24)


# ✅ 1. KRX 전체 종목코드 불러오기
def fetch_all_stock_codes():
    global STOCK_CODE_CACHE, CACHE_TIMESTAMP

    if CACHE_TIMESTAMP and datetime.now() - CACHE_TIMESTAMP < CACHE_DURATION:
        if STOCK_CODE_CACHE:
            return STOCK_CODE_CACHE

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
            stock_dict[name.upper()] = code
            stock_dict[name.lower()] = code

        STOCK_CODE_CACHE = stock_dict
        CACHE_TIMESTAMP = datetime.now()
        print(f"✅ {len(stock_dict)} 종목 로드 완료")
        return stock_dict

    except Exception as e:
        print(f"❌ KRX 로드 실패: {e}")
        return STOCK_CODE_CACHE


# ✅ 2. 종목명으로 코드 찾기
def get_ticker_by_name(name):
    stock_dict = fetch_all_stock_codes()
    if name in stock_dict:
        return stock_dict[name]

    for k, v in stock_dict.items():
        if name in k or k in name:
            return v
    return None


# ✅ 3. 실시간 주가 조회 (공식 api.stock.naver.com 사용)
def get_korean_stock_price(ticker):
    try:
        url = f"https://api.stock.naver.com/stock/{ticker}/basic"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": f"https://api.stock.naver.com/stock/{ticker}/basic",
            "Accept": "application/json",
        }
        res = requests.get(url, headers=headers, timeout=5)

        if res.status_code != 200:
            print(f"⚠️ API 응답 오류 {res.status_code}")
            return None

        data = res.json()
        price = data.get("now") or data.get("closePrice")

        if price is None:
            print(f"⚠️ 가격 데이터 없음: {data}")
            return None

        return {
            "current_price": f"{int(price):,}",
            "change_amount": f"{int(data.get('diff', 0)):,}",
            "change_rate": data.get("rate", 0.0),
            "volume": f"{int(data.get('accVolume', 0)):,}",
        }

    except Exception as e:
        print(f"❌ 실시간 조회 실패 ({ticker}): {e}")
        return None


# ✅ 4. 메인 API
@app.route("/api/stock", methods=["GET"])
def api_stock():
    name = (request.args.get("name") or "").strip()
    if not name:
        return Response(
            json.dumps({"success": False, "error": "종목명을 입력하세요"}, ensure_ascii=False),
            content_type="application/json; charset=utf-8",
        )

    ticker = get_ticker_by_name(name)
    if not ticker:
        return Response(
            json.dumps({"success": False, "error": f"'{name}' 종목을 찾을 수 없습니다."}, ensure_ascii=False),
            content_type="application/json; charset=utf-8",
        )

    rt = get_korean_stock_price(ticker)
    if not rt:
        return Response(
            json.dumps({"success": False, "error": f"'{name}'({ticker}) 실시간 시세 조회 실패."}, ensure_ascii=False),
            content_type="application/json; charset=utf-8",
        )

    res = {
        "success": True,
        "company_name": name,
        "ticker": ticker,
        "market": "KOSPI/KOSDAQ",
        "real_time_data": rt,
    }
    return Response(json.dumps(res, ensure_ascii=False), content_type="application/json; charset=utf-8")


# ✅ 5. 헬스체크
@app.route("/api/health", methods=["GET"])
def health():
    return Response(
        json.dumps(
            {"status": "ok", "cached": len(STOCK_CODE_CACHE), "timestamp": str(CACHE_TIMESTAMP)},
            ensure_ascii=False,
        ),
        content_type="application/json; charset=utf-8",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

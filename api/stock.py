from flask import Flask, request, Response
import requests
import yfinance as yf
import json

app = Flask(__name__)

# ✅ 한국 주식 실시간 시세 (네이버 모바일 API 사용)
def get_korean_stock_price(ticker):
    url = f"https://m.stock.naver.com/api/item/getPriceInfo.nhn?code={ticker}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=3)
        data = res.json()
        if "now" in data:
            return str(data["now"])
        else:
            return "조회 실패"
    except Exception as e:
        print("❌ Error(get_korean_stock_price):", e)
        return "조회 실패"


# ✅ 미국 주식 시세 (Yahoo Finance)
def get_us_stock_price(symbol):
    try:
        stock = yf.Ticker(symbol)
        data = stock.history(period="1d")
        if not data.empty:
            price = float(data["Close"].iloc[-1])
            return f"{price:.2f}"
        else:
            return "조회 실패"
    except Exception as e:
        print("❌ Error(get_us_stock_price):", e)
        return "조회 실패"


# ✅ 네이버에서 한글 종목명 → 종목코드 자동 변환
def get_stock_code_by_name(name):
    url = f"https://finance.naver.com/search/searchList.naver?query={name}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        html = requests.get(url, headers=headers, timeout=3).text
        start = html.find("code=")
        if start == -1:
            return None
        code = html[start + 5:start + 11]
        return code if code.isdigit() else None
    except Exception as e:
        print("❌ Error(get_stock_code_by_name):", e)
        return None


# ✅ 주요 종목 캐시 (속도 향상용)
PREDEFINED = {
    "삼성전자": "005930",
    "LG전자": "066570",
    "이월드": "084680",
    "카카오": "035720",
    "하이브": "352820",
    "엔씨소프트": "036570",
    "테슬라": "TSLA",
    "애플": "AAPL",
    "엔비디아": "NVDA"
}


@app.route("/api/stock", methods=["GET"])
def stock_api():
    val = request.args.get("name") or request.args.get("ticker")
    if not val:
        return Response(
            json.dumps({"error": "⚠️ name 또는 ticker 파라미터가 필요합니다."}, ensure_ascii=False),
            content_type="application/json; charset=utf-8"
        )

    val = val.strip()

    # ✅ 한글 입력 → 한국 주식
    if not val.isalpha():
        ticker = PREDEFINED.get(val) or get_stock_code_by_name(val)
        if not ticker:
            return Response(
                json.dumps({"error": f"'{val}' 종목을 찾을 수 없습니다."}, ensure_ascii=False),
                content_type="application/json; charset=utf-8"
            )
        price = get_korean_stock_price(ticker)
        res = {"name": val, "ticker": ticker, "price": price, "market": "KOSPI/KOSDAQ"}

    # ✅ 영문 입력 → 미국 주식
    else:
        ticker = val.upper()
        price = get_us_stock_price(ticker)
        res = {"name": ticker, "price": price, "market": "NASDAQ/NYSE"}

    return Response(
        json.dumps(res, ensure_ascii=False),
        content_type="application/json; charset=utf-8"
    )


# ✅ 로컬 실행용 (Vercel 환경에서는 필요 없음)
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

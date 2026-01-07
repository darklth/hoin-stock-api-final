from flask import Flask, request, Response
import requests, yfinance as yf, json

app = Flask(__name__)

# ✅ 네이버 최신 종목 검색 API (2026년)
def get_ticker_by_name(name: str):
    try:
        url = f"https://m.stock.naver.com/api/search/stock/{name}"
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
            "Accept": "application/json"
        }
        res = requests.get(url, headers=headers, timeout=5)
        data = res.json()

        stocks = data.get("stocks", [])
        if not stocks:
            print(f"⚠️ 종목 검색 결과 없음: {name}")
            return None

        ticker = stocks[0].get("itemCode")
        print(f"✅ 종목코드 매핑 성공: {name} → {ticker}")
        return ticker
    except Exception as e:
        print(f"❌ 종목 검색 실패: {e}")
        return None


# ✅ 네이버 모바일 실시간 주가 조회
def get_korean_stock_price(ticker: str):
    try:
        url = f"https://m.stock.naver.com/api/stock/{ticker}/basic"
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
            "Accept": "application/json"
        }
        res = requests.get(url, headers=headers, timeout=5)
        data = res.json()

        if not data or "now" not in data:
            print(f"⚠️ 시세 데이터 없음: {ticker}")
            return None

        return {
            "current_price": f"{int(data.get('now', 0)):,}",
            "change_amount": f"{int(data.get('cv', 0)):,}",
            "change_rate": float(data.get('cr', 0)),
            "volume": f"{int(data.get('aq', 0)):,}" if data.get('aq') else "0"
        }
    except Exception as e:
        print(f"❌ 실시간 시세 조회 실패: {e}")
        return None


# ✅ 미국 주식 (Yahoo Finance)
def get_us_stock_price(symbol: str):
    try:
        stock = yf.Ticker(symbol)
        hist = stock.history(period="1d")
        if hist.empty:
            return None
        price = round(float(hist["Close"].iloc[-1]), 2)
        return {
            "current_price": f"{price:,.2f}",
            "change_amount": "N/A",
            "change_rate": 0.0,
            "volume": "N/A"
        }
    except Exception as e:
        print(f"❌ 미국 주식 조회 실패: {e}")
        return None


# ✅ 메인 API
@app.route("/api/stock", methods=["GET"])
def api_stock():
    name = (request.args.get("name") or "").strip()
    if not name:
        return Response(
            json.dumps({"success": False, "error": "종목명을 입력하세요"}, ensure_ascii=False),
            content_type="application/json; charset=utf-8"
        )

    # 🇰🇷 한국 주식 시도
    ticker = get_ticker_by_name(name)
    if ticker and ticker.isdigit() and len(ticker) == 6:
        price_data = get_korean_stock_price(ticker)
        if price_data:
            return Response(
                json.dumps({
                    "success": True,
                    "company_name": name,
                    "ticker": ticker,
                    "market": "KOSPI/KOSDAQ",
                    "real_time_data": price_data
                }, ensure_ascii=False),
                content_type="application/json; charset=utf-8"
            )

    # 🇺🇸 미국 주식 시도
    us_price = get_us_stock_price(name.upper())
    if us_price:
        return Response(
            json.dumps({
                "success": True,
                "company_name": name.upper(),
                "ticker": name.upper(),
                "market": "NASDAQ/NYSE",
                "real_time_data": us_price
            }, ensure_ascii=False),
            content_type="application/json; charset=utf-8"
        )

    # ❌ 실패 시
    return Response(
        json.dumps({
            "success": False,
            "error": f"'{name}' 종목을 찾을 수 없습니다. (한국/미국 모두 해당 없음)"
        }, ensure_ascii=False),
        content_type="application/json; charset=utf-8"
    )


# ✅ 헬스체크
@app.route("/api/health", methods=["GET"])
def health_check():
    return Response(
        json.dumps({"status": "healthy", "service": "stock-api"}, ensure_ascii=False),
        content_type="application/json; charset=utf-8"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

from flask import Flask, request, Response
import requests, yfinance as yf, json, re
from bs4 import BeautifulSoup

app = Flask(__name__)

# ✅ 한국 주식 실시간 시세 (신형 + 백업)
def get_korean_stock_price(ticker):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": f"https://m.stock.naver.com/stock/{ticker}"
    }

    # ① 신형 API 우선 시도
    try:
        url = f"https://m.stock.naver.com/api/stock/{ticker}/basic"
        res = requests.get(url, headers=headers, timeout=5)
        data = res.json()
        if "now" in data and data["now"]:
            return f"{int(data['now']):,}"
        if "closePrice" in data and data["closePrice"]:
            return f"{int(data['closePrice']):,}"
    except Exception as e:
        print(f"❌ JSON API 실패: {e}")

    # ② JSON 실패 시 HTML 파싱 (백업 루틴)
    try:
        url_html = f"https://finance.naver.com/item/main.naver?code={ticker}"
        html = requests.get(url_html, headers=headers, timeout=5).text
        soup = BeautifulSoup(html, "html.parser")
        price_tag = soup.select_one("p.no_today span.blind")
        if price_tag:
            return price_tag.text.strip()
        else:
            return "조회 실패"
    except Exception as e:
        print(f"❌ HTML 파싱 실패: {e}")
        return "조회 실패"


# ✅ 미국 주식 시세 (Yahoo Finance)
def get_us_stock_price(symbol):
    try:
        stock = yf.Ticker(symbol)
        data = stock.history(period="1d")
        if not data.empty:
            return f"{float(data['Close'].iloc[-1]):.2f}"
        return "조회 실패"
    except Exception as e:
        print(f"❌ Error(get_us_stock_price): {e}")
        return "조회 실패"


# ✅ 네이버 종목명 → 코드 변환
def get_stock_code_by_name(name):
    try:
        html = requests.get(
            f"https://finance.naver.com/search/searchList.naver?query={name}",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=5
        ).text
        match = re.search(r'code=(\d{6})', html)
        return match.group(1) if match else None
    except Exception:
        return None


PREDEFINED = {
    "삼성전자": "005930", "LG전자": "066570", "이월드": "084680",
    "카카오": "035720", "하이브": "352820", "엔씨소프트": "036570",
    "테슬라": "TSLA", "애플": "AAPL", "엔비디아": "NVDA"
}


@app.route("/api/stock", methods=["GET"])
def stock_api():
    val = request.args.get("name") or request.args.get("ticker")
    if not val:
        return Response(
            json.dumps({"error": "name 또는 ticker가 필요합니다."}, ensure_ascii=False),
            content_type="application/json; charset=utf-8"
        )

    val = val.strip()
    is_korean = bool(re.search('[가-힣]', val))

    if is_korean or (val.isdigit() and len(val) == 6):
        ticker = PREDEFINED.get(val) or get_stock_code_by_name(val)
        if not ticker:
            return Response(
                json.dumps({"error": f"'{val}' 종목을 찾을 수 없습니다."}, ensure_ascii=False),
                content_type="application/json; charset=utf-8"
            )
        price = get_korean_stock_price(ticker)
        res = {"name": val, "ticker": ticker, "price": price, "market": "KOSPI/KOSDAQ"}
    else:
        ticker = val.upper()
        price = get_us_stock_price(ticker)
        res = {"name": ticker, "price": price, "market": "NASDAQ/NYSE"}

    return Response(
        json.dumps(res, ensure_ascii=False),
        content_type="application/json; charset=utf-8"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

from flask import Flask, request, Response
import requests, yfinance as yf, re, json
from datetime import datetime
from bs4 import BeautifulSoup

app = Flask(__name__)

# 🇰🇷 네이버 금융 실시간 시세
def get_korean_stock_price(ticker):
    try:
        url = f"https://m.stock.naver.com/api/stock/{ticker}/basic"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=5)
        data = res.json()
        return {
            "current_price": int(data["now"]),
            "change_amount": int(data["diff"]),
            "change_rate": float(data["rate"]),
            "volume": int(data["accumulatedTradingVolume"]),
            "market_cap": f"{round(int(data['marketValue'])/1e12,2)}조원"
        }
    except Exception as e:
        print("Error(get_korean_stock_price):", e)
        return None

# 🇺🇸 야후 파이낸스 시세
def get_us_stock_price(symbol):
    try:
        stock = yf.Ticker(symbol)
        hist = stock.history(period="1d")
        info = stock.info
        if not hist.empty:
            close = float(hist["Close"].iloc[-1])
            open_ = float(hist["Open"].iloc[-1])
            change = close - open_
            rate = (change / open_) * 100
            return {
                "current_price": round(close, 2),
                "change_amount": round(change, 2),
                "change_rate": round(rate, 2),
                "volume": int(hist["Volume"].iloc[-1]),
                "market_cap": f"{info.get('marketCap', 0)/1e9:.2f}B USD"
            }
    except Exception as e:
        print("Error(get_us_stock_price):", e)
    return None

# 💰 재무정보 (네이버 금융)
def get_financial_data(ticker):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={ticker}"
        headers = {"User-Agent": "Mozilla/5.0"}
        html = requests.get(url, headers=headers, timeout=5).text
        soup = BeautifulSoup(html, "html.parser")
        per = soup.select_one("em#_per").text
        roe = soup.select_one("em#_roe").text
        return {"per": float(per), "roe": float(roe)}
    except:
        return {"per": None, "roe": None}

# 📰 최신 뉴스 (네이버 뉴스)
def get_stock_news(keyword):
    try:
        url = f"https://newssearch.naver.com/search.naver?where=news&query={keyword}"
        html = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).text
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select("a.news_tit")[:3]
        return [{"title": i["title"], "link": i["href"]} for i in items]
    except:
        return []

# 📦 메인 API
@app.route("/api/stock", methods=["GET"])
def api_stock():
    val = request.args.get("name") or request.args.get("ticker")
    if not val:
        return Response(json.dumps({"error": "name 또는 ticker 필요"}, ensure_ascii=False),
                        content_type="application/json; charset=utf-8")
    
    val = val.strip()
    is_korean = bool(re.search("[가-힣]", val))
    data = None

    if is_korean:
        mapping = {"삼성전자": "005930", "LG전자": "066570", "이월드": "084680"}
        ticker = mapping.get(val)
        market = "KOSPI"
        rt = get_korean_stock_price(ticker)
        fin = get_financial_data(ticker)
    else:
        ticker = val.upper()
        market = "NASDAQ/NYSE"
        rt = get_us_stock_price(ticker)
        fin = {}

    news = get_stock_news(val)
    res = {
        "success": True,
        "company_name": val,
        "ticker": ticker,
        "market": market,
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "real_time_data": rt or {"current_price": "조회 실패"},
        "financial_data": fin,
        "news_data": news,
        "summary": {
            "trend": "상승" if rt and rt["change_rate"] > 0 else "하락",
            "comment": f"{val} {'상승 중' if rt and rt['change_rate'] > 0 else '약세 흐름'}"
        }
    }

    return Response(json.dumps(res, ensure_ascii=False),
                    content_type="application/json; charset=utf-8")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

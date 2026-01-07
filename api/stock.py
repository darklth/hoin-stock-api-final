from flask import Flask, request, Response
import requests
from bs4 import BeautifulSoup
import yfinance as yf
import json

app = Flask(__name__)

def get_korean_stock_price(ticker):
    url = f"https://finance.naver.com/item/main.naver?code={ticker}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        html = requests.get(url, headers=headers).text
        soup = BeautifulSoup(html, "html.parser")
        return soup.select_one(".no_today .blind").text
    except:
        return "조회 실패"

def get_us_stock_price(symbol):
    try:
        stock = yf.Ticker(symbol)
        data = stock.history(period="1d")
        return f"{float(data['Close'].iloc[-1]):.2f}" if not data.empty else "조회 실패"
    except:
        return "조회 실패"

@app.route("/api/stock", methods=["GET"])
def stock_api():
    val = request.args.get("name") or request.args.get("ticker")
    if not val:
        return Response('{"error": "파라미터 필요"}', content_type="application/json; charset=utf-8")

    val_upper = val.upper().strip()
    
    # 한국 주식 티커/이름 매핑
    stocks = {
        "005930": ("005930", "삼성전자"), "삼성전자": ("005930", "삼성전자"),
        "066570": ("066570", "LG전자"), "LG전자": ("066570", "LG전자"),
        "TSLA": ("TSLA", "테슬라"), "테슬라": ("TSLA", "테슬라"),
        "AAPL": ("AAPL", "애플"), "애플": ("AAPL", "애플")
    }

    if val_upper in stocks:
        sym, name = stocks[val_upper]
        price = get_korean_stock_price(sym) if sym.isdigit() else get_us_stock_price(sym)
    else:
        price, name = get_us_stock_price(val_upper), val_upper

    # 한글 인코딩 강제 고정 응답
    res_json = json.dumps({"name": name, "price": price}, ensure_ascii=False)
    return Response(res_json, content_type="application/json; charset=utf-8")

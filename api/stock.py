from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import yfinance as yf

app = Flask(__name__)

def get_korean_stock_price(ticker):
    url = f"https://finance.naver.com/item/main.naver?code={ticker}"
    headers = {"User-Agent": "Mozilla/5.0"}
    html = requests.get(url, headers=headers).text
    soup = BeautifulSoup(html, "html.parser")
    try:
        price = soup.select_one(".no_today .blind").text
        return price
    except:
        return "조회 실패"

def get_us_stock_price(symbol):
    stock = yf.Ticker(symbol)
    data = stock.history(period="1d")
    return float(data['Close'].iloc[-1]) if not data.empty else "조회 실패"

@app.route("/api/stock", methods=["GET"])
def stock_api():
    name = request.args.get("name")
    if not name:
        return jsonify({"error": "name 파라미터가 필요합니다."})

    if name == "삼성전자":
        price = get_korean_stock_price("005930")
    elif name == "LG전자":
        price = get_korean_stock_price("066570")
    elif name.upper() == "TSLA":
        price = get_us_stock_price("TSLA")
    else:
        return jsonify({"error": "지원되지 않는 종목입니다."})

    return jsonify({"name": name, "price": price})

if __name__ == "__main__":
    app.run()

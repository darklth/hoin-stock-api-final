from flask import Flask, request, Response
import requests, yfinance as yf, re, json
from datetime import datetime
from bs4 import BeautifulSoup

app = Flask(__name__)

# ✅ 네이버 금융 검색 (영문명이라도 국장이면 무조건 먼저 찾음)
def get_ticker_by_name(name):
    try:
        url = f"https://finance.naver.com/search/searchList.naver?query={name}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        # 1. 즉시 이동되는 경우
        if "item/main.naver?code=" in res.url:
            return re.search(r'code=(\d{6})', res.url).group(1)
        # 2. 검색 목록에서 첫 번째 결과 확인
        soup = BeautifulSoup(res.text, "html.parser")
        link = soup.select_one("table.type_1 tr:nth-child(2) td.tit a")
        if link:
            return re.search(r'code=(\d{6})', link['href']).group(1)
    except:
        return None
    return None

def get_korean_stock_price(ticker):
    try:
        url = f"https://m.stock.naver.com/api/stock/{ticker}/basic"
        data = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5).json()
        now = data.get("now") or data.get("closePrice")
        if now:
            return {
                "current_price": f"{int(now):,}",
                "change_rate": float(data.get('rate', 0)),
                "market_cap": f"{round(int(data.get('marketValue', 0))/1e12, 2)}조원"
            }
    except:
        return None

@app.route("/api/stock", methods=["GET"])
def api_stock():
    val = (request.args.get("name") or "").strip()
    if not val:
        return Response(json.dumps({"error": "종목명 필요"}), content_type="application/json")

    # 1단계: 국장 우선 검색 (사전 매핑 + 실시간 검색)
    mapping = {"삼성전자": "005930", "이월드": "084680", "LS ELECTRIC": "010120"}
    ticker = mapping.get(val) or mapping.get(val.upper()) or get_ticker_by_name(val)
    
    if ticker and ticker.isdigit():
        rt = get_korean_stock_price(ticker)
        market = "KOSPI/KOSDAQ"
    else:
        # 2단계: 국장에 없으면 미장 시도
        ticker = val.upper()
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d")
            price = round(float(hist["Close"].iloc[-1]), 2) if not hist.empty else "조회 실패"
            rt = {"current_price": price}
        except:
            rt = None
        market = "NASDAQ/NYSE"

    res = {
        "success": True,
        "company_name": val,
        "ticker": ticker,
        "market": market,
        "real_time_data": rt or {"current_price": "조회 실패"}
    }
    return Response(json.dumps(res, ensure_ascii=False), content_type="application/json; charset=utf-8")

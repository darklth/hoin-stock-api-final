from flask import Flask, request, Response
import requests, yfinance as yf, re, json
from datetime import datetime
from bs4 import BeautifulSoup

app = Flask(__name__)

# ✅ 한국 주식 실시간 시세 (가장 안정적인 폴링 API 사용)
def get_korean_stock_price(ticker):
    # 💡 경로 변경: 가장 차단이 적은 실시간 폴링 API
    url = f"https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{ticker}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://finance.naver.com/",
        "Accept": "*/*"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=5)
        data = res.json()
        
        # 네이버 폴링 API 데이터 구조 분석 후 추출
        # result -> areas -> 0 -> datas -> 0 -> nv (현재가)
        items = data.get('result', {}).get('areas', [{}])[0].get('datas', [])
        if items:
            current_price = items[0].get('nv') # nv가 현재가(now value)
            if current_price:
                return {
                    "current_price": f"{int(current_price):,}",
                    "change_amount": f"{int(items[0].get('cv', 0)):,}", # cv: 전일대비
                    "change_rate": float(items[0].get('cr', 0)),        # cr: 등락률
                    "volume": f"{int(items[0].get('aq', 0)):,}"         # aq: 거래량
                }
    except Exception as e:
        print(f"❌ 네이버 API 호출 실패: {e}")
    
    return None

# ✅ 네이버 종목명 -> 코드 변환
def get_ticker_by_name(name):
    try:
        url = f"https://finance.naver.com/search/searchList.naver?query={name}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        if "item/main.naver?code=" in res.url:
            return re.search(r'code=(\d{6})', res.url).group(1)
        soup = BeautifulSoup(res.text, "html.parser")
        link = soup.select_one("table.type_1 tr:nth-child(2) td.tit a")
        if link:
            return re.search(r'code=(\d{6})', link['href']).group(1)
    except:
        return None

@app.route("/api/stock", methods=["GET"])
def api_stock():
    val = (request.args.get("name") or "").strip()
    if not val:
        return Response(json.dumps({"error": "종목명 필요"}), content_type="application/json")

    # 1. 국장 우선 검색 (사전 매핑 포함)
    mapping = {"삼성전자": "005930", "이월드": "084680", "LS ELECTRIC": "010120"}
    ticker = mapping.get(val) or mapping.get(val.upper()) or get_ticker_by_name(val)
    
    if ticker and ticker.isdigit() and len(ticker) == 6:
        rt = get_korean_stock_price(ticker)
        market = "KOSPI/KOSDAQ"
    else:
        # 2. 미장 시도
        try:
            ticker = val.upper()
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

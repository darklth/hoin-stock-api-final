from flask import Flask, request, Response
import requests, yfinance as yf, json, re
from bs4 import BeautifulSoup

app = Flask(__name__)

# ✅ 한국 주식 실시간 시세 (신형 API + 백업 파싱)
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


# ✅ 네이버 종목명 → 코드 변환 (국내 주식 우선 검색)
def get_stock_code_by_name(name):
    try:
        # 네이버 금융 검색 URL
        search_url = f"https://finance.naver.com/search/searchList.naver?query={name}"
        res = requests.get(search_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        
        # 1. 정확히 일치하여 해당 종목 페이지로 바로 리다이렉트 된 경우
        if "item/main.naver?code=" in res.url:
            match = re.search(r'code=(\d{6})', res.url)
            return match.group(1) if match else None
        
        # 2. 검색 결과 리스트가 나온 경우
        html = res.text
        soup = BeautifulSoup(html, "html.parser")
        # 검색 결과 테이블의 첫 번째 종목 코드 추출
        first_row = soup.select_one("table.type_1 tr:nth-child(2) td.tit a")
        if first_row:
            match = re.search(r'code=(\d{6})', first_row['href'])
            return match.group(1) if match else None
            
        return None
    except Exception:
        return None


# ✅ 사전 정의 (정확한 매칭 및 미국 주식 강제 지정)
PREDEFINED = {
    "삼성전자": "005930", "LG전자": "066570", "이월드": "084680",
    "LS ELECTRIC": "010120", "LSELECTRIC": "010120", # 영문 사명 국장 우선 매칭
    "테슬라": "TSLA", "애플": "AAPL", "엔비디아": "NVDA",
    "로켓랩": "RKLB", "로캣랩": "RKLB", "아이온큐": "IONQ"
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
    
    # 1. PREDEFINED에서 먼저 확인
    ticker = PREDEFINED.get(val) or PREDEFINED.get(val.upper())
    
    # 2. PREDEFINED에 없으면 한국 시장(네이버)에서 먼저 검색 시도
    if not ticker:
        ticker = get_stock_code_by_name(val)
        
    # ✅ 한국 주식으로 판별된 경우 (티커가 6자리 숫자인 경우)
    if ticker and ticker.isdigit() and len(ticker) == 6:
        price = get_korean_stock_price(ticker)
        res = {"name": val, "ticker": ticker, "price": price, "market": "KOSPI/KOSDAQ"}
    
    # ✅ 한국 시장에서 못 찾았거나, PREDEFINED에서 미국 티커로 지정된 경우
    else:
        #

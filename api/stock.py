from flask import Flask, request, Response
import requests
import yfinance as yf
import json
import re

app = Flask(__name__)

# ✅ 한국 주식 실시간 시세 (네이버 모바일 API 보강 버전)
def get_korean_stock_price(ticker):
    url = f"https://finance.naver.com/item/main.naver?code={ticker}"
    
    # 💡 브라우저처럼 보이기 위한 필수 헤더 보강
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://m.stock.naver.com/item/main.nhn?code={ticker}",
        "Accept": "application/json, text/plain, */*"
    }
    
    try:
        # timeout을 5초로 늘리고 헤더를 적용합니다.
        res = requests.get(url, headers=headers, timeout=5)
        
        if res.status_code != 200:
            return f"에러 {res.status_code}"
            
        data = res.json()
        # API 응답 구조에 따라 'now' 값이 있는지 확인
        if "now" in data:
            return f"{int(data['now']):,}" # 숫자에 콤마(,) 추가
        elif "result" in data and "now" in data["result"]:
            return f"{int(data['result']['now']):,}"
        else:
            return "데이터 없음"
            
    except Exception as e:
        print(f"❌ Error(get_korean_stock_price): {e}")
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
        print(f"❌ Error(get_us_stock_price): {e}")
        return "조회 실패"


# ✅ 네이버 종목명 → 종목코드 검색
def get_stock_code_by_name(name):
    url = f"https://finance.naver.com/search/searchList.naver?query={name}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        html = requests.get(url, headers=headers, timeout=5).text
        # 검색 결과에서 code= 뒤의 6자리 숫자를 추출
        match = re.search(r'code=(\d{6})', html)
        return match.group(1) if match else None
    except:
        return None


# ✅ 주요 종목 캐시
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

    # ✅ 한국 주식 판별
    if is_korean or (val.isdigit() and len(val) == 6):
        ticker = PREDEFINED.get(val) or get_stock_code_by_name(val)
        if not ticker:
            return Response(
                json.dumps({"error": f"'{val}' 종목을 찾을 수 없습니다."}, ensure_ascii=False),
                content_type="application/json; charset=utf-8"
            )
        price = get_korean_stock_price(ticker)
        res = {"name": val, "ticker": ticker, "price": price, "market": "KOSPI/KOSDAQ"}

    # ✅ 미국 주식 판별
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

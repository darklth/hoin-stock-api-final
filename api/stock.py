from flask import Flask, request, Response
import requests
from bs4 import BeautifulSoup
import yfinance as yf
import json

app = Flask(__name__)

# 🔹 한국 주식 이름으로 종목코드 자동 검색
def get_stock_code_by_name(name):
    """네이버 금융에서 한글 종목명을 종목코드로 변환"""
    search_url = f"https://finance.naver.com/search/searchList.naver?query={name}"
    headers = {"User-Agent": "Mozilla/5.0"}
    html = requests.get(search_url, headers=headers).text
    soup = BeautifulSoup(html, "html.parser")

    try:
        link = soup.select_one(".search_result dd a")["href"]
        code = link.split("code=")[-1]
        return code
    except Exception:
        return None


# 🔹 한국 주식 실시간 시세
def get_korean_stock_price(ticker):
    """네이버 금융에서 실시간 현재가 가져오기"""
    url = f"https://finance.naver.com/item/main.naver?code={ticker}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        html = requests.get(url, headers=headers).text
        soup = BeautifulSoup(html, "html.parser")

        # 기본 구조
        price_tag = soup.select_one(".no_today .blind")

        # 구조가 다를 경우 예외 처리
        if not price_tag:
            price_tag = (
                soup.select_one("strong.current > span.blind")
                or soup.find("span", {"class": "blind"})
            )

        return price_tag.text.strip() if price_tag else "조회 실패"
    except Exception:
        return "조회 실패"


# 🔹 미국 주식 실시간 시세
def get_us_stock_price(symbol):
    """Yahoo Finance에서 미국 주식 종가"""
    try:
        stock = yf.Ticker(symbol)
        data = stock.history(period="1d")
        return f"{float(data['Close'].iloc[-1]):.2f}" if not data.empty else "조회 실패"
    except Exception:
        return "조회 실패"


# 🔹 API 라우트
@app.route("/api/stock", methods=["GET"])
def stock_api():
    """한국/미국 주식 실시간 조회 API"""
    val = request.args.get("name") or request.args.get("ticker")
    if not val:
        return Response(
            json.dumps({"error": "name 또는 ticker 파라미터가 필요합니다."}, ensure_ascii=False),
            content_type="application/json; charset=utf-8",
        )

    val_upper = val.upper().strip()

    # 미리 등록된 주요 종목들 (빠른 응답용)
    stocks = {
        "005930": ("005930", "삼성전자"), "삼성전자": ("005930", "삼성전자"),
        "066570": ("066570", "LG전자"), "LG전자": ("066570", "LG전자"),
        "086890": ("086890", "이월드"), "이월드": ("086890", "이월드"),
        "TSLA": ("TSLA", "테슬라"), "테슬라": ("TSLA", "테슬라"),
        "AAPL": ("AAPL", "애플"), "애플": ("AAPL", "애플"),
    }

    # 🔸 사전에 등록된 종목이면
    if val_upper in stocks:
        sym, name = stocks[val_upper]
        price = get_korean_stock_price(sym) if sym.isdigit() else get_us_stock_price(sym)

    # 🔸 한글 입력이면 (한국 종목으로 간주)
    elif not val.isalpha():
        code = get_stock_code_by_name(val)
        if code:
            price = get_korean_stock_price(code)
            name = val
        else:
            return Response(
                json.dumps({"error": f"{val} 종목을 찾을 수 없습니다."}, ensure_ascii=False),
                content_type="application/json; charset=utf-8",
            )

    # 🔸 영문 입력이면 (미국 종목으로 간주)
    else:
        price = get_us_stock_price(val_upper)
        name = val_upper

    # 🔸 결과 반환
    res_json = json.dumps({"name": name, "price": price}, ensure_ascii=False)
    return Response(res_json, content_type="application/json; charset=utf-8")


# 🔹 로컬 테스트용 (Vercel에서는 자동 실행 안 됨)
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

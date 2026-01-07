from flask import Flask, request, Response
import requests, yfinance as yf, re, json
import urllib.parse
from bs4 import BeautifulSoup

app = Flask(__name__)

# ✅ 한국 주식 실시간 시세 (네이버 모바일 API 기반)
def get_korean_stock_price(ticker):
    url = f"https://polling.finance.naver.com/api/realtime?query=SERVICE_RECENT_ITEM:{ticker}"
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
        "Referer": f"https://m.stock.naver.com/item/main.nhn?code={ticker}",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://m.stock.naver.com"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=5)
        data = res.json()
        items = data.get("result", {}).get("areas", [{}])[0].get("datas", [])
        if not items:
            return None
        
        item = items[0]
        current_price = item.get("nv")
        if not current_price:
            return None

        return {
            "current_price": f"{int(current_price):,}",
            "change_amount": f"{int(item.get('cv', 0)):,}",
            "change_rate": float(item.get("cr", 0)),
            "volume": f"{int(item.get('aq', 0)):,}",
            "debug_info": {
                "prev_close": f"{int(item.get('pcv', 0)):,}" if item.get('pcv') else "N/A",
                "open": f"{int(item.get('ov', 0)):,}" if item.get('ov') else "N/A",
                "high": f"{int(item.get('hv', 0)):,}" if item.get('hv') else "N/A",
                "low": f"{int(item.get('lv', 0)):,}" if item.get('lv') else "N/A",
                "timestamp": item.get("st", "N/A")
            }
        }
    except Exception as e:
        print(f"❌ 네이버 API 호출 실패: {e}")
        return None


# ✅ 네이버 종목명 → 종목코드 검색
def get_ticker_by_name(name):
    try:
        encoded_name = urllib.parse.quote(name)
        url = f"https://finance.naver.com/search/searchList.naver?query={encoded_name}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=10)
        
        # 1️⃣ 리다이렉트 되는 경우
        if "code=" in res.url:
            match = re.search(r"code=(\d{6})", res.url)
            if match:
                return match.group(1)
        
        # 2️⃣ 검색 결과 리스트 페이지에서 추출
        soup = BeautifulSoup(res.text, "html.parser")
        links = soup.select("a[href*='item/main.naver?code=']")
        if links:
            match = re.search(r"code=(\d{6})", links[0]["href"])
            if match:
                return match.group(1)
    except Exception as e:
        print(f"❌ 종목명 검색 에러: {e}")
    return None


# ✅ 메인 API 엔드포인트
@app.route("/api/stock", methods=["GET"])
def api_stock():
    val = (request.args.get("name") or "").strip()
    if not val:
        return Response(
            json.dumps({"error": "종목명을 입력하세요"}, ensure_ascii=False),
            content_type="application/json; charset=utf-8"
        )

    # 사전 매핑 (빠른 처리용)
    mapping = {
        "삼성전자": "005930",
        "이월드": "084680",
        "LS ELECTRIC": "010120",
        "팜젠사이언스": "208340",
        "셀트리온": "068270",
        "카카오": "035720",
        "NAVER": "035420",
        "네이버": "035420",
        "SK하이닉스": "000660",
        "현대차": "005380",
        "LG전자": "066570",
        "포스코홀딩스": "005490",
        "기아": "000270"
    }

    ticker = mapping.get(val) or mapping.get(val.upper()) or get_ticker_by_name(val)

    # ✅ 한국 주식
    if ticker and ticker.isdigit() and len(ticker) == 6:
        rt = get_korean_stock_price(ticker)
        market = "KOSPI/KOSDAQ"
        if not rt:
            return Response(
                json.dumps({
                    "success": False,
                    "error": f"{val}({ticker}) 실시간 시세 조회 실패. 장 마감 또는 일시적 오류일 수 있습니다."
                }, ensure_ascii=False),
                content_type="application/json; charset=utf-8"
            )

    # ✅ 미국 주식
    else:
        try:
            ticker = val.upper()
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d")
            if hist.empty:
                raise ValueError("데이터 없음")
            price = round(float(hist["Close"].iloc[-1]), 2)
            rt = {"current_price": f"{price:,}"}
            market = "NASDAQ/NYSE"
        except Exception:
            return Response(
                json.dumps({
                    "success": False,
                    "error": f"'{val}' 종목을 찾을 수 없습니다."
                }, ensure_ascii=False),
                content_type="application/json; charset=utf-8"
            )

    res = {
        "success": True,
        "company_name": val,
        "ticker": ticker,
        "market": market,
        "real_time_data": rt
    }

    return Response(json.dumps(res, ensure_ascii=False),
                    content_type="application/json; charset=utf-8")


# ✅ 디버그용 (네이버 원본 응답 확인용)
@app.route("/api/debug", methods=["GET"])
def api_debug():
    ticker = request.args.get("ticker", "208340")
    url = f"https://polling.finance.naver.com/api/realtime?query=SERVICE_RECENT_ITEM:{ticker}"
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
        "Referer": f"https://m.stock.naver.com/item/main.nhn?code={ticker}",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://m.stock.naver.com"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=5)
        data = res.json()
        return Response(json.dumps(data, indent=2, ensure_ascii=False),
                        content_type="application/json; charset=utf-8")
    except Exception as e:
        return Response(json.dumps({"error": str(e)}, ensure_ascii=False),
                        content_type="application/json; charset=utf-8")


# ✅ Vercel 환경 자동 인식
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

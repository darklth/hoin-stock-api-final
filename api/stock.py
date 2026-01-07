from flask import Flask, request, Response
import requests, re, json
from bs4 import BeautifulSoup

app = Flask(__name__)

# ✅ 네이버 종목명 → 코드 변환 (모바일 기반)
def get_ticker_by_name(name):
    try:
        search_url = f"https://m.stock.naver.com/api/json/search/searchListJson.nhn?keyword={name}"
        headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)"}
        res = requests.get(search_url, headers=headers, timeout=5)
        data = res.json()

        items = data.get("result", {}).get("itemList", [])
        if not items:
            return None
        # 첫 번째 결과 사용
        ticker = items[0].get("itemcode")
        return ticker
    except Exception as e:
        print(f"❌ 종목 검색 실패: {e}")
        return None


# ✅ 실시간 시세 (모바일 API 버전, 가장 빠름)
def get_korean_stock_price(ticker):
    try:
        url = f"https://m.stock.naver.com/api/stock/{ticker}/basic"
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
            "Referer": f"https://m.stock.naver.com/item/main.nhn?code={ticker}"
        }
        res = requests.get(url, headers=headers, timeout=5)
        data = res.json()

        # ✅ 실시간 데이터 추출
        current_price = data.get("now")
        change_rate = data.get("cr")
        change_amount = data.get("cv")
        volume = data.get("aq")

        if current_price is None:
            return None

        return {
            "current_price": f"{int(current_price):,}",
            "change_amount": f"{int(change_amount):,}" if change_amount else "0",
            "change_rate": float(change_rate) if change_rate else 0.0,
            "volume": f"{int(volume):,}" if volume else "0"
        }
    except Exception as e:
        print(f"⚠️ 모바일 API 실패: {e}")
        return None


@app.route("/api/stock", methods=["GET"])
def api_stock():
    name = (request.args.get("name") or "").strip()
    if not name:
        return Response(json.dumps({"success": False, "error": "종목명을 입력하세요"}, ensure_ascii=False),
                        content_type="application/json; charset=utf-8")

    # 종목코드 조회
    ticker = get_ticker_by_name(name)
    if not ticker:
        return Response(json.dumps({"success": False, "error": f"'{name}' 종목을 찾을 수 없습니다."}, ensure_ascii=False),
                        content_type="application/json; charset=utf-8")

    # 실시간 시세 조회
    data = get_korean_stock_price(ticker)
    if not data:
        return Response(json.dumps({"success": False, "error": f"{name}({ticker}) 시세 조회 실패"}, ensure_ascii=False),
                        content_type="application/json; charset=utf-8")

    return Response(json.dumps({
        "success": True,
        "company_name": name,
        "ticker": ticker,
        "market": "KOSPI/KOSDAQ",
        "real_time_data": data
    }, ensure_ascii=False), content_type="application/json; charset=utf-8")


# ✅ 헬스체크
@app.route("/api/health", methods=["GET"])
def health_check():
    return Response(json.dumps({"status": "healthy", "service": "stock-api"}, ensure_ascii=False),
                    content_type="application/json; charset=utf-8")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

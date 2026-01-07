from flask import Flask, request, Response
import requests, yfinance as yf, re, json
import urllib.parse
from datetime import datetime
from bs4 import BeautifulSoup

app = Flask(__name__)

# ✅ 한국 주식 실시간 시세 (디버깅 추가)
def get_korean_stock_price(ticker):
    url = f"https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{ticker}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://finance.naver.com/",
        "Accept": "*/*"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=5)
        data = res.json()
        
        items = data.get('result', {}).get('areas', [{}])[0].get('datas', [])
        if items:
            item = items[0]
            
            # ✅ 디버깅: 전체 데이터 출력 (Vercel 로그에서 확인 가능)
            print(f"🔍 [{ticker}] 전체 응답 데이터:")
            print(json.dumps(item, indent=2, ensure_ascii=False))
            
            # ✅ 가능한 모든 가격 필드 확인
            current_price = item.get('nv')  # 현재가
            prev_close = item.get('pcv')     # 전일 종가
            open_price = item.get('ov')      # 시가
            high_price = item.get('hv')      # 고가
            low_price = item.get('lv')       # 저가
            
            print(f"📊 현재가(nv): {current_price}")
            print(f"📊 전일종가(pcv): {prev_close}")
            print(f"📊 시가(ov): {open_price}")
            print(f"📊 고가(hv): {high_price}")
            print(f"📊 저가(lv): {low_price}")
            
            if current_price:
                return {
                    "current_price": f"{int(current_price):,}",
                    "change_amount": f"{int(item.get('cv', 0)):,}",
                    "change_rate": float(item.get('cr', 0)),
                    "volume": f"{int(item.get('aq', 0)):,}",
                    # ✅ 디버깅용 추가 정보
                    "debug_info": {
                        "prev_close": f"{int(prev_close):,}" if prev_close else "N/A",
                        "open": f"{int(open_price):,}" if open_price else "N/A",
                        "high": f"{int(high_price):,}" if high_price else "N/A",
                        "low": f"{int(low_price):,}" if low_price else "N/A"
                    }
                }
    except Exception as e:
        print(f"❌ 네이버 API 호출 실패: {e}")
    
    return None

# ✅ 네이버 종목명 -> 코드 변환 (강화 버전)
def get_ticker_by_name(name):
    try:
        encoded_name = urllib.parse.quote(name)
        url = f"https://finance.naver.com/search/searchList.naver?query={encoded_name}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://finance.naver.com/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        
        res = requests.get(url, headers=headers, timeout=10)
        
        # 1. 즉시 해당 종목 페이지로 이동한 경우
        if "code=" in res.url:
            match = re.search(r'code=(\d{6})', res.url)
            if match: return match.group(1)
            
        # 2. 검색 결과 리스트 페이지인 경우
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 여러 선택자 시도
        links = soup.select("a[href*='item/main.naver?code=']")
        if links:
            match = re.search(r'code=(\d{6})', links[0]['href'])
            if match: return match.group(1)
        
        # 추가 시도
        link = soup.select_one(".section_search table.type_1 td.tit a")
        if link and 'href' in link.attrs:
            match = re.search(r'code=(\d{6})', link['href'])
            if match: return match.group(1)
            
    except Exception as e:
        print(f"❌ 검색 에러: {e}")
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
    
    # 1. 국장 우선 검색 (사전 매핑 포함)
    mapping = {
        "삼성전자": "005930", 
        "이월드": "084680", 
        "LS ELECTRIC": "010120",
        "팜젠사이언스": "208340",  # ✅ 추가
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
    else:
        # 2. 미장 시도
        try:
            ticker = val.upper()
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d")
            
            if not hist.empty:
                price = round(float(hist["Close"].iloc[-1]), 2)
                rt = {"current_price": price}
                market = "NASDAQ/NYSE"
            else:
                return Response(
                    json.dumps({
                        "success": False,
                        "error": f"'{val}' 종목을 찾을 수 없습니다. 정확한 종목명을 입력해주세요."
                    }, ensure_ascii=False),
                    content_type="application/json; charset=utf-8"
                )
        except Exception as e:
            return Response(
                json.dumps({
                    "success": False,
                    "error": f"조회 실패"
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
    return Response(
        json.dumps(res, ensure_ascii=False), 
        content_type="application/json; charset=utf-8"
    )

# ✅ 디버깅용 엔드포인트 (네이버 API 원본 데이터 확인)
@app.route("/api/debug", methods=["GET"])
def api_debug():
    ticker = request.args.get("ticker", "208340")  # 기본값: 팜젠사이언스
    
    url = f"https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{ticker}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.naver.com/",
        "Accept": "*/*"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=5)
        data = res.json()
        
        return Response(
            json.dumps(data, indent=2, ensure_ascii=False),
            content_type="application/json; charset=utf-8"
        )
    except Exception as e:
        return Response(
            json.dumps({"error": str(e)}, ensure_ascii=False),
            content_type="application/json; charset=utf-8"
        )

# ✅ Vercel Serverless Function용 (자동으로 처리됨)

from flask import Flask, request, Response
import requests, yfinance as yf, re, json
import urllib.parse
from bs4 import BeautifulSoup

app = Flask(__name__)

# ✅ 한국 주식 실시간 시세 (네이버 모바일 API 기반)
def get_korean_stock_price(ticker, include_debug=False):
    """
    네이버 모바일 API로 실시간 주식 시세 조회
    
    Args:
        ticker (str): 6자리 종목코드
        include_debug (bool): 디버그 정보 포함 여부
    
    Returns:
        dict: 주식 시세 정보 또는 None
    """
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
        res.raise_for_status()
        data = res.json()
        
        items = data.get("result", {}).get("areas", [{}])[0].get("datas", [])
        if not items:
            print(f"⚠️ [{ticker}] API 응답에 데이터 없음")
            return None
        
        item = items[0]
        current_price = item.get("nv")
        
        if not current_price:
            print(f"⚠️ [{ticker}] 현재가(nv) 데이터 없음")
            return None

        result = {
            "current_price": f"{int(current_price):,}",
            "change_amount": f"{int(item.get('cv', 0)):,}",
            "change_rate": float(item.get("cr", 0)),
            "volume": f"{int(item.get('aq', 0)):,}"
        }
        
        # 디버그 정보 추가 (요청 시에만)
        if include_debug:
            result["debug_info"] = {
                "prev_close": f"{int(item.get('pcv', 0)):,}" if item.get('pcv') else "N/A",
                "open": f"{int(item.get('ov', 0)):,}" if item.get('ov') else "N/A",
                "high": f"{int(item.get('hv', 0)):,}" if item.get('hv') else "N/A",
                "low": f"{int(item.get('lv', 0)):,}" if item.get('lv') else "N/A",
                "timestamp": item.get("st", "N/A")
            }
        
        return result
        
    except requests.exceptions.Timeout:
        print(f"❌ [{ticker}] API 요청 타임아웃")
    except requests.exceptions.RequestException as e:
        print(f"❌ [{ticker}] API 요청 실패: {e}")
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        print(f"❌ [{ticker}] 응답 파싱 실패: {e}")
    except Exception as e:
        print(f"❌ [{ticker}] 예상치 못한 오류: {e}")
    
    return None


# ✅ 네이버 종목명 → 종목코드 검색 (다중 전략)
def get_ticker_by_name(name):
    """
    네이버 금융 검색으로 종목명을 6자리 종목코드로 변환
    여러 방법을 시도하여 성공률 극대화
    
    Args:
        name (str): 종목명
    
    Returns:
        str: 6자리 종목코드 또는 None
    """
    
    # 전략 1: 네이버 금융 PC 검색
    try:
        encoded_name = urllib.parse.quote(name)
        url = f"https://finance.naver.com/search/searchList.naver?query={encoded_name}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://finance.naver.com/"
        }
        res = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        
        # 리다이렉트로 바로 종목 페이지로 이동한 경우
        if "item/main.naver" in res.url and "code=" in res.url:
            match = re.search(r"code=(\d{6})", res.url)
            if match:
                code = match.group(1)
                print(f"✅ [전략1-리다이렉트] {name} → {code}")
                return code
        
        # 검색 결과 페이지 파싱
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 방법 1: a 태그에서 code 찾기
        links = soup.select("a[href*='item/main.naver?code=']")
        if links:
            for link in links[:3]:  # 상위 3개 결과 확인
                match = re.search(r"code=(\d{6})", link.get("href", ""))
                if match:
                    code = match.group(1)
                    print(f"✅ [전략1-링크] {name} → {code}")
                    return code
        
        # 방법 2: td.tit 안의 링크 찾기
        tit_links = soup.select("td.tit a")
        if tit_links:
            for link in tit_links[:3]:
                match = re.search(r"code=(\d{6})", link.get("href", ""))
                if match:
                    code = match.group(1)
                    print(f"✅ [전략1-테이블] {name} → {code}")
                    return code
                    
    except Exception as e:
        print(f"⚠️ [전략1] 실패: {e}")
    
    # 전략 2: 네이버 증권 모바일 검색 API
    try:
        encoded_name = urllib.parse.quote(name)
        url = f"https://m.stock.naver.com/api/search/itemList?query={encoded_name}"
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
            "Referer": "https://m.stock.naver.com/",
            "Accept": "application/json"
        }
        res = requests.get(url, headers=headers, timeout=10)
        data = res.json()
        
        # itemList에서 첫 번째 결과 추출
        items = data.get("result", {}).get("itemList", [])
        if items:
            for item in items[:3]:  # 상위 3개 확인
                code = item.get("code", "")
                item_name = item.get("name", "")
                if code and code.isdigit() and len(code) == 6:
                    print(f"✅ [전략2-모바일API] {name} → {code} ({item_name})")
                    return code
                    
    except Exception as e:
        print(f"⚠️ [전략2] 실패: {e}")
    
    # 전략 3: 네이버 자동완성 API
    try:
        encoded_name = urllib.parse.quote(name)
        url = f"https://ac.finance.naver.com/ac?q={encoded_name}&q_enc=euc-kr&t_koreng=1&st=111"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.naver.com/"
        }
        res = requests.get(url, headers=headers, timeout=10)
        
        # 응답 형식: query|종목명|code
        lines = res.text.strip().split('\n')
        if lines and lines[0] != "null":
            for line in lines[:3]:
                parts = line.split('|')
                if len(parts) >= 3:
                    code = parts[2].strip()
                    if code.isdigit() and len(code) == 6:
                        print(f"✅ [전략3-자동완성] {name} → {code}")
                        return code
                        
    except Exception as e:
        print(f"⚠️ [전략3] 실패: {e}")
    
    print(f"❌ 모든 검색 전략 실패: {name}")
    return None


# ✅ 영문 약어로 한국 종목 검색 (HPSP, LG, SK 등)
def search_by_english_name(name):
    """
    영문 약어로 한국 종목 검색
    예: HPSP, LG, SK, NAVER 등
    
    Args:
        name (str): 영문 약어
    
    Returns:
        str: 6자리 종목코드 또는 None
    """
    try:
        # 네이버 통합 검색 API (영문 지원)
        encoded_name = urllib.parse.quote(name)
        url = f"https://m.stock.naver.com/api/search/itemList?query={encoded_name}"
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
            "Referer": "https://m.stock.naver.com/",
            "Accept": "application/json"
        }
        res = requests.get(url, headers=headers, timeout=10)
        data = res.json()
        
        items = data.get("result", {}).get("itemList", [])
        if items:
            # 영문 약어가 정확히 매칭되는 것 우선
            for item in items:
                code = item.get("code", "")
                item_name = item.get("name", "")
                reutersCode = item.get("reutersCode", "")  # 영문 약어
                
                # 영문 약어가 정확히 일치하거나, 종목명에 포함되는 경우
                if code and code.isdigit() and len(code) == 6:
                    if (reutersCode and name.upper() in reutersCode.upper()) or \
                       (name.upper() in item_name.upper()):
                        print(f"✅ [영문검색] {name} → {code} ({item_name})")
                        return code
            
            # 정확히 매칭 안되면 첫 번째 결과 사용
            first_item = items[0]
            code = first_item.get("code", "")
            if code and code.isdigit() and len(code) == 6:
                print(f"✅ [영문검색-첫결과] {name} → {code}")
                return code
                
    except Exception as e:
        print(f"⚠️ 영문 검색 실패: {name} - {e}")
    
    return None


# ✅ 메인 API 엔드포인트
@app.route("/api/stock", methods=["GET"])
def api_stock():
    """
    주식 정보 조회 API
    
    Query Parameters:
        - name (required): 종목명 또는 티커
        - debug (optional): "true"이면 디버그 정보 포함
    
    Returns:
        JSON: 주식 시세 정보
    """
    val = (request.args.get("name") or "").strip()
    include_debug = request.args.get("debug", "").lower() == "true"
    
    if not val:
        return Response(
            json.dumps({"success": False, "error": "종목명을 입력하세요"}, ensure_ascii=False),
            content_type="application/json; charset=utf-8",
            status=400
        )

    # 🚀 사전 매핑 (자주 조회되는 종목은 빠르게 처리)
    mapping = {
        "삼성전자": "005930",
        "이월드": "084680",
        "LS ELECTRIC": "010120",
        "팜젠사이언스": "004720",
        "셀트리온": "068270",
        "카카오": "035720",
        "NAVER": "035420",
        "네이버": "035420",
        "SK하이닉스": "000660",
        "현대차": "005380",
        "LG전자": "066570",
        "포스코홀딩스": "005490",
        "기아": "000270",
        "HPSP": "403870"  # ✅ HPSP 추가
    }

    ticker = mapping.get(val) or mapping.get(val.upper()) or get_ticker_by_name(val)

    # ✅ 한국 주식 처리
    if ticker and ticker.isdigit() and len(ticker) == 6:
        rt = get_korean_stock_price(ticker, include_debug)
        market = "KOSPI/KOSDAQ"
        
        if not rt:
            return Response(
                json.dumps({
                    "success": False,
                    "error": f"'{val}'({ticker}) 실시간 시세 조회 실패. 장 마감 또는 일시적 오류일 수 있습니다."
                }, ensure_ascii=False),
                content_type="application/json; charset=utf-8",
                status=503
            )

    # ✅ 미국 주식 처리 (한국 주식 검색 실패 시에만)
    else:
        # 영문만 있는 경우 한국/미국 둘 다 시도
        try:
            # 한국 주식 재시도 (영문 약어의 경우)
            if val.upper() == val and not ticker:
                # 네이버 자동완성으로 영문 약어 검색
                ticker = search_by_english_name(val)
                if ticker:
                    rt = get_korean_stock_price(ticker, include_debug)
                    if rt:
                        market = "KOSPI/KOSDAQ"
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
            
            # 미국 주식 시도
            ticker = val.upper()
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d")
            
            if hist.empty:
                raise ValueError("데이터 없음")
            
            price = round(float(hist["Close"].iloc[-1]), 2)
            rt = {"current_price": f"{price:,.2f}"}
            market = "NASDAQ/NYSE"
            
            print(f"✅ 미국 주식 조회 성공: {ticker} = ${price}")
            
        except Exception as e:
            print(f"❌ 미국 주식 조회 실패: {val} - {e}")
            return Response(
                json.dumps({
                    "success": False,
                    "error": f"'{val}' 종목을 찾을 수 없습니다. 정확한 종목명 또는 티커를 입력해주세요."
                }, ensure_ascii=False),
                content_type="application/json; charset=utf-8",
                status=404
            )

    # 성공 응답
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


# ✅ 디버그용 엔드포인트 (네이버 API 원본 응답 확인)
@app.route("/api/debug", methods=["GET"])
def api_debug():
    """
    네이버 API 원본 응답 확인용 디버그 엔드포인트
    
    Query Parameters:
        - ticker: 6자리 종목코드 (기본값: 208340 - 팜젠사이언스)
    """
    ticker = request.args.get("ticker", "208340")
    
    # 티커 검증
    if not (ticker.isdigit() and len(ticker) == 6):
        return Response(
            json.dumps({"error": "6자리 종목코드를 입력하세요"}, ensure_ascii=False),
            content_type="application/json; charset=utf-8",
            status=400
        )
    
    url = f"https://polling.finance.naver.com/api/realtime?query=SERVICE_RECENT_ITEM:{ticker}"
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
        "Referer": f"https://m.stock.naver.com/item/main.nhn?code={ticker}",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://m.stock.naver.com"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=5)
        res.raise_for_status()
        data = res.json()
        
        return Response(
            json.dumps(data, indent=2, ensure_ascii=False),
            content_type="application/json; charset=utf-8"
        )
    except Exception as e:
        return Response(
            json.dumps({"error": f"API 호출 실패: {str(e)}"}, ensure_ascii=False),
            content_type="application/json; charset=utf-8",
            status=500
        )


# ✅ 헬스체크 엔드포인트
@app.route("/api/health", methods=["GET"])
def health_check():
    """서버 상태 확인용"""
    return Response(
        json.dumps({"status": "healthy", "service": "stock-api"}, ensure_ascii=False),
        content_type="application/json; charset=utf-8"
    )


# ✅ Vercel 환경 자동 인식 (로컬 개발용)
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

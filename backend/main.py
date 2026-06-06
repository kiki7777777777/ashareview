from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os, sys

sys.path.insert(0, os.path.dirname(__file__))
import data_provider as dp
import indicators as ind

app = FastAPI(title="A股量化仪表盘")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DEFAULT_SYMBOLS = [
    {"code": "300308", "name": "中际旭创"},
    {"code": "300806", "name": "斯迪克"},
    {"code": "601138", "name": "工业富联"},
    {"code": "300394", "name": "天孚通信"},
    {"code": "002741", "name": "光华科技"},
    {"code": "603063", "name": "禾望电气"},
]


@app.get("/api/status")
def get_status():
    return {"connected": True, "source": "akshare · 东方财富", "message": "数据正常"}


@app.get("/api/quote/{symbol}")
def get_quote(symbol: str):
    q = dp.get_realtime_quote(symbol.strip().zfill(6))
    if q is None:
        raise HTTPException(status_code=404, detail="无法获取实时行情")
    return q


@app.get("/api/symbols")
def get_symbols():
    return {"symbols": DEFAULT_SYMBOLS}


@app.get("/api/analyze/{symbol}")
def analyze_symbol(
    symbol: str,
    interval: str = Query(default="1d", pattern="^(1d|1h|1min)$"),
):
    symbol = symbol.strip().zfill(6)
    try:
        df = dp.get_stock_data(symbol, interval=interval)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法获取 {symbol} 数据: {str(e)}")

    min_bars = 30 if interval != "1d" else 60
    if df is None or len(df) < min_bars:
        bars = len(df) if df is not None else 0
        raise HTTPException(status_code=400, detail=f"数据不足: {symbol} ({bars} 条)")

    try:
        result = ind.analyze(df, interval=interval)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")

    info = dp.get_stock_info(symbol)

    # 涨跌停幅度
    limit = 20 if symbol.startswith(("688", "300")) else 10

    result["symbol"]    = symbol
    result["interval"]  = interval
    result["info"]      = info
    result["source"]    = "akshare · 东方财富"
    result["limit_pct"] = limit
    return result


@app.get("/api/confluence/{symbol}")
def get_confluence(symbol: str):
    symbol = symbol.strip().zfill(6)
    results = {}
    for iv in ["1d", "1h", "1min"]:
        try:
            df = dp.get_stock_data(symbol, interval=iv)
            min_bars = 30 if iv != "1d" else 60
            if df is None or len(df) < min_bars:
                results[iv] = None
                continue
            a = ind.analyze(df, interval=iv)
            results[iv] = {
                "trend":    a["signals"].get("trend",    {}),
                "macd":     a["signals"].get("macd",     {}),
                "rsi":      a["signals"].get("rsi",      {}),
                "kdj":      a["signals"].get("kdj",      {}),
                "bull_pct": a["bull_pct"],
                "score":    round(sum(s["score"] for s in a["signals"].values()), 1),
            }
        except Exception:
            results[iv] = None

    valid = [v for v in results.values() if v is not None]
    if len(valid) >= 2:
        dirs = [1 if v["score"] > 0 else (-1 if v["score"] < 0 else 0) for v in valid]
        if all(d > 0 for d in dirs):
            confluence = "bullish"
        elif all(d < 0 for d in dirs):
            confluence = "bearish"
        else:
            confluence = "mixed"
    else:
        confluence = "mixed"

    return {"intervals": results, "confluence": confluence}


# ── Serve frontend ────────────────────────────────────────────────────────────
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(frontend_dir, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)

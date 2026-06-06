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
    {"code": "600519", "name": "贵州茅台"},
    {"code": "300750", "name": "宁德时代"},
    {"code": "002594", "name": "比亚迪"},
    {"code": "601318", "name": "中国平安"},
    {"code": "000858", "name": "五粮液"},
    {"code": "600036", "name": "招商银行"},
    {"code": "000001", "name": "平安银行"},
    {"code": "688981", "name": "中芯国际"},
]


@app.get("/api/status")
def get_status():
    return {"connected": True, "source": "akshare · 东方财富", "message": "数据正常"}


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

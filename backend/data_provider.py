import baostock as bs
import pandas as pd
import requests, re
from datetime import datetime, timedelta, timezone
import threading
import logging

logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))

# baostock 全局 session（模块加载时登录一次）
_lock = threading.Lock()
_logged_in = False


def _ensure_login():
    global _logged_in
    with _lock:
        if not _logged_in:
            lg = bs.login()
            if lg.error_code == "0":
                _logged_in = True
            else:
                raise RuntimeError(f"baostock 登录失败: {lg.error_msg}")


def _symbol_to_bs(symbol: str) -> str:
    """将6位代码转换为 baostock 格式 (sh.600519 / sz.000001)"""
    symbol = symbol.strip().zfill(6)
    prefix = "sz" if symbol[0] in ("0", "3") else "sh"
    return f"{prefix}.{symbol}"


def get_stock_data(symbol: str, interval: str = "1d") -> pd.DataFrame:
    _ensure_login()
    bs_code = _symbol_to_bs(symbol)
    today   = datetime.now().strftime("%Y-%m-%d")

    if interval == "1d":
        start = (datetime.now() - timedelta(days=500)).strftime("%Y-%m-%d")
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume,pctChg,turn",
            start_date=start, end_date=today,
            frequency="d", adjustflag="2"
        )
        rows = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())
        df = pd.DataFrame(rows, columns=["date","open","high","low","close","volume","pct_chg","turnover"])
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        for c in ["open","high","low","close","volume","pct_chg","turnover"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        return df.dropna(subset=["open","close"])

    # 分钟数据 (1h → 60分钟; 1min → 5分钟)
    freq     = "60" if interval == "1h" else "5"
    days_back = 30  if interval == "1h" else 10
    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    rs = bs.query_history_k_data_plus(
        bs_code,
        "date,time,open,high,low,close,volume",
        start_date=start, end_date=today,
        frequency=freq, adjustflag="2"
    )
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())
    df = pd.DataFrame(rows, columns=["date","time","open","high","low","close","volume"])
    # 合并日期+时间 → 北京时间 datetime
    df["datetime"] = pd.to_datetime(df["date"] + " " + df["time"].str[:8])
    df = df.set_index("datetime")
    for c in ["open","high","low","close","volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[["open","high","low","close","volume"]].dropna()
    # 标记为北京时间（UTC+8），让 indicators.py 的 timestamp() 得到正确 UTC 戳
    df.index = pd.DatetimeIndex([t.replace(tzinfo=CST) for t in df.index])
    return df


def get_stock_info(symbol: str) -> dict:
    _ensure_login()
    bs_code = _symbol_to_bs(symbol)
    try:
        rs = bs.query_stock_basic(code=bs_code)
        row = None
        fields = rs.fields or []
        while rs.error_code == "0" and rs.next():
            row = rs.get_row_data()
        if row:
            info_map = dict(zip(fields, row))
            name = info_map.get("code_name", symbol)
        else:
            name = symbol

        # 获取市盈率等估值数据
        today = datetime.now().strftime("%Y-%m-%d")
        rs2 = bs.query_history_k_data_plus(
            bs_code, "date,pbMRQ,peTTM,psTTM,pcfNcfTTM",
            start_date=today, end_date=today, frequency="d"
        )
        pe, pb = None, None
        while rs2.error_code == "0" and rs2.next():
            r2 = rs2.get_row_data()
            if len(r2) >= 3:
                pb = float(r2[1]) if r2[1] else None
                pe = float(r2[2]) if r2[2] else None

        return {"name": name, "sector": "", "total_mv": 0, "float_mv": 0,
                "pe_ratio": pe, "pb_ratio": pb}
    except Exception as e:
        logger.warning(f"get_stock_info {symbol}: {e}")
        return {"name": symbol, "sector": "", "total_mv": 0, "float_mv": 0,
                "pe_ratio": None, "pb_ratio": None}


def get_realtime_quote(symbol: str) -> dict | None:
    """从新浪财经拉取实时行情（无需VPN，国内可用）"""
    code   = symbol.strip().zfill(6)
    prefix = "sz" if code[0] in ("0", "3") else "sh"
    url    = f"https://hq.sinajs.cn/list={prefix}{code}"
    headers = {
        "Referer":    "https://finance.sina.com.cn/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    try:
        r = requests.get(url, headers=headers, timeout=6)
        r.encoding = "gbk"
        m = re.search(r'"([^"]+)"', r.text)
        if not m or not m.group(1).strip(","):
            return None
        p = m.group(1).split(",")
        if len(p) < 32 or not p[3]:
            return None
        prev  = float(p[2]) if p[2] else 0
        price = float(p[3]) if p[3] else 0
        return {
            "name":       p[0],
            "open":       float(p[1]) if p[1] else price,
            "prev_close": prev,
            "price":      price,
            "high":       float(p[4]) if p[4] else price,
            "low":        float(p[5]) if p[5] else price,
            "volume":     int(p[8])   if p[8]  else 0,
            "amount":     float(p[9]) if p[9]  else 0,
            "pct_chg":    round((price - prev) / prev * 100, 2) if prev else 0,
            "date":       p[30],
            "time":       p[31],
        }
    except Exception as e:
        logger.warning(f"Realtime quote {symbol}: {e}")
        return None


# 登录（进程启动时）
try:
    _ensure_login()
except Exception as e:
    logger.warning(f"baostock 启动登录失败: {e}")

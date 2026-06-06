import pandas as pd
import numpy as np


def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def calculate_macd(close, fast=12, slow=26, signal=9):
    ema_fast   = calculate_ema(close, fast)
    ema_slow   = calculate_ema(close, slow)
    macd_line  = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    histogram  = macd_line - signal_line
    return macd_line, signal_line, histogram


def calculate_rsi(close, period=14):
    delta    = close.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calculate_bollinger(close, period=20, std_dev=2):
    sma   = close.rolling(period).mean()
    std   = close.rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    pct_b = (close - lower) / (upper - lower)
    return upper, sma, lower, pct_b


def calculate_atr(high, low, close, period=14):
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, min_periods=period).mean()


def calculate_volume_trend(volume, close, period=20):
    price_change = close.pct_change()
    up_vol   = (volume * (price_change > 0)).rolling(period).sum()
    down_vol = (volume * (price_change < 0)).rolling(period).sum()
    total    = up_vol + down_vol
    return (up_vol / total.replace(0, np.nan)).fillna(0.5)


def calculate_kdj(high, low, close, n=9, m1=3, m2=3):
    """KDJ 随机指标 (A股最常用)"""
    lowest  = low.rolling(n, min_periods=1).min()
    highest = high.rolling(n, min_periods=1).max()
    denom   = (highest - lowest).replace(0, np.nan)
    rsv     = ((close - lowest) / denom * 100).fillna(50)
    k = rsv.ewm(com=m1 - 1, adjust=False).mean()
    d = k.ewm(com=m2 - 1, adjust=False).mean()
    j = 3 * k - 2 * d
    return k, d, j


def calculate_vwap(high, low, close, volume):
    tp = (high + low + close) / 3
    return (tp * volume).cumsum() / volume.cumsum().replace(0, np.nan)


def find_sr_levels(high, low, n=5):
    window    = max(5, len(high) // 20)
    local_max = high[(high == high.rolling(window, center=True).max())]
    local_min = low[(low  == low.rolling(window,  center=True).min())]

    def cluster(vals, tol=0.005):
        levels = []
        for v in sorted(vals):
            if not levels or abs(v - levels[-1]) / levels[-1] > tol:
                levels.append(v)
            else:
                levels[-1] = (levels[-1] + v) / 2
        return levels

    resistance = sorted(cluster(local_max.tolist()), reverse=True)[:n]
    support    = sorted(cluster(local_min.tolist()))[-n:]
    return support, resistance


def generate_trade_signals(close, high, low, vwap, rsi, histogram, ts_fn):
    signals   = []
    prev_above = None if np.isnan(vwap.iloc[0]) else (close.iloc[0] > vwap.iloc[0])

    for i in range(2, len(close)):
        c, v  = close.iloc[i],     vwap.iloc[i]
        r, h  = rsi.iloc[i],       histogram.iloc[i]
        h1    = histogram.iloc[i - 1]
        t     = ts_fn(close.index[i])
        above = (c > v) if not np.isnan(v) else None

        if above and prev_above is False and r > 45:
            signals.append({"time": t, "type": "buy",  "price": round(c, 2), "reason": "VWAP 突破↑"})
        elif above is False and prev_above and r < 55:
            signals.append({"time": t, "type": "sell", "price": round(c, 2), "reason": "VWAP 跌破↓"})

        if h > 0 and h1 <= 0 and r < 70:
            signals.append({"time": t, "type": "buy",  "price": round(c, 2), "reason": "MACD 金叉"})
        elif h < 0 and h1 >= 0 and r > 30:
            signals.append({"time": t, "type": "sell", "price": round(c, 2), "reason": "MACD 死叉"})

        if r > 32 and rsi.iloc[i - 1] <= 32:
            signals.append({"time": t, "type": "buy",  "price": round(c, 2), "reason": "RSI 超卖反弹"})
        elif r < 68 and rsi.iloc[i - 1] >= 68:
            signals.append({"time": t, "type": "sell", "price": round(c, 2), "reason": "RSI 超买回落"})

        if above is not None:
            prev_above = above

    seen = {}
    for s in signals:
        seen[s["time"]] = s
    return list(seen.values())[-40:]


def analyze(df: pd.DataFrame, interval: str = "1d") -> dict:
    close  = df["close"]
    high   = df["high"]
    low    = df["low"]
    volume = df["volume"]

    macd_line, signal_line, histogram = calculate_macd(close)
    vwap        = calculate_vwap(high, low, close, volume)
    rsi         = calculate_rsi(close)
    upper_bb, mid_bb, lower_bb, pct_b = calculate_bollinger(close)
    atr         = calculate_atr(high, low, close)
    bull_vol    = calculate_volume_trend(volume, close)
    ema20       = calculate_ema(close, 20)
    ema50       = calculate_ema(close, 50)
    ema200      = calculate_ema(close, 200)
    kdj_k, kdj_d, kdj_j = calculate_kdj(high, low, close)

    latest         = close.iloc[-1]
    latest_rsi     = rsi.iloc[-1]
    latest_macd    = macd_line.iloc[-1]
    latest_signal  = signal_line.iloc[-1]
    latest_hist    = histogram.iloc[-1]
    prev_hist      = histogram.iloc[-2]
    latest_pct_b   = pct_b.iloc[-1]
    latest_atr     = atr.iloc[-1]
    latest_vol     = bull_vol.iloc[-1]
    latest_ema20   = ema20.iloc[-1]
    latest_ema50   = ema50.iloc[-1]
    latest_ema200  = ema200.iloc[-1]
    latest_k       = kdj_k.iloc[-1]
    latest_d       = kdj_d.iloc[-1]
    latest_j       = kdj_j.iloc[-1]
    prev_k         = kdj_k.iloc[-2]
    prev_d         = kdj_d.iloc[-2]

    # 今日涨跌幅
    if "pct_chg" in df.columns:
        daily_change = float(df["pct_chg"].iloc[-1])
    elif len(close) > 1:
        daily_change = (close.iloc[-1] / close.iloc[-2] - 1) * 100
    else:
        daily_change = 0.0

    ret5  = (close.iloc[-1] / close.iloc[-6]  - 1) * 100 if len(close) > 5  else daily_change
    ret20 = (close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) > 20 else daily_change

    # ── Signals ──────────────────────────────────────────────────────────────
    signals = {}

    if latest_macd > latest_signal and latest_hist > prev_hist:
        signals["macd"] = {"value": "bullish", "label": "MACD 金叉上升", "score": 1}
    elif latest_macd < latest_signal and latest_hist < prev_hist:
        signals["macd"] = {"value": "bearish", "label": "MACD 死叉下降", "score": -1}
    else:
        signals["macd"] = {"value": "neutral",  "label": "MACD 信号混合", "score": 0}

    if latest_rsi > 70:
        signals["rsi"] = {"value": "bearish", "label": f"RSI 超买 ({latest_rsi:.1f})", "score": -1}
    elif latest_rsi < 30:
        signals["rsi"] = {"value": "bullish", "label": f"RSI 超卖 ({latest_rsi:.1f})", "score": 1}
    elif latest_rsi > 55:
        signals["rsi"] = {"value": "bullish", "label": f"RSI 偏强 ({latest_rsi:.1f})", "score": 0.5}
    elif latest_rsi < 45:
        signals["rsi"] = {"value": "bearish", "label": f"RSI 偏弱 ({latest_rsi:.1f})", "score": -0.5}
    else:
        signals["rsi"] = {"value": "neutral",  "label": f"RSI 中性 ({latest_rsi:.1f})", "score": 0}

    if latest > latest_ema20 > latest_ema50 > latest_ema200:
        signals["trend"] = {"value": "bullish", "label": "强势上涨趋势", "score": 1}; trend_label = "上涨"
    elif latest < latest_ema20 < latest_ema50 < latest_ema200:
        signals["trend"] = {"value": "bearish", "label": "强势下跌趋势", "score": -1}; trend_label = "下跌"
    elif latest > latest_ema20 and latest_ema20 > latest_ema50:
        signals["trend"] = {"value": "bullish", "label": "短期上涨趋势", "score": 0.5}; trend_label = "震荡偏多"
    elif latest < latest_ema20 and latest_ema20 < latest_ema50:
        signals["trend"] = {"value": "bearish", "label": "短期下跌趋势", "score": -0.5}; trend_label = "震荡偏空"
    else:
        signals["trend"] = {"value": "neutral",  "label": "横盘震荡", "score": 0}; trend_label = "震荡"

    if latest_pct_b > 1.0:
        signals["bollinger"] = {"value": "bearish", "label": "突破布林上轨", "score": -0.5}
    elif latest_pct_b < 0.0:
        signals["bollinger"] = {"value": "bullish", "label": "触及布林下轨", "score": 0.5}
    elif latest_pct_b > 0.6:
        signals["bollinger"] = {"value": "bullish", "label": f"布林通道上方 ({latest_pct_b:.0%})", "score": 0.3}
    elif latest_pct_b < 0.4:
        signals["bollinger"] = {"value": "bearish", "label": f"布林通道下方 ({latest_pct_b:.0%})", "score": -0.3}
    else:
        signals["bollinger"] = {"value": "neutral",  "label": f"布林通道中部 ({latest_pct_b:.0%})", "score": 0}

    if latest_vol > 0.65:
        signals["volume"] = {"value": "bullish", "label": f"量能偏多 ({latest_vol:.0%})", "score": 0.5}
    elif latest_vol < 0.35:
        signals["volume"] = {"value": "bearish", "label": f"量能偏空 ({latest_vol:.0%})", "score": -0.5}
    else:
        signals["volume"] = {"value": "neutral",  "label": f"量能均衡 ({latest_vol:.0%})", "score": 0}

    if ret5 > 2 and ret20 > 5:
        signals["momentum"] = {"value": "bullish", "label": f"动量强 (5日 {ret5:.1f}%)", "score": 1}
    elif ret5 < -2 and ret20 < -5:
        signals["momentum"] = {"value": "bearish", "label": f"动量弱 (5日 {ret5:.1f}%)", "score": -1}
    elif ret5 > 0:
        signals["momentum"] = {"value": "bullish", "label": f"短期正动量 (5日 {ret5:.1f}%)", "score": 0.3}
    elif ret5 < 0:
        signals["momentum"] = {"value": "bearish", "label": f"短期负动量 (5日 {ret5:.1f}%)", "score": -0.3}
    else:
        signals["momentum"] = {"value": "neutral",  "label": "动量中性", "score": 0}

    # KDJ signal
    if latest_j < 20:
        signals["kdj"] = {"value": "bullish", "label": f"KDJ 超卖区 (J={latest_j:.1f})", "score": 1}
    elif latest_j > 80:
        signals["kdj"] = {"value": "bearish", "label": f"KDJ 超买区 (J={latest_j:.1f})", "score": -1}
    elif latest_k > latest_d and prev_k <= prev_d:
        signals["kdj"] = {"value": "bullish", "label": f"KDJ 金叉 (K={latest_k:.1f})", "score": 0.7}
    elif latest_k < latest_d and prev_k >= prev_d:
        signals["kdj"] = {"value": "bearish", "label": f"KDJ 死叉 (K={latest_k:.1f})", "score": -0.7}
    elif latest_k > 50:
        signals["kdj"] = {"value": "bullish", "label": f"KDJ 偏强 (K={latest_k:.1f})", "score": 0.3}
    elif latest_k < 50:
        signals["kdj"] = {"value": "bearish", "label": f"KDJ 偏弱 (K={latest_k:.1f})", "score": -0.3}
    else:
        signals["kdj"] = {"value": "neutral",  "label": f"KDJ 中性 (K={latest_k:.1f})", "score": 0}

    total_score = sum(s["score"] for s in signals.values())
    max_score   = len(signals)
    bull_pct    = max(0.0, min(1.0, (total_score + max_score) / (2 * max_score)))

    if total_score >= 2.0:
        strategy, strategy_color = "做多", "bullish"
    elif total_score <= -2.0:
        strategy, strategy_color = "做空", "bearish"
    else:
        strategy, strategy_color = "观望", "neutral"

    entry_price = latest
    stop_loss   = round(latest - 2 * latest_atr, 2) if strategy == "做多" else round(latest + 2 * latest_atr, 2)
    target      = round(latest + 3 * latest_atr, 2) if strategy == "做多" else round(latest - 3 * latest_atr, 2)

    # ── Chart data ────────────────────────────────────────────────────────────
    n        = min(200, len(df))
    recent   = df.tail(n)
    idx      = recent.index
    intraday = interval in ("1h", "1min")

    def ts(t):
        if intraday:
            return int(t.timestamp())
        return t.strftime("%Y-%m-%d")

    # A股颜色: 红涨绿跌
    candles = [
        {"time": ts(t), "open": round(r.open, 2), "high": round(r.high, 2),
         "low": round(r.low, 2), "close": round(r.close, 2)}
        for t, r in recent.iterrows()
    ]
    volumes = [
        {"time": ts(t),
         "value": int(r.volume),
         "color": "rgba(220,53,69,0.5)" if r.close >= r.open else "rgba(40,167,69,0.5)"}
        for t, r in recent.iterrows()
    ]

    def series(s, decimals=4):
        vals = s.tail(n)
        return [{"time": ts(t), "value": round(v, decimals)}
                for t, v in zip(idx, vals) if not np.isnan(v)]

    def macd_hist_series():
        vals = histogram.tail(n)
        return [
            {"time": ts(t), "value": round(v, 4),
             "color": "rgba(220,53,69,0.7)" if v >= 0 else "rgba(40,167,69,0.7)"}
            for t, v in zip(idx, vals) if not np.isnan(v)
        ]

    sr_support, sr_resistance = find_sr_levels(high, low)
    latest_vwap = vwap.dropna().iloc[-1] if not vwap.dropna().empty else None

    trade_signals = generate_trade_signals(
        close.tail(n * 2), high.tail(n * 2), low.tail(n * 2),
        vwap.tail(n * 2), rsi.tail(n * 2), histogram.tail(n * 2), ts
    )

    return {
        "price":         round(latest, 2),
        "change":        round(daily_change, 2),
        "change_5d":     round(ret5, 2),
        "atr":           round(latest_atr, 2),
        "rsi":           round(latest_rsi, 1),
        "macd":          round(latest_macd, 4),
        "macd_signal":   round(latest_signal, 4),
        "macd_hist":     round(latest_hist, 4),
        "kdj_k":         round(latest_k, 1),
        "kdj_d":         round(latest_d, 1),
        "kdj_j":         round(latest_j, 1),
        "trend":         trend_label,
        "bull_pct":      round(bull_pct * 100, 1),
        "signals":       signals,
        "strategy":      strategy,
        "strategy_color": strategy_color,
        "entry":         round(entry_price, 2),
        "stop_loss":     stop_loss,
        "target":        target,
        "vwap":          round(latest_vwap, 2) if latest_vwap else None,
        "sr": {
            "support":    [round(v, 2) for v in sr_support],
            "resistance": [round(v, 2) for v in sr_resistance],
        },
        "trade_signals": trade_signals,
        "chart": {
            "candles":     candles,
            "volumes":     volumes,
            "macd":        series(macd_line),
            "macd_signal": series(signal_line),
            "macd_hist":   macd_hist_series(),
            "rsi":         series(rsi, decimals=1),
            "kdj_k":       series(kdj_k, decimals=1),
            "kdj_d":       series(kdj_d, decimals=1),
            "kdj_j":       series(kdj_j, decimals=1),
            "vwap":        series(vwap, decimals=2),
        },
        "ema": {
            "ema20":  round(latest_ema20,  2),
            "ema50":  round(latest_ema50,  2),
            "ema200": round(latest_ema200, 2),
        }
    }

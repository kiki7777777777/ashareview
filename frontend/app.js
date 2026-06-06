const API = "";
let macdChart = null, rsiChart = null, kdjChart = null;
let klineChart = null, volChart = null, candleSeries = null;
let currentInterval = "1d";
let liveTimer = null, liveSymbol = null, liveBarState = null;

// ─── Init ─────────────────────────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", () => {
  fetchSymbols();
  updateMarketStatus();
  setInterval(updateMarketStatus, 60000);
  document.getElementById("symbol-input").addEventListener("keydown", e => {
    if (e.key === "Enter") analyze();
  });
  document.getElementById("symbol-input").addEventListener("input", e => {
    e.target.value = e.target.value.replace(/\D/g, "").slice(0, 6);
  });
});

// ─── 市场状态（北京时间） ──────────────────────────────────────────────────────
function isMarketOpen() {
  const bj  = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Shanghai" }));
  const day = bj.getDay(), t = bj.getHours() * 60 + bj.getMinutes();
  if (day < 1 || day > 5) return false;
  return (t >= 570 && t <= 690) || (t >= 780 && t <= 900);
}

function updateMarketStatus() {
  const el   = document.getElementById("market-status");
  const open = isMarketOpen();
  el.className   = "conn-badge " + (open ? "conn-ok" : "conn-off");
  el.textContent = open ? "● 交易中" : "● 已收盘";
}

// ─── 快捷股票 ─────────────────────────────────────────────────────────────────
async function fetchSymbols() {
  try {
    const r = await fetch(`${API}/api/symbols`);
    const d = await r.json();
    const wrap = document.getElementById("quick-symbols");
    wrap.innerHTML = "";
    d.symbols.forEach(s => {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.innerHTML = `<span class="chip-code">${s.code}</span><span class="chip-name">${s.name}</span>`;
      chip.onclick = () => {
        document.getElementById("symbol-input").value = s.code;
        analyze();
      };
      wrap.appendChild(chip);
    });
  } catch { }
}

// ─── 切换周期 ─────────────────────────────────────────────────────────────────
function setInterval_(iv) {
  currentInterval = iv;
  document.querySelectorAll(".ivbtn").forEach(b =>
    b.classList.toggle("active", b.dataset.iv === iv)
  );
  if (document.getElementById("symbol-input").value.trim()) analyze();
}

// ─── 分析 ─────────────────────────────────────────────────────────────────────
async function analyze() {
  const sym = document.getElementById("symbol-input").value.trim();
  if (!sym) return;
  const btn = document.getElementById("analyze-btn");
  btn.disabled = true; btn.textContent = "分析中…";
  showLoading(sym);
  destroyCharts();
  try {
    const r = await fetch(`${API}/api/analyze/${sym}?interval=${currentInterval}`);
    if (!r.ok) { const e = await r.json(); showError(e.detail || "分析失败"); return; }
    renderDashboard(await r.json());
  } catch (e) {
    showError("无法连接后端，请双击 run.bat 启动: " + e.message);
  } finally {
    btn.disabled = false; btn.textContent = "分析";
  }
}

function showLoading(sym) {
  document.getElementById("main-content").innerHTML =
    `<div class="loading"><div class="spinner"></div><p>正在获取 ${sym} 数据…</p></div>`;
}
function showError(msg) {
  document.getElementById("main-content").innerHTML =
    `<div class="dashboard"><div class="error-box">❌ ${msg}</div></div>`;
}
function destroyCharts() {
  stopLive();
  if (macdChart)  { macdChart.destroy();  macdChart = null; }
  if (rsiChart)   { rsiChart.destroy();   rsiChart = null; }
  if (kdjChart)   { kdjChart.destroy();   kdjChart = null; }
  if (klineChart) { klineChart.remove();  klineChart = null; candleSeries = null; }
  if (volChart)   { volChart.remove();    volChart = null; }
}

// ─── 实时行情刷新 ─────────────────────────────────────────────────────────────
function startLive(symbol) {
  stopLive();
  liveSymbol   = symbol;
  liveBarState = null;
  tickLive();                              // 立即第一次
  liveTimer = setInterval(tickLive, 3000); // 之后每3秒
}

function stopLive() {
  if (liveTimer) { clearInterval(liveTimer); liveTimer = null; }
  const badge = document.getElementById("live-badge");
  if (badge) badge.style.display = "none";
}

async function tickLive() {
  if (!liveSymbol) return;
  try {
    const r = await fetch(`${API}/api/quote/${liveSymbol}`);
    if (!r.ok) return;
    const q = await r.json();
    if (!q.price || !q.date) return;

    // ── 更新顶部价格 ───────────────────────────────────────────────────
    const priceEl   = document.querySelector(".price-value");
    const changeEl  = document.querySelector(".price-change");
    const change2El = document.querySelectorAll(".price-change")[1];
    if (priceEl)   priceEl.textContent = `¥${q.price.toFixed(2)}`;
    if (changeEl) {
      const sign = q.pct_chg >= 0 ? "+" : "";
      changeEl.style.color = q.pct_chg >= 0 ? "var(--bull)" : "var(--bear)";
      changeEl.textContent = `${sign}${q.pct_chg}% 今日`;
    }

    // ── 更新 LIVE 角标 ─────────────────────────────────────────────────
    const badge = document.getElementById("live-badge");
    if (badge) {
      badge.style.display = "inline-flex";
      badge.textContent   = `● LIVE  ${q.time}`;
    }

    // ── 更新 K 线最后一根 ──────────────────────────────────────────────
    if (!candleSeries) return;

    if (currentInterval === "1d") {
      // 日线：直接用今日行情更新当天那根K线
      candleSeries.update({
        time:  q.date,
        open:  q.open,
        high:  q.high,
        low:   q.low,
        close: q.price,
      });
    } else {
      // 分时：每个周期内自行维护 OHLC，避免 high/low 用整天数据
      const period = currentInterval === "1h" ? 3600 : 300;
      const bjMs   = new Date(`${q.date}T${q.time}+08:00`).getTime();
      const barTs  = Math.floor(bjMs / 1000 / period) * period;

      if (!liveBarState || liveBarState.time !== barTs) {
        // 新周期开始：以当前价格作为开盘
        liveBarState = { time: barTs, open: q.price, high: q.price, low: q.price, close: q.price };
      } else {
        liveBarState.high  = Math.max(liveBarState.high, q.price);
        liveBarState.low   = Math.min(liveBarState.low,  q.price);
        liveBarState.close = q.price;
      }
      candleSeries.update(liveBarState);
    }
  } catch { /* 静默忽略 */ }
}

// ─── 渲染仪表盘 ───────────────────────────────────────────────────────────────
function renderDashboard(d) {
  const bull  = d.bull_pct, bear = 100 - bull;
  const rC    = bull > 55 ? "var(--bull)" : bull < 45 ? "var(--bear)" : "var(--neutral)";
  const rsiC  = d.rsi > 70 ? "var(--bear)" : d.rsi < 30 ? "var(--bull)" : "var(--accent)";
  const rsiLb = d.rsi > 70 ? "超买区" : d.rsi < 30 ? "超卖区" : "正常区";
  const histDir = d.macd_hist >= 0;
  const limitUp   = d.change >= d.limit_pct * 0.99;
  const limitDown = d.change <= -d.limit_pct * 0.99;

  // 今日涨跌颜色（A股 红涨绿跌）
  const changeC = d.change > 0 ? "var(--bull)" : d.change < 0 ? "var(--bear)" : "var(--text2)";
  const changeSign = d.change > 0 ? "+" : "";

  const sigNames = { macd: "MACD", rsi: "RSI", kdj: "KDJ", trend: "趋势", bollinger: "布林带", volume: "量能", momentum: "动量" };
  const sigsHtml = Object.entries(d.signals).map(([k, s]) => `
    <div class="signal-item ${s.value}">
      <span class="signal-name">${sigNames[k] || k}</span>
      <span class="signal-label">${s.label}</span>
      <span class="signal-dot ${s.value}"></span>
    </div>`).join("");

  const emaHtml = [
    { name: "EMA 20",  val: d.ema.ema20  },
    { name: "EMA 50",  val: d.ema.ema50  },
    { name: "EMA 200", val: d.ema.ema200 },
  ].map(e => `
    <div class="ema-item">
      <span class="ema-name">${e.name}</span>
      <span class="ema-value">¥${e.val.toFixed(2)}</span>
      <span class="ema-rel ${d.price > e.val ? "above" : "below"}">${d.price > e.val ? "价格上方" : "价格下方"}</span>
    </div>`).join("");

  const pe = d.info.pe_ratio ? parseFloat(d.info.pe_ratio).toFixed(1) : "-";
  const pb = d.info.pb_ratio ? parseFloat(d.info.pb_ratio).toFixed(2) : "-";
  const mv = d.info.total_mv ? fmtMV(d.info.total_mv) : "-";

  const ivLabel = { "1d": "日线", "1h": "1小时", "1min": "1分钟" }[d.interval];

  document.getElementById("main-content").innerHTML = `
    <div class="dashboard">

      <!-- Hero -->
      <div class="card card-hero">
        <div class="hero-name">
          <h1>${d.info.name || d.symbol}
            ${limitUp   ? '<span class="limit-badge limit-up">涨停</span>'   : ""}
            ${limitDown ? '<span class="limit-badge limit-down">跌停</span>' : ""}
          </h1>
          <div class="company-name">${d.symbol} · ${d.info.sector || "A股"} · 涨跌停 ±${d.limit_pct}%</div>
          <div class="hero-meta">
            <div class="meta-item"><span class="meta-label">总市值</span><span class="meta-value">${mv}</span></div>
            <div class="meta-item"><span class="meta-label">市盈率(动)</span><span class="meta-value">${pe}</span></div>
            <div class="meta-item"><span class="meta-label">市净率</span><span class="meta-value">${pb}</span></div>
            <div class="meta-item"><span class="meta-label">ATR (14)</span><span class="meta-value">¥${d.atr}</span></div>
          </div>
        </div>
        <div class="hero-price">
          <div style="display:flex;align-items:center;gap:10px">
            <div class="price-value">¥${d.price.toFixed(2)}</div>
            <span id="live-badge" class="live-badge" style="display:none">● LIVE</span>
          </div>
          <div class="price-change" style="color:${changeC}">${changeSign}${d.change}% 今日</div>
          <div class="price-change" style="color:${changeC};font-size:12px">${d.change_5d > 0 ? "+" : ""}${d.change_5d}% 5日</div>
          <div class="source-badge">数据: ${d.source}</div>
        </div>
      </div>

      <!-- Strategy -->
      <div class="card card-strategy">
        <div class="card-title">操作建议</div>
        <div class="strategy-label ${d.strategy_color}">${d.strategy}</div>
        <div class="strategy-row"><span>入场价</span><span class="entry">¥${d.entry}</span></div>
        <div class="strategy-row"><span>止损位</span><span class="stop">¥${d.stop_loss}</span></div>
        <div class="strategy-row"><span>目标位</span><span class="target">¥${d.target}</span></div>
      </div>

      <!-- Bull/Bear -->
      <div class="card card-ratio">
        <div class="card-title">多空比例</div>
        <div class="ratio-pct" style="color:${rC}">${bull.toFixed(1)}%</div>
        <div class="ratio-sub">多方强度</div>
        <div class="ratio-bar-wrap">
          <div class="ratio-bar-fill" style="width:${bull}%;background:linear-gradient(90deg,var(--bull) ${bull}%,var(--bear) ${bull}%)"></div>
        </div>
        <div class="ratio-labels">
          <span style="color:var(--bull)">多 ${bull.toFixed(1)}%</span>
          <span style="color:var(--bear)">空 ${bear.toFixed(1)}%</span>
        </div>
      </div>

      <!-- RSI -->
      <div class="card card-rsi">
        <div class="card-title">RSI (14)</div>
        <div class="rsi-value-text" style="color:${rsiC}">${d.rsi}</div>
        <div class="rsi-label" style="color:${rsiC}">${rsiLb}</div>
        <div class="rsi-slider">
          <div class="rsi-thumb" style="left:${d.rsi}%;background:${rsiC}"></div>
        </div>
        <div class="rsi-zones"><span>超卖 30</span><span>中性 50</span><span>超买 70</span></div>
      </div>

      <!-- MACD badge -->
      <div class="card card-macd-badge">
        <div class="card-title">MACD 动能</div>
        <div class="macd-badge-inner">
          <div class="macd-badge-label">MACD 柱状图</div>
          <div class="macd-badge-val" style="color:${histDir ? "var(--bull)" : "var(--bear)"}">
            ${histDir ? "▲" : "▼"} ${Math.abs(d.macd_hist).toFixed(4)}
          </div>
          <div class="macd-badge-sub">${histDir ? "多头动能" : "空头动能"}</div>
        </div>
        <div class="macd-badge-inner" style="margin-top:8px">
          <div class="macd-badge-label">趋势判断</div>
          <div class="macd-badge-val" style="font-size:20px;color:${
            d.trend.includes("上") ? "var(--bull)" : d.trend.includes("下") ? "var(--bear)" : "var(--neutral)"
          }">${d.trend}</div>
        </div>
      </div>

      <!-- K线图 -->
      <div class="card card-kline">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
          <span class="card-title" style="margin:0">K 线图 — ${ivLabel} · ${d.chart.candles.length} 根</span>
          <div class="interval-bar">
            <button class="ivbtn ${currentInterval==="1min"?"active":""}" data-iv="1min" onclick="setInterval_('1min')">5分钟</button>
            <button class="ivbtn ${currentInterval==="1h"?"active":""}"   data-iv="1h"   onclick="setInterval_('1h')">1小时</button>
            <button class="ivbtn ${currentInterval==="1d"?"active":""}"   data-iv="1d"   onclick="setInterval_('1d')">日线</button>
          </div>
        </div>
        <div id="kline-chart"></div>
        <div id="volume-chart"></div>
      </div>

      <!-- MACD 图 -->
      <div class="card card-macd-chart">
        <div class="card-title">MACD 柱状图 (12,26,9)</div>
        <div class="chart-container"><canvas id="macdCanvas"></canvas></div>
      </div>

      <!-- RSI 图 -->
      <div class="card card-rsi-chart">
        <div class="card-title">RSI 历史 (14)</div>
        <div class="chart-container"><canvas id="rsiCanvas"></canvas></div>
      </div>

      <!-- KDJ 图 -->
      <div class="card card-kdj-chart">
        <div class="card-title">KDJ (9,3,3) &nbsp;
          <span style="color:#58a6ff">K=${d.kdj_k}</span> &nbsp;
          <span style="color:#d29922">D=${d.kdj_d}</span> &nbsp;
          <span style="color:#f472b6">J=${d.kdj_j}</span>
        </div>
        <div class="chart-container"><canvas id="kdjCanvas"></canvas></div>
      </div>

      <!-- 买卖信号 -->
      <div class="card card-trade-signals">
        <div class="card-title" style="margin-bottom:8px">
          日内买卖信号
          ${d.vwap ? `<span style="float:right;font-weight:600;color:${d.price>=d.vwap?"var(--bull)":"var(--bear)"}">VWAP ¥${d.vwap} ${d.price>=d.vwap?"▲":"▼"}</span>` : ""}
        </div>
        <div class="sr-levels">
          ${d.sr.resistance.slice(0,3).reverse().map(v=>`<div class="sr-item resistance"><span>阻力</span><span>¥${v}</span><span class="sr-dist">${((v/d.price-1)*100).toFixed(1)}%</span></div>`).join("")}
          <div class="sr-item current"><span>当前价</span><span style="color:var(--accent);font-weight:700">¥${d.price}</span><span></span></div>
          ${d.sr.support.slice(-3).reverse().map(v=>`<div class="sr-item support"><span>支撑</span><span>¥${v}</span><span class="sr-dist">${((v/d.price-1)*100).toFixed(1)}%</span></div>`).join("")}
        </div>
        <div class="trade-signal-list" style="margin-top:10px">
          ${d.trade_signals.length === 0
            ? '<div style="color:var(--text2);font-size:13px;padding:8px">暂无信号</div>'
            : d.trade_signals.slice(-8).reverse().map(s => `
              <div class="tsig-item ${s.type}">
                <span class="tsig-dot ${s.type}">${s.type==="buy"?"▲":"▼"}</span>
                <span class="tsig-reason">${s.reason}</span>
                <span class="tsig-price">¥${s.price}</span>
                <span class="tsig-time">${fmtTime(s.time)}</span>
              </div>`).join("")}
        </div>
      </div>

      <!-- 指标信号 -->
      <div class="card card-signals">
        <div class="card-title">指标信号汇总</div>
        <div class="signal-list">${sigsHtml}</div>
      </div>

      <!-- 均线 -->
      <div class="card card-ema">
        <div class="card-title">均线分析</div>
        <div class="ema-list">${emaHtml}</div>
      </div>

    </div>`;

  buildKlineChart(d);
  buildSubCharts(d);
  // 开盘时间内自动启动实时刷新
  if (isMarketOpen()) startLive(d.symbol);
}

// ─── K线图（TradingView Lightweight Charts） ──────────────────────────────────
function buildKlineChart(d) {
  const opts = {
    layout: { background: { color: "#0f1923" }, textColor: "#8b949e" },
    grid:   { vertLines: { color: "#1a2332" }, horzLines: { color: "#1a2332" } },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    rightPriceScale: { borderColor: "#30363d" },
    timeScale: { borderColor: "#30363d", timeVisible: true },
  };

  klineChart = LightweightCharts.createChart(document.getElementById("kline-chart"), {
    ...opts, height: 340,
    width: document.getElementById("kline-chart").clientWidth,
  });

  // A股: 红涨绿跌
  candleSeries = klineChart.addCandlestickSeries({
    upColor:         "#dc3545",
    downColor:       "#28a745",
    borderUpColor:   "#dc3545",
    borderDownColor: "#28a745",
    wickUpColor:     "#dc3545",
    wickDownColor:   "#28a745",
  });
  candleSeries.setData(d.chart.candles);

  // VWAP
  if (d.chart.vwap && d.chart.vwap.length > 0) {
    const vwapS = klineChart.addLineSeries({
      color: "#f59e0b", lineWidth: 1.5, lineStyle: 2,
      title: "VWAP", priceLineVisible: false, lastValueVisible: true,
    });
    vwapS.setData(d.chart.vwap);
  }

  // 支撑/阻力
  d.sr.resistance.slice(0, 3).forEach(v =>
    candleSeries.createPriceLine({ price: v, color: "rgba(220,53,69,0.5)", lineWidth: 1, lineStyle: 1, axisLabelVisible: true, title: `R ¥${v}` })
  );
  d.sr.support.slice(-3).forEach(v =>
    candleSeries.createPriceLine({ price: v, color: "rgba(40,167,69,0.5)", lineWidth: 1, lineStyle: 1, axisLabelVisible: true, title: `S ¥${v}` })
  );

  // 买卖标记
  if (d.trade_signals && d.trade_signals.length > 0) {
    const markers = d.trade_signals.map(s => ({
      time:     s.time,
      position: s.type === "buy" ? "belowBar" : "aboveBar",
      color:    s.type === "buy" ? "#dc3545"  : "#28a745",
      shape:    s.type === "buy" ? "arrowUp"  : "arrowDown",
      text:     s.reason,
      size:     1,
    }));
    candleSeries.setMarkers(markers);
  }

  // 成交量
  volChart = LightweightCharts.createChart(document.getElementById("volume-chart"), {
    ...opts, height: 80,
    width: document.getElementById("volume-chart").clientWidth,
    rightPriceScale: { ...opts.rightPriceScale, scaleMargins: { top: 0.1, bottom: 0 } },
    timeScale: { visible: false },
  });
  const volS = volChart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "" });
  volS.priceScale().applyOptions({ scaleMargins: { top: 0.1, bottom: 0 } });
  volS.setData(d.chart.volumes);

  klineChart.timeScale().subscribeVisibleLogicalRangeChange(r => { if (r) volChart.timeScale().setVisibleLogicalRange(r); });
  volChart.timeScale().subscribeVisibleLogicalRangeChange(r =>   { if (r) klineChart.timeScale().setVisibleLogicalRange(r); });
  klineChart.timeScale().fitContent();

  window.addEventListener("resize", () => {
    klineChart.applyOptions({ width: document.getElementById("kline-chart").clientWidth });
    volChart.applyOptions({   width: document.getElementById("volume-chart").clientWidth });
  });
}

// ─── Chart.js MACD + RSI ──────────────────────────────────────────────────────
function buildSubCharts(d) {
  const fmtT  = t => typeof t === "number"
    ? new Date(t * 1000).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })
    : t.slice(5);
  const labels = d.chart.macd.map(p => fmtT(p.time));
  const base = {
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { color: "#8b949e", maxTicksLimit: 8, font: { size: 11 } }, grid: { color: "#1a2332" } },
      y: { ticks: { color: "#8b949e", font: { size: 11 } },                   grid: { color: "#1a2332" } },
    },
    animation: { duration: 400 },
    responsive: true,
    maintainAspectRatio: false,
  };

  macdChart = new Chart(document.getElementById("macdCanvas"), {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Hist",   data: d.chart.macd_hist.map(p => p.value), backgroundColor: d.chart.macd_hist.map(p => p.color), barPercentage: 0.9 },
        { label: "MACD",   data: d.chart.macd.map(p => p.value),   type: "line", borderColor: "#58a6ff", borderWidth: 1.5, pointRadius: 0, fill: false },
        { label: "Signal", data: d.chart.macd_signal.map(p => p.value), type: "line", borderColor: "#d29922", borderWidth: 1.5, pointRadius: 0, fill: false },
      ],
    },
    options: { ...base, plugins: { legend: { display: true, labels: { color: "#8b949e", boxWidth: 12, font: { size: 11 } } } } },
  });

  rsiChart = new Chart(document.getElementById("rsiCanvas"), {
    type: "line",
    data: {
      labels: d.chart.rsi.map(p => fmtT(p.time)),
      datasets: [{ data: d.chart.rsi.map(p => p.value), borderColor: "#a371f7", backgroundColor: "rgba(163,113,247,.07)", borderWidth: 2, pointRadius: 0, fill: true, tension: 0.3 }],
    },
    options: {
      ...base,
      scales: { ...base.scales, y: { ...base.scales.y, min: 0, max: 100, ticks: { color: "#8b949e", font: { size: 11 }, stepSize: 20 } } },
    },
  });

  const kdjLabels = d.chart.kdj_k.map(p => fmtT(p.time));
  kdjChart = new Chart(document.getElementById("kdjCanvas"), {
    type: "line",
    data: {
      labels: kdjLabels,
      datasets: [
        { label: "K", data: d.chart.kdj_k.map(p => p.value), borderColor: "#58a6ff", borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0.3 },
        { label: "D", data: d.chart.kdj_d.map(p => p.value), borderColor: "#d29922", borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0.3 },
        { label: "J", data: d.chart.kdj_j.map(p => p.value), borderColor: "#f472b6", borderWidth: 1,   pointRadius: 0, fill: false, tension: 0.3 },
      ],
    },
    options: {
      ...base,
      plugins: { legend: { display: true, labels: { color: "#8b949e", boxWidth: 12, font: { size: 11 } } } },
      scales: {
        x: base.scales.x,
        y: { ...base.scales.y, ticks: { color: "#8b949e", font: { size: 11 }, stepSize: 20 } },
      },
    },
  });
}

// ─── 工具函数 ─────────────────────────────────────────────────────────────────
function fmtTime(t) {
  if (typeof t === "number")
    return new Date(t * 1000).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  return t.slice(5);
}

function fmtMV(v) {
  const n = parseFloat(v);
  if (!n || isNaN(n)) return "-";
  if (n >= 1e12) return (n / 1e12).toFixed(2) + " 万亿";
  if (n >= 1e8)  return (n / 1e8).toFixed(2)  + " 亿";
  if (n >= 1e4)  return (n / 1e4).toFixed(2)  + " 万";
  return n.toFixed(0);
}

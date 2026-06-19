"""
data_fetcher.py
============================================================
数据拉取层: 多源 fallback
- 优先级 1: yfinance (本地/家庭宽带快且全)
- 优先级 2: Finnhub (云端 fallback, Yahoo 限流时用)
- 优先级 3: 最小 snapshot (两源都挂时, data_quality="low")
- FRED: 宏观背景 (GDP/CPI/利率) - 可选
============================================================
"""
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import yfinance as yf
import httpx
from schemas import StockSnapshot


def _setup_proxy():
    """国内环境必须设代理 (仅本地便利)"""
    is_cloud = bool(os.environ.get('PORT') or os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('RENDER'))

    if is_cloud:
        # 云端: 主动清掉指向 127.0.0.1/localhost 的 proxy (本地误配)
        for k in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
            v = os.environ.get(k, '')
            if v and ('127.0.0.1' in v or 'localhost' in v):
                print(f'[data_fetcher] 云端检测到本地 proxy {k}={v}, 主动清掉')
                os.environ.pop(k, None)
        return

    if not os.environ.get('HTTP_PROXY') and not os.environ.get('HTTPS_PROXY'):
        # 本地: 只在 7890 端口可达时才用
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.3)
            s.connect(('127.0.0.1', 7890))
            s.close()
            os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7890'
            os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'
        except Exception:
            pass  # 连不上就走直连


# ════════════════════════════════════════
# 主入口: fallback 链
# ════════════════════════════════════════

def fetch_stock_snapshot(ticker: str) -> StockSnapshot:
    """拉取单只股票的全量快照

    Fallback 链:
      1. yfinance (本地优先, 速度快数据全)
      2. Finnhub (云端 fallback, yfinance 被 Yahoo 限流时)
      3. 最小 snapshot (两源都挂时, data_quality="low")
    """
    _setup_proxy()
    ticker = ticker.upper()

    # 1) yfinance 优先
    snap = _try_yfinance(ticker)
    if snap is not None:
        return snap

    # 2) Finnhub fallback
    snap = _try_finnhub(ticker)
    if snap is not None:
        return snap

    # 3) 都失败 → 最小 snapshot
    print(f"[data_fetcher] yfinance + Finnhub 全部失败 {ticker}, 返回空 snapshot")
    return StockSnapshot(
        ticker=ticker,
        name=ticker,
        sector="数据拉取失败",
        industry="N/A",
        data_quality="low",
    )


# ════════════════════════════════════════
# 源 1: yfinance
# ════════════════════════════════════════

def _try_yfinance(ticker: str) -> Optional[StockSnapshot]:
    """yfinance 拉取, 失败返回 None"""
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception as e:
        print(f"[data_fetcher] yfinance 拉取 {ticker} 失败: {type(e).__name__}: {e}")
        return None

    if not info:
        print(f"[data_fetcher] yfinance 拉取 {ticker} 返回空 dict (可能被 Yahoo 限流)")
        return None

    # 检查是否有实际数据 (无效 ticker 时 yfinance 也返回 dict, 但全 None)
    # 如果 name/market_cap/current_price 全是 None, 视为拉取失败
    if not (info.get('longName') or info.get('shortName')) and not info.get('marketCap') and not (info.get('currentPrice') or info.get('regularMarketPrice')):
        print(f"[data_fetcher] yfinance {ticker} 拉取到空数据 (可能是无效 ticker)")
        return None

    def _f(key, default=None):
        v = info.get(key)
        if v is None or v == '':
            return default
        try:
            return float(v)
        except (ValueError, TypeError):
            return default

    def _pct(key, default=None):
        v = _f(key)
        if v is None:
            return default
        return round(v * 100, 2) if abs(v) < 100 else round(v, 2)

    market_cap = _f('marketCap')
    mcap_bil = round(market_cap / 1e9, 2) if market_cap else None

    return StockSnapshot(
        ticker=ticker,
        name=info.get('longName') or info.get('shortName') or ticker,
        sector=info.get('sector'),
        industry=info.get('industry'),
        market_cap=market_cap,
        current_price=_f('currentPrice') or _f('regularMarketPrice'),
        fifty_two_week_high=_f('fiftyTwoWeekHigh'),
        fifty_two_week_low=_f('fiftyTwoWeekLow'),
        fifty_day_ma=_f('fiftyDayAverage'),
        two_hundred_day_ma=_f('twoHundredDayAverage'),
        beta=_f('beta'),
        adv_30d_shares_mil=_f('averageDailyVolume10day', 0) / 1e6 if _f('averageDailyVolume10day') else None,
        mcap_usd_bil=mcap_bil,
        pe_trailing=_f('trailingPE'),
        pe_forward=_f('forwardPE'),
        pb=_f('priceToBook'),
        ps_trailing=_f('priceToSalesTrailing12Months'),
        ev_to_ebitda=_f('enterpriseToEbitda'),
        ev_to_revenue=_f('enterpriseToRevenue'),
        gross_margin=_pct('grossMargins'),
        operating_margin=_pct('operatingMargins'),
        profit_margin=_pct('profitMargins'),
        roe=_pct('returnOnEquity'),
        roa=_pct('returnOnAssets'),
        revenue_growth_yoy=_pct('revenueGrowth'),
        earnings_growth_yoy=_pct('earningsGrowth'),
        current_ratio=_f('currentRatio'),
        quick_ratio=_f('quickRatio'),
        debt_to_equity=_f('debtToEquity'),
        total_cash_usd_bil=round(_f('totalCash', 0) / 1e9, 2) if _f('totalCash') else None,
        total_debt_usd_bil=round(_f('totalDebt', 0) / 1e9, 2) if _f('totalDebt') else None,
        free_cashflow_usd_bil=round(_f('freeCashflow', 0) / 1e9, 2) if _f('freeCashflow') else None,
        operating_cashflow_usd_bil=round(_f('operatingCashflow', 0) / 1e9, 2) if _f('operatingCashflow') else None,
        target_mean_price=_f('targetMeanPrice'),
        recommendation_mean=_f('recommendationMean'),
        held_percent_institutions=_pct('heldPercentInstitutions'),
        held_percent_insiders=_pct('heldPercentInsiders'),
        short_percent_of_float=_pct('shortPercentOfFloat'),
        description=info.get('description'),
        business_summary=info.get('longBusinessSummary'),
        data_quality="high",
    )


# ════════════════════════════════════════
# 源 2: Finnhub
# ════════════════════════════════════════

def _try_finnhub(ticker: str) -> Optional[StockSnapshot]:
    """Finnhub fallback 拉取, 失败返回 None

    调用 4 个端点 (1 个 ticker 共 4 calls, free tier 60 calls/min 够用):
      - /quote          → 当前价
      - /stock/profile2 → 名称/市值/行业
      - /stock/metric   → PE/PB/Beta/margins/ROE 等全量指标
      - /company-news   → 最近 7 天新闻 (catalysts 用)
    """
    api_key = os.environ.get('FINNHUB_API_KEY')
    if not api_key:
        return None  # 没配 key 就静默跳过, 让上层走最小 snapshot

    import httpx
    base = "https://finnhub.io/api/v1"
    params = {"token": api_key}
    timeout = 15.0

    try:
        with httpx.Client(timeout=timeout) as c:
            # 1) Quote
            r_quote = c.get(f"{base}/quote", params={**params, "symbol": ticker})
            if r_quote.status_code != 200:
                print(f"[data_fetcher] Finnhub /quote {ticker} {r_quote.status_code}")
                return None
            quote = r_quote.json()
            if not quote or quote.get("c") is None or quote.get("c") == 0:
                print(f"[data_fetcher] Finnhub /quote {ticker} 返回空/0 价")
                return None

            # 2) Profile
            r_prof = c.get(f"{base}/stock/profile2", params={**params, "symbol": ticker})
            if r_prof.status_code != 200:
                print(f"[data_fetcher] Finnhub /profile2 {ticker} {r_prof.status_code}")
                return None
            prof = r_prof.json() or {}

            # 3) Metric (optional, 失败不阻塞)
            metric = {}
            r_metric = c.get(f"{base}/stock/metric", params={**params, "symbol": ticker, "metric": "all"})
            if r_metric.status_code == 200:
                m = r_metric.json()
                metric = (m or {}).get("metric", {}) or {}

            # 4) News (optional, 失败不阻塞)
            # 不存 news 到 StockSnapshot, 但打 log 方便调试
            to_date = datetime.now().strftime("%Y-%m-%d")
            from_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            try:
                r_news = c.get(f"{base}/company-news", params={**params, "symbol": ticker, "from": from_date, "to": to_date})
                if r_news.status_code == 200:
                    news = r_news.json() or []
                    print(f"[data_fetcher] Finnhub {ticker}: 拉到 {len(news)} 条新闻")
            except Exception:
                pass

    except Exception as e:
        print(f"[data_fetcher] Finnhub 拉取 {ticker} 异常: {type(e).__name__}: {e}")
        return None

    # ── 解析 ──
    def _f(v, default=None):
        if v is None or v == '' or v == 0:
            return default
        try:
            return float(v)
        except (ValueError, TypeError):
            return default

    # Finnhub 的 margin/ROE 等指标已经是百分数 (e.g. 45.0 = 45%), 不需要 *100
    def _pct(v, default=None):
        x = _f(v)
        if x is None:
            return default
        return round(x, 2)

    # 市值: profile2 给的是 millions, 转 raw
    mcap_mil = _f(prof.get("marketCapitalization"))
    market_cap = mcap_mil * 1e6 if mcap_mil else None
    mcap_bil = round(mcap_mil / 1e3, 2) if mcap_mil else None

    # 板块: Finnhub 只有 finnhubIndustry, 没有 sector
    industry = prof.get("finnhubIndustry")

    # shares outstanding (millions → raw)
    share_out_mil = _f(prof.get("shareOutstanding"))
    share_out = share_out_mil * 1e6 if share_out_mil else None

    # per-share metrics → 美元 billions (totalCash/totalDebt/FCF/OCF)
    def _per_share_to_bil(per_share):
        v = _f(per_share)
        if v is None or share_out is None:
            return None
        return round(v * share_out / 1e9, 2)

    print(f"[data_fetcher] Finnhub {ticker} OK: price={quote.get('c')}, mcap_bil={mcap_bil}, industry={industry}")

    return StockSnapshot(
        ticker=ticker,
        name=prof.get("name") or ticker,
        sector=industry,  # Finnhub 没 sector, 用 industry 顶上
        industry=industry,
        market_cap=market_cap,
        current_price=_f(quote.get("c")),
        fifty_two_week_high=_f(metric.get("52WeekHigh")),
        fifty_two_week_low=_f(metric.get("52WeekLow")),
        fifty_day_ma=_f(metric.get("priceAvg50Day")),
        two_hundred_day_ma=_f(metric.get("priceAvg200Day")),
        beta=_f(metric.get("beta")),
        adv_30d_shares_mil=_f(metric.get("10DayAverageTradingVolume")),
        mcap_usd_bil=mcap_bil,
        pe_trailing=_f(metric.get("peBasicExtraTTM")),
        pe_forward=_f(metric.get("peForwardAnnual") or metric.get("forwardPE")),
        pb=_f(metric.get("pbAnnual") or metric.get("pbQuarterly")),
        ps_trailing=_f(metric.get("psAnnual") or metric.get("psTTM")),
        ev_to_ebitda=_f(metric.get("evToEbitdaAnnual") or metric.get("evEbitdaTTM")),
        ev_to_revenue=_f(metric.get("evToRevenueAnnual") or metric.get("evRevenueTTM")),
        gross_margin=_pct(metric.get("grossMarginAnnual") or metric.get("grossMarginTTM")),
        operating_margin=_pct(metric.get("operatingMarginAnnual") or metric.get("operatingMarginTTM")),
        profit_margin=_pct(metric.get("netMarginAnnual") or metric.get("netProfitMarginTTM")),
        roe=_pct(metric.get("roeAnnual") or metric.get("roeTTM")),
        roa=_pct(metric.get("roaAnnual") or metric.get("roaTTM")),
        revenue_growth_yoy=_pct(metric.get("revenueGrowthAnnual") or metric.get("revenueGrowthTTMYoy")),
        earnings_growth_yoy=_pct(metric.get("epsGrowthAnnual") or metric.get("epsGrowthTTMYoy")),
        current_ratio=_f(metric.get("currentRatioAnnual") or metric.get("currentRatioQuarterly")),
        quick_ratio=_f(metric.get("quickRatioAnnual") or metric.get("quickRatioQuarterly")),
        debt_to_equity=_f(metric.get("debtToEquityAnnual") or metric.get("debtToEquity")),
        total_cash_usd_bil=_per_share_to_bil(metric.get("totalCashPerShareAnnual")),
        total_debt_usd_bil=_per_share_to_bil(metric.get("totalDebtPerShareAnnual")),
        free_cashflow_usd_bil=_per_share_to_bil(metric.get("freeCashFlowPerShareTTM")),
        operating_cashflow_usd_bil=_per_share_to_bil(metric.get("operatingCashFlowPerShareTTM")),
        target_mean_price=_f(metric.get("targetPrice") or metric.get("priceTargetMean")),
        recommendation_mean=None,  # Finnhub metric 没这字段, 需调 /recommendation
        held_percent_institutions=_pct(metric.get("institutionalOwnershipPercent")),
        held_percent_insiders=None,  # 需调 /ownership
        short_percent_of_float=None,  # 需调 /short-interest
        description=prof.get("weburl"),
        business_summary=None,  # Finnhub profile2 没 summary
        data_quality="high",
    )


# ════════════════════════════════════════
# 宏观指标 (FRED, 独立链路)
# ════════════════════════════════════════

def fetch_macro_indicators() -> Dict[str, Any]:
    """拉取宏观指标 (FRED)"""
    _setup_proxy()
    fred_key = os.environ.get('FRED_API_KEY')
    if not fred_key:
        return {"status": "no_fred_key", "indicators": {}}

    try:
        from fredapi import Fred
        fred = Fred(api_key=fred_key)
        indicators = {
            "GDP_growth": _safe_fred(fred, 'GDPC1'),
            "CPI": _safe_fred(fred, 'CPIAUCSL'),
            "unemployment": _safe_fred(fred, 'UNRATE'),
            "10y_yield": _safe_fred(fred, 'DGS10'),
            "fed_funds": _safe_fred(fred, 'DFF'),
        }
        return {"status": "ok", "indicators": indicators}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# =============================================================
# Phase C: 历史价拉取 (Finnhub candle API, cloud 友好)
# =============================================================

def fetch_history_prices(symbol: str, days: int = 200) -> Optional[Dict[str, Any]]:
    """拉历史日线价 (Phase C: 板块轮动 / 个股相对表现)

    优先 Finnhub (cloud 友好), yfinance fallback (本地友好)
    返回: {c: [close...], h, l, o, t: [timestamp...], v: [volume...], s: 'ok'}

    注意: 不缓存 (拉一次几十 KB, 不重)
    """
    _setup_proxy()
    import time as _t

    # 1) Finnhub 优先 (60 calls/min 免费额度)
    api_key = os.environ.get('FINNHUB_API_KEY')
    if api_key:
        try:
            to_ts = int(_t.time())
            from_ts = to_ts - days * 24 * 3600
            url = f"https://finnhub.io/api/v1/stock/candle?symbol={symbol.upper()}&resolution=D&from={from_ts}&to={to_ts}&token={api_key}"
            with httpx.Client(timeout=10.0) as c:
                r = c.get(url)
            if r.status_code == 200:
                data = r.json()
                if data.get('s') == 'ok' and data.get('c'):
                    return data
                # s = "no_data" 表示没有
        except Exception as e:
            print(f"[history] Finnhub {symbol} 失败: {e}")

    # 2) yfinance fallback
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        h = t.history(period=f"{days}d")
        if h is not None and len(h) > 0:
            import pandas as pd
            return {
                "c": h['Close'].tolist(),
                "h": h['High'].tolist(),
                "l": h['Low'].tolist(),
                "o": h['Open'].tolist(),
                "v": h['Volume'].tolist(),
                "t": [int(d.timestamp()) for d in h.index],
                "s": "ok",
            }
    except Exception as e:
        print(f"[history] yfinance {symbol} 失败: {e}")

    return None


# =============================================================
# Market Sentiment (CNN Fear & Greed Index) - Phase A
# =============================================================
import time as _time

_SENTIMENT_CACHE = {"data": None, "ts": 0}
_SENTIMENT_TTL = 600  # 10 分钟缓存


def fetch_market_sentiment(force: bool = False) -> Dict[str, Any]:
    """拉取 CNN Fear & Greed Index (0-100)
    - 免费 API, 不用 key
    - 10 分钟内存缓存
    - 失败时返回 score=None (前端用规则推断降级)
    """
    if not force and _SENTIMENT_CACHE["data"] and (_time.time() - _SENTIMENT_CACHE["ts"]) < _SENTIMENT_TTL:
        return _SENTIMENT_CACHE["data"]

    _setup_proxy()
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.cnn.com/",
    }
    try:
        with httpx.Client(timeout=10.0) as c:
            r = c.get(url, headers=headers)
        if r.status_code != 200:
            print(f"[sentiment] CNN API HTTP {r.status_code}: {r.text[:200]}")
            return {"score": None, "source": "fallback", "error": f"HTTP {r.status_code}"}
        data = r.json()
        fg = data.get("fear_and_greed", {})
        result = {
            "score": int(fg.get("score")) if fg.get("score") is not None else None,
            "label": fg.get("rating"),
            "previous_close": int(fg.get("previous_close")) if fg.get("previous_close") is not None else None,
            "previous_1_week": int(fg.get("previous_1_week")) if fg.get("previous_1_week") is not None else None,
            "source": "cnn_api",
            "fetched_at": _time.time(),
        }
        _SENTIMENT_CACHE["data"] = result
        _SENTIMENT_CACHE["ts"] = _time.time()
        return result
    except Exception as e:
        print(f"[sentiment] CNN API 拉取失败: {type(e).__name__}: {e}")
        return {"score": None, "source": "fallback", "error": str(e)}


def _safe_fred(fred, series_id):
    try:
        data = fred.get_series(series_id)
        if data is not None and len(data) > 0:
            return float(data.iloc[-1])
    except Exception:
        return None
    return None

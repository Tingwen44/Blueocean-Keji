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

# ════════════════════════════════════════
# Ticker 别名映射 (用户友好 → 交易所代码)
# ════════════════════════════════════════
TICKER_ALIASES = {
    # 韩国
    "HYNIX": "000660.KS",
    "SK_HYNIX": "000660.KS",
    "SKHYNIX": "000660.KS",
    "SAMSUNG": "005930.KS",
    "KAKAO": "035720.KS",
    # 港股
    "TENCENT": "0700.HK",
    "ALI": "9988.HK",  # 阿里巴巴
    "MEITUAN": "3690.HK",
    "JD": "9618.HK",
    "BABA": "9988.HK",
    # 美股双类别
    "GOOG": "GOOGL",  # 选有 vote 的 A 类
    "BRK": "BRK.B",  # 伯克希尔 B 类
    "BRK_B": "BRK.B",
    # 常见错拼
    "BERKSHIRE": "BRK.B",
    "TESLA": "TSLA",  # 同
    "APPLE": "AAPL",
    "MICROSOFT": "MSFT",
    "NVIDIA": "NVDA",
}


def resolve_ticker(ticker: str) -> str:
    """把用户友好 ticker 转成交易所代码, 没找到返原 ticker"""
    if not ticker:
        return ticker
    t = ticker.strip().upper()
    return TICKER_ALIASES.get(t, t)


def _try_yfinance_with_timeout(ticker: str, timeout: float = 8.0) -> Optional[StockSnapshot]:
    """yfinance 带超时 (避免 datacenter IP 被 Yahoo 限流时无限挂起)

    ThreadPoolExecutor 跑同步调用, 主线程 timeout 强制返回 None
    """
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_try_yfinance, ticker)
        try:
            return fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            print(f"[data_fetcher] yfinance {ticker} 超时 ({timeout}s), 跳过")
            return None
        except Exception as e:
            print(f"[data_fetcher] yfinance {ticker} 异常: {type(e).__name__}: {e}")
            return None


def fetch_stock_snapshot(ticker: str) -> StockSnapshot:
    """拉取单只股票的全量快照

    Fallback 链:
      1. yfinance (本地优先, 速度快数据全) - 8s 超时
      2. Finnhub (云端 fallback, yfinance 被 Yahoo 限流时)
      3. 最小 snapshot (两源都挂时, data_quality="low")

    支持 ticker 别名 (HYNIX → 000660.KS), 见 TICKER_ALIASES
    """
    _setup_proxy()
    ticker = resolve_ticker(ticker)

    # 1) yfinance 优先 (带超时)
    snap = _try_yfinance_with_timeout(ticker, timeout=8.0)
    if snap is not None:
        return snap

    # 2) Finnhub fallback (已有 15s 超时)
    snap = _try_finnhub(ticker)
    if snap is not None:
        return snap

    # 3) 都失败 → 最小 snapshot + 友好提示
    print(f"[data_fetcher] yfinance + Finnhub 全部失败 {ticker}, 返回空 snapshot")
    return StockSnapshot(
        ticker=ticker,
        name=ticker,
        sector="数据拉取失败 (yfinance 超时 + Finnhub 401, 需配置真实 FINNHUB_API_KEY)",
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
            if r_quote.status_code == 401:
                print(f"[data_fetcher] Finnhub /quote {ticker} 401 Unauthorized — API key 失效, 需重配")
                return None
            if r_quote.status_code == 403:
                print(f"[data_fetcher] Finnhub /quote {ticker} 403 Forbidden — free tier 不支持此 ticker (常见: 韩股 .KS / 港股 .HK)")
                return None
            if r_quote.status_code != 200:
                print(f"[data_fetcher] Finnhub /quote {ticker} {r_quote.status_code}: {r_quote.text[:200]}")
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

    三源 fallback:
      1. Tiingo daily/prices (优先, 支持美股 + ETF, Railway 友好)
      2. Finnhub candle (美股个股, 不支持 ETF)
      3. yfinance (本地, 带 6s 超时)

    返回: {c: [close...], h, l, o, t: [timestamp...], v: [volume...], s: 'ok'}
    """
    _setup_proxy()
    import time as _t

    # 1) Tiingo 优先 (支持美股 + ETF, free 500 requests/day, Railway 友好)
    tiingo_key = os.environ.get('TIINGO_API_KEY')
    if tiingo_key:
        try:
            to_ts = int(_t.time())
            from_ts = to_ts - days * 24 * 3600
            from_date = _t.strftime('%Y-%m-%d', _t.gmtime(from_ts))
            to_date = _t.strftime('%Y-%m-%d', _t.gmtime(to_ts))
            url = f"https://api.tiingo.com/tiingo/daily/{symbol.upper()}/prices?token={tiingo_key}&startDate={from_date}&endDate={to_date}&format=json"
            with httpx.Client(timeout=10.0) as c:
                r = c.get(url)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
                    return {
                        "c": [d['close'] for d in data],
                        "h": [d['high'] for d in data],
                        "l": [d['low'] for d in data],
                        "o": [d['open'] for d in data],
                        "v": [d['volume'] for d in data],
                        "t": [int(_t.mktime(_t.strptime(d['date'][:10], '%Y-%m-%d'))) for d in data],
                        "s": "ok",
                    }
                # Tiingo 返 [] 表示该 ticker 不支持 (常见: 韩股港股)
            elif r.status_code == 404:
                print(f"[history] Tiingo {symbol} 404 Not found (免费档不支持此 ticker)")
        except Exception as e:
            print(f"[history] Tiingo {symbol} 失败: {type(e).__name__}: {e}")

    # 2) Finnhub candle (美股个股, 不支持 ETF)
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
        except Exception as e:
            print(f"[history] Finnhub {symbol} 失败: {e}")

    # 3) yfinance fallback (带 6s 超时)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_yfinance_history_sync, symbol, days)
        try:
            return fut.result(timeout=6.0)
        except concurrent.futures.TimeoutError:
            print(f"[history] yfinance {symbol} 超时 (6s), 跳过")
            return None
        except Exception as e:
            print(f"[history] yfinance {symbol} 异常: {type(e).__name__}: {e}")
            return None


def _yfinance_history_sync(symbol: str, days: int):
    """yfinance 同步拉历史 (内部函数, 用 ThreadPoolExecutor 包装超时)"""
    import yfinance as yf
    t = yf.Ticker(symbol)
    h = t.history(period=f"{days}d")
    if h is not None and len(h) > 0:
        return {
            "c": h['Close'].tolist(),
            "h": h['High'].tolist(),
            "l": h['Low'].tolist(),
            "o": h['Open'].tolist(),
            "v": h['Volume'].tolist(),
            "t": [int(d.timestamp()) for d in h.index],
            "s": "ok",
        }
    return None


# =============================================================
# Market Sentiment (CNN Fear & Greed Index) - Phase A
# =============================================================
import time as _time

_SENTIMENT_CACHE = {"data": None, "ts": 0}
_SENTIMENT_TTL = 600  # 10 分钟缓存


# =============================================================
# Phase E.1: 估值精细化 (行业 peers + 历史 PE)
# =============================================================

INDUSTRY_PEERS = {
    "Technology": ["NVDA", "AMD", "INTC", "MU", "AVGO", "TXN", "MRVL", "AMAT", "QCOM"],
    "Communication Services": ["GOOGL", "META", "NFLX", "T", "VZ"],
    "Consumer Cyclical": ["AMZN", "TSLA", "HD", "MCD", "NKE"],
    "Consumer Defensive": ["PG", "KO", "PEP", "WMT", "COST"],
    "Healthcare": ["LLY", "JNJ", "PFE", "MRK", "ABBV", "TMO", "UNH"],
    "Financial Services": ["JPM", "BAC", "WFC", "GS", "MS", "V", "MA"],
    "Industrials": ["HON", "UNP", "CAT", "BA", "GE"],
    "Energy": ["XOM", "CVX", "COP", "SLB"],
    "Utilities": ["NEE", "DUK", "SO"],
    "Real Estate": ["PLD", "AMT", "EQIX"],
    "Basic Materials": ["LIN", "FCX", "NEM"],
}


def fetch_peer_metrics(ticker: str) -> Optional[Dict[str, Any]]:
    """拉单个同业的 PE + marketCap (Phase E.1)

    用 Finnhub /stock/profile2 (marketCap) + /stock/metric (peNormalized)
    返回: {ticker, pe_normalized, market_cap, name}
    """
    api_key = os.environ.get('FINNHUB_API_KEY')
    if not api_key:
        return None
    try:
        with httpx.Client(timeout=10.0) as c:
            base = "https://finnhub.io/api/v1"
            r_prof = c.get(f"{base}/stock/profile2", params={"symbol": ticker, "token": api_key})
            if r_prof.status_code != 200:
                return None
            prof = r_prof.json() or {}
            mc = prof.get('marketCapitalization', 0) * 1_000_000  # Finnhub 单位是 million USD

            r_met = c.get(f"{base}/stock/metric", params={"symbol": ticker, "token": api_key, "metric": "all"})
            pe = None
            if r_met.status_code == 200:
                m = r_met.json() or {}
                metric = (m or {}).get('metric', {}) or {}
                pe = metric.get('peNormalizedAnnual') or metric.get('peBasicExtraTTM')
                if pe is not None:
                    try: pe = float(pe)
                    except: pe = None

            if pe is None or pe <= 0:
                return None
            return {
                "ticker": ticker,
                "name": prof.get('name', ticker),
                "pe_normalized": round(pe, 2),
                "market_cap": float(mc) if mc else 0,
            }
    except Exception as e:
        print(f"[peer] Finnhub {ticker} 失败: {e}")
        return None


def compute_historical_pe_range(symbol: str, current_eps: Optional[float]) -> Dict[str, Any]:
    """拉 5y 历史价 + 用当前 EPS 估算历史 PE 区间

    注意: 这是简化版 (用 current EPS 算历史所有 PE), 精确版需要 historical EPS
    返回: {min, max, current_percentile, points}
    """
    if current_eps is None or current_eps <= 0:
        return {"available": False, "reason": "EPS <= 0, 无法算 PE"}
    hist = fetch_history_prices(symbol, days=1825)  # 5y
    if not hist or not hist.get('c'):
        return {"available": False, "reason": "无历史价数据"}
    prices = hist['c']
    pe_values = [round(p / current_eps, 2) for p in prices if p > 0 and current_eps > 0]
    if len(pe_values) < 60:
        return {"available": False, "reason": f"数据点不足 ({len(pe_values)})"}
    pe_min = min(pe_values)
    pe_max = max(pe_values)
    pe_now = prices[-1] / current_eps
    sorted_pe = sorted(pe_values)
    idx = sum(1 for p in sorted_pe if p <= pe_now)
    percentile = round(idx / len(sorted_pe) * 100, 1)
    return {
        "available": True,
        "min": round(pe_min, 2),
        "max": round(pe_max, 2),
        "current": round(pe_now, 2),
        "current_percentile": percentile,
        "points": len(pe_values),
        "years": round(len(pe_values) / 252, 1),
    }


def fetch_market_sentiment(force: bool = False) -> Dict[str, Any]:
    """Phase 移除于 2026-06-19 (用户判断市场情绪对个股无参考价值)

    历史实现: 拉 CNN Fear & Greed Index, 10min 缓存
    现在直接返 None, 调用方需自己处理
    """
    return {"score": None, "source": "removed", "error": "Phase removed"}


def _safe_fred(fred, series_id):
    try:
        data = fred.get_series(series_id)
        if data is not None and len(data) > 0:
            return float(data.iloc[-1])
    except Exception:
        return None
    return None

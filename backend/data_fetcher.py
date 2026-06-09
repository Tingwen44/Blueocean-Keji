"""
data_fetcher.py
============================================================
数据拉取层: yfinance + FRED
- yfinance: 美股/港股 价格/财务/估值
- FRED: 宏观背景 (GDP/CPI/利率) - 可选
============================================================
"""
import os
import yfinance as yf
from typing import Optional, Dict, Any
from datetime import datetime
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


def fetch_stock_snapshot(ticker: str) -> StockSnapshot:
    """拉取单只股票的全量快照

    失败时不抛异常, 返回 data_quality="low" 的最小 snapshot (其他字段 None)
    """
    _setup_proxy()
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception as e:
        print(f"[data_fetcher] yfinance 拉取 {ticker} 失败: {type(e).__name__}: {e}")
        return StockSnapshot(
            ticker=ticker.upper(),
            name=ticker.upper(),
            sector="数据拉取失败",
            industry="N/A",
            data_quality="low",
        )

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

    # 市值
    market_cap = _f('marketCap')
    mcap_bil = round(market_cap / 1e9, 2) if market_cap else None

    snapshot = StockSnapshot(
        ticker=ticker.upper(),
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
    return snapshot


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
        return {"status": "error", "error": str(e), "indicators": {}}


def _safe_fred(fred, series_id):
    try:
        data = fred.get_series(series_id)
        if data is not None and len(data) > 0:
            return float(data.iloc[-1])
    except Exception:
        return None
    return None

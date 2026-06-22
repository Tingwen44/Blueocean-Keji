"""
scoring.py
============================================================
8 步评分算法 (MPEVL + 5 大方法量化部分)
- Step 2: 4 维基本面
- Step 5: 日历+事件
- Step 7: 见顶/见底信号
- Step 8 (综合分): MPEVL 5 维加权
============================================================
"""
import os
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from schemas import (
    StockSnapshot, FundamentalScan,
    TopBottomBlock, TopBottomSignal, OnePagerReport
)


# ────────────────────────────────────────
# Step 2: 4 维基本面扫描
# ────────────────────────────────────────
def scan_fundamental(snap: StockSnapshot) -> FundamentalScan:
    """4 维基本面信号 (从 yfinance 硬数据推导)"""

    # 1. 盈利维度
    earnings_signal = "neutral"
    earnings_detail = ""
    margin = snap.profit_margin
    if margin is not None:
        if margin > 15:
            earnings_signal = "bullish"
            earnings_detail = f"净利率 {margin:.1f}% (高利润护城河)"
        elif margin > 5:
            earnings_signal = "neutral"
            earnings_detail = f"净利率 {margin:.1f}% (中等盈利)"
        elif margin > 0:
            earnings_signal = "bearish"
            earnings_detail = f"净利率 {margin:.1f}% (微利)"
        else:
            earnings_signal = "bearish"
            earnings_detail = f"净利率 {margin:.1f}% (亏损)"

    # 2. 增长维度
    growth_signal = "neutral"
    growth_detail = ""
    growth = snap.revenue_growth_yoy
    if growth is not None:
        if growth > 20:
            growth_signal = "bullish"
            growth_detail = f"营收 YoY +{growth:.1f}% (高增)"
        elif growth > 5:
            growth_signal = "neutral"
            growth_detail = f"营收 YoY +{growth:.1f}% (稳健)"
        elif growth > 0:
            growth_signal = "bearish"
            growth_detail = f"营收 YoY +{growth:.1f}% (放缓)"
        else:
            growth_signal = "bearish"
            growth_detail = f"营收 YoY {growth:.1f}% (下滑)"

    # 3. 财务健康
    financial_signal = "neutral"
    financial_detail = ""
    cr = snap.current_ratio
    dte = snap.debt_to_equity
    if cr is not None and dte is not None:
        if cr > 2 and dte < 50:
            financial_signal = "bullish"
            financial_detail = f"流动比率 {cr:.2f}, D/E {dte:.0f}% (强健)"
        elif cr > 1.5 and dte < 100:
            financial_signal = "neutral"
            financial_detail = f"流动比率 {cr:.2f}, D/E {dte:.0f}% (健康)"
        elif cr > 1:
            financial_signal = "bearish"
            financial_detail = f"流动比率 {cr:.2f}, D/E {dte:.0f}% (偏紧)"
        else:
            financial_signal = "bearish"
            financial_detail = f"流动比率 {cr:.2f}, D/E {dte:.0f}% (危险区)"

    # 4. 估值维度
    valuation_signal = "neutral"
    valuation_detail = ""
    pe = snap.pe_forward
    if pe is not None:
        if pe > 0:
            if pe < 15:
                valuation_signal = "bullish"
                valuation_detail = f"PE Fwd {pe:.1f}x (便宜)"
            elif pe < 25:
                valuation_signal = "neutral"
                valuation_detail = f"PE Fwd {pe:.1f}x (合理)"
            elif pe < 40:
                valuation_signal = "bearish"
                valuation_detail = f"PE Fwd {pe:.1f}x (贵)"
            else:
                valuation_signal = "bearish"
                valuation_detail = f"PE Fwd {pe:.1f}x (极贵)"
        else:
            valuation_signal = "bearish"
            valuation_detail = f"PE Fwd {pe:.1f}x (亏损)"

    # 转化为 0-10 分数
    sig_to_score = {"bullish": 8, "neutral": 5, "bearish": 3}
    e_score = sig_to_score[earnings_signal]
    g_score = sig_to_score[growth_signal]
    f_score = sig_to_score[financial_signal]
    v_score = sig_to_score[valuation_signal]
    fund_score = round((e_score + g_score + f_score + v_score) / 4, 2)

    return FundamentalScan(
        ticker=snap.ticker,
        earnings_signal=earnings_signal,
        growth_signal=growth_signal,
        financial_signal=financial_signal,
        valuation_signal=valuation_signal,
        earnings_detail=earnings_detail,
        growth_detail=growth_detail,
        financial_detail=financial_detail,
        valuation_detail=valuation_detail,
        earnings_score=e_score,
        growth_score=g_score,
        financial_score=f_score,
        valuation_score=v_score,
        fund_score=fund_score,
    )


# ────────────────────────────────────────
# Step 5: 日历+事件 (Phase 移除, 用户判断价值不大)
# ────────────────────────────────────────
# (Step 5 删除于 2026-06-19 - 见 git log)


# ────────────────────────────────────────
# Step 7: 见顶/见底信号
# ────────────────────────────────────────
def scan_top_bottom_signals(snap: StockSnapshot) -> TopBottomBlock:
    """可量化的见顶/见底信号检测 (不依赖 LLM)

    每个信号标注 signal_type:
      - "top"     = 见顶警告 (触发时是减仓信号)
      - "bottom"  = 见底信号 (触发时是加仓信号)
      - "neutral" = 中性 (双向)
    """
    signals: List[TopBottomSignal] = []

    # 1. 标普 PE 分位 (用个股 PE Fwd 近似)
    pe = snap.pe_forward or 0
    if pe > 40:
        signals.append(TopBottomSignal(
            name="PE Fwd 高位",
            signal_type="top",  # ← 触发 = 见顶警告
            triggered=True,
            value=f"{pe:.1f}x",
            note="PE > 40, 估值在历史高位"
        ))
    elif 0 < pe < 10:
        signals.append(TopBottomSignal(
            name="PE Fwd 低位",
            signal_type="bottom",  # ← 触发 = 见底信号
            triggered=True,
            value=f"{pe:.1f}x",
            note="PE < 10, 估值在历史低位"
        ))
    else:
        signals.append(TopBottomSignal(
            name="PE Fwd 中位",
            signal_type="neutral",
            triggered=False,
            value=f"{pe:.1f}x" if pe else "N/A",
            note="估值未明显高估或低估"
        ))

    # 2. 距 52w 高点回撤
    if snap.fifty_two_week_high and snap.current_price:
        dd = (snap.current_price / snap.fifty_two_week_high - 1) * 100
        if dd < -30:
            signals.append(TopBottomSignal(
                name="距高点大幅回撤",
                signal_type="bottom",  # ← 触发 = 见底信号 (深度回撤)
                triggered=True,
                value=f"{dd:.1f}%",
                note="从高点回撤 30%+, 严重超卖, 关注反弹机会"
            ))
        elif dd < -10:
            signals.append(TopBottomSignal(
                name="距高点回撤",
                signal_type="bottom",  # ← 触发 = 见底信号
                triggered=True,
                value=f"{dd:.1f}%",
                note="从高点回撤 10%+, 可能见底机会"
            ))
        elif dd > -5:
            signals.append(TopBottomSignal(
                name="接近 52w 高点",
                signal_type="top",  # ← 触发 = 见顶警告
                triggered=True,
                value=f"{dd:.1f}%",
                note="距离 52w 高点不到 5%, 谨防动能衰竭"
            ))
        else:
            signals.append(TopBottomSignal(
                name="中位震荡",
                signal_type="neutral",
                triggered=False,
                value=f"{dd:.1f}%",
                note="距高点 5-10%, 区间震荡"
            ))

    # 3. 现价 vs 200d MA
    if snap.current_price and snap.two_hundred_day_ma:
        pct = (snap.current_price / snap.two_hundred_day_ma - 1) * 100
        if pct > 50:
            signals.append(TopBottomSignal(
                name="现价 vs 200d MA",
                signal_type="top",  # ← 触发 = 见顶警告
                triggered=True,
                value=f"+{pct:.1f}%",
                note="超涨 50%+, 严重超买"
            ))
        elif pct > 0:
            signals.append(TopBottomSignal(
                name="现价 vs 200d MA",
                signal_type="top",  # ← 触发 = 见顶警告
                triggered=True,
                value=f"+{pct:.1f}%",
                note="趋势向上, 谨防追高"
            ))
        elif pct < -30:
            signals.append(TopBottomSignal(
                name="现价 vs 200d MA",
                signal_type="bottom",  # ← 触发 = 见底信号
                triggered=True,
                value=f"{pct:.1f}%",
                note="低于 200d MA 30%+, 严重超卖"
            ))
        else:
            signals.append(TopBottomSignal(
                name="现价 vs 200d MA",
                signal_type="bottom",  # ← 触发 = 见底信号
                triggered=True,
                value=f"{pct:.1f}%",
                note="低于长期均线, 可能见底"
            ))

    # 4. Beta 高
    if snap.beta:
        if snap.beta > 2:
            signals.append(TopBottomSignal(
                name="高 Beta",
                signal_type="top",  # ← 触发 = 见顶警告 (高波动=高风险)
                triggered=True,
                value=f"{snap.beta:.2f}",
                note="波动率为大盘 2 倍以上, 仓位要小"
            ))
        elif snap.beta > 1.5:
            signals.append(TopBottomSignal(
                name="中高 Beta",
                signal_type="neutral",
                triggered=False,
                value=f"{snap.beta:.2f}",
                note="波动较大, 注意仓位管理"
            ))

    # 5. 内部人持股低
    if snap.held_percent_insiders is not None:
        if snap.held_percent_insiders < 1:
            signals.append(TopBottomSignal(
                name="内部人持股低",
                signal_type="top",  # ← 触发 = 见顶警告 (管理层对自己信心不足)
                triggered=True,
                value=f"{snap.held_percent_insiders:.1f}%",
                note="内部人持股 < 1%, 信号不积极"
            ))
        elif snap.held_percent_insiders > 20:
            signals.append(TopBottomSignal(
                name="内部人持股高",
                signal_type="bottom",  # ← 触发 = 见底信号 (管理层高信心)
                triggered=True,
                value=f"{snap.held_percent_insiders:.1f}%",
                note="内部人持股 > 20%, 管理层高信心"
            ))

    # 6. 做空占比
    if snap.short_percent_of_float:
        if snap.short_percent_of_float > 20:
            signals.append(TopBottomSignal(
                name="高做空",
                signal_type="bottom",  # ← 触发 = 见底信号 (过度悲观 = 反弹机会)
                triggered=True,
                value=f"{snap.short_percent_of_float:.1f}%",
                note="做空 > 20%, 市场极度看空, 可能见底"
            ))
        elif snap.short_percent_of_float < 2:
            signals.append(TopBottomSignal(
                name="低做空",
                signal_type="top",  # ← 触发 = 见顶警告 (市场过度乐观)
                triggered=True,
                value=f"{snap.short_percent_of_float:.1f}%",
                note="做空 < 2%, 市场极度乐观, 谨防见顶"
            ))

    # 7. 现金流
    if snap.free_cashflow_usd_bil is not None:
        if snap.free_cashflow_usd_bil < -0.5:
            signals.append(TopBottomSignal(
                name="FCF 转负",
                signal_type="top",  # ← 触发 = 见顶警告 (财务恶化)
                triggered=True,
                value=f"${snap.free_cashflow_usd_bil:.1f}B",
                note="自由现金流转负, 关注融资风险"
            ))
        elif snap.free_cashflow_usd_bil > snap.market_cap and snap.market_cap:
            signals.append(TopBottomSignal(
                name="FCF 强劲",
                signal_type="bottom",  # ← 触发 = 见底信号 (财务健康)
                triggered=True,
                value=f"${snap.free_cashflow_usd_bil:.1f}B",
                note="自由现金流超过市值, 极度低估"
            ))

    triggered_count = sum(1 for s in signals if s.triggered)
    total_count = len(signals)
    top_count = sum(1 for s in signals if s.signal_type == "top" and s.triggered)
    bottom_count = sum(1 for s in signals if s.signal_type == "bottom" and s.triggered)

    # 情绪判断 (会由 app.py 用真实 CNN 数据覆盖)
    if triggered_count >= total_count * 0.7:
        sentiment = "extreme_greed"
    elif triggered_count >= total_count * 0.5:
        sentiment = "greed"
    elif triggered_count >= total_count * 0.3:
        sentiment = "neutral"
    elif triggered_count > 0:
        sentiment = "fear"
    else:
        sentiment = "extreme_fear"

    return TopBottomBlock(
        ticker=snap.ticker,
        signals=signals,
        triggered_count=triggered_count,
        total_count=total_count,
        sentiment=sentiment,
    )


# ────────────────────────────────────────
# 综合分计算
# ────────────────────────────────────────
def compute_composite_score(
    fund: FundamentalScan,
    top_bottom: TopBottomBlock,
) -> float:
    """综合分 = 基本面 60% + 反向情绪 40%"""
    # 情绪分数 (反向, 越恐惧 = 越好)
    sentiment_to_score = {
        "extreme_fear": 9,
        "fear": 7,
        "neutral": 5,
        "greed": 3,
        "extreme_greed": 1,
    }
    sent_score = sentiment_to_score[top_bottom.sentiment]

    composite = fund.fund_score * 0.6 + sent_score * 0.4
    return round(composite, 2)


def derive_signal(composite: float, target: float = None, current: float = None) -> tuple:
    """根据综合分 + 目标价/现价,推导信号"""
    if composite >= 7.5:
        signal = "bullish"
    elif composite >= 6.0:
        signal = "neutral_to_bullish"
    elif composite >= 4.0:
        signal = "neutral"
    elif composite >= 3.0:
        signal = "neutral_to_bearish"
    else:
        signal = "bearish"
    return signal, composite


# =============================================================
# Phase C: 轮动定位量化 (4 子指标)
# =============================================================

# GICS 11 板块 → SPDR 板块 ETF 映射
SECTOR_ETF = {
    "Technology": "XLK",
    "Communication Services": "XLC",
    "Consumer Cyclical": "XLY",
    "Consumer Discretionary": "XLY",  # 别名
    "Consumer Defensive": "XLP",
    "Consumer Staples": "XLP",  # 别名
    "Healthcare": "XLV",
    "Financial Services": "XLF",
    "Financials": "XLF",  # 别名
    "Industrials": "XLI",
    "Energy": "XLE",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Basic Materials": "XLB",
    "Materials": "XLB",  # 别名
}


def _calc_return(closes: list, days_ago: int) -> Optional[float]:
    """计算 N 日前的回报率 (N=days_ago)"""
    if not closes or len(closes) < days_ago + 1:
        return None
    current = closes[-1]
    past = closes[-days_ago - 1] if days_ago > 0 else closes[-1]
    if not past or past == 0:
        return None
    return (current - past) / past * 100  # 百分比


def _calc_avg_volume(volumes: list, days: int) -> Optional[float]:
    """最近 N 日均量"""
    if not volumes or len(volumes) < days:
        return None
    return sum(volumes[-days:]) / days


def compute_rotation_metrics(
    snap: StockSnapshot,
    sector_etf_history: Optional[Dict[str, Any]] = None,
    ticker_history: Optional[Dict[str, Any]] = None,
    spy_history: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """轮动定位量化 - 4 个子指标 + 总分

    数据需求 (任一缺失该子指标得 0):
      - sector_etf_history: 板块 ETF 历史 (200d)
      - ticker_history: 个股历史 (200d)
      - spy_history: SPY 基准 (200d)
      - Google Trends: cloud 不支持, 留接口给本地

    返回:
      sub_scores: {sector_relative, fund_heat, google_trend, ticker_relative}
      total_score: 0-100
      auto_position: leading/mid/late/catchup
    """
    result = {
        "sub_scores": {
            "sector_relative": {"score": 0, "max": 25, "detail": "无板块 ETF 数据", "available": False},
            "fund_heat": {"score": 0, "max": 25, "detail": "无板块 ETF 数据", "available": False},
            "google_trend": {"score": 0, "max": 25, "detail": "cloud 不支持 (需本地 pytrends)", "available": False},
            "ticker_relative": {"score": 0, "max": 25, "detail": "无 ticker 历史数据", "available": False},
        },
        "total_score": 0,
        "max_score": 100,
        "auto_position": "mid",
        "auto_position_label": "中段 (数据不足)",
        "sector_etf": SECTOR_ETF.get(snap.sector) if snap.sector else None,
        "sector": snap.sector or "N/A",
    }

    # ────────────────────────────────────────
    # 1. 板块相对强弱 (板块 ETF 1m 涨幅 - SPY 1m 涨幅)
    # ────────────────────────────────────────
    if sector_etf_history and spy_history:
        try:
            sector_closes = sector_etf_history.get('c', [])
            spy_closes = spy_history.get('c', [])
            sector_1m = _calc_return(sector_closes, 21)
            spy_1m = _calc_return(spy_closes, 21)
            if sector_1m is not None and spy_1m is not None:
                diff = sector_1m - spy_1m
                if diff > 10:
                    sub_score = 25
                    level = "大幅跑赢 (+{:.1f}%)"
                elif diff > 0:
                    sub_score = 18
                    level = "小幅跑赢 (+{:.1f}%)"
                elif diff > -10:
                    sub_score = 10
                    level = "跑输 (-{:.1f}%)"
                else:
                    sub_score = 0
                    level = "大幅跑输 (-{:.1f}%)"
                result["sub_scores"]["sector_relative"] = {
                    "score": sub_score, "max": 25, "available": True,
                    "detail": "板块 ETF 1m {} (板块: +{:.1f}%, SPY: +{:.1f}%)".format(
                        level.format(abs(diff)), sector_1m, spy_1m),
                }
        except Exception as e:
            pass

    # ────────────────────────────────────────
    # 2. 板块资金热度 (板块 ETF 20d vs 60d 均量比率)
    # ────────────────────────────────────────
    if sector_etf_history:
        try:
            volumes = sector_etf_history.get('v', [])
            vol_20d = _calc_avg_volume(volumes, 20)
            vol_60d = _calc_avg_volume(volumes, 60)
            if vol_20d and vol_60d and vol_60d > 0:
                ratio = vol_20d / vol_60d
                if ratio > 1.5:
                    sub_score = 25
                    level = "资金涌入 ({:.2f}x)"
                elif ratio > 1.2:
                    sub_score = 18
                    level = "温和放量 ({:.2f}x)"
                elif ratio > 0.8:
                    sub_score = 12
                    level = "成交正常 ({:.2f}x)"
                else:
                    sub_score = 5
                    level = "资金流出 ({:.2f}x)"
                result["sub_scores"]["fund_heat"] = {
                    "score": sub_score, "max": 25, "available": True,
                    "detail": "板块 ETF 20d/60d 均量比: " + level.format(ratio),
                }
        except Exception as e:
            pass

    # ────────────────────────────────────────
    # 3. Google Trends (cloud 留接口)
    # ────────────────────────────────────────
    # 留 0 分 + 标注不可用, Phase C+ 可在本地集成 pytrends
    # result["sub_scores"]["google_trend"] 已在初始化设 0

    # ────────────────────────────────────────
    # 4. 个股相对表现 (ticker 1m - SPY 1m)
    # ────────────────────────────────────────
    if ticker_history and spy_history:
        try:
            ticker_closes = ticker_history.get('c', [])
            spy_closes = spy_history.get('c', [])
            ticker_1m = _calc_return(ticker_closes, 21)
            spy_1m = _calc_return(spy_closes, 21)
            ticker_3m = _calc_return(ticker_closes, 63)
            spy_3m = _calc_return(spy_closes, 63)
            if ticker_1m is not None and spy_1m is not None:
                diff = ticker_1m - spy_1m
                if diff > 10:
                    sub_score = 25
                    level = "强势 (1m vs SPY +{:.1f}%)"
                elif diff > 5:
                    sub_score = 18
                    level = "偏强 (+{:.1f}%)"
                elif diff > -5:
                    sub_score = 12
                    level = "中性 ({:+.1f}%)"
                else:
                    sub_score = 0
                    level = "弱势 ({:+.1f}%)"
                # 3m 也算上 (信息含量)
                extra = ""
                if ticker_3m is not None and spy_3m is not None:
                    diff_3m = ticker_3m - spy_3m
                    extra = f" | 3m vs SPY {diff_3m:+.1f}%"
                result["sub_scores"]["ticker_relative"] = {
                    "score": sub_score, "max": 25, "available": True,
                    "detail": level.format(diff) + extra,
                }
        except Exception as e:
            pass

    # ────────────────────────────────────────
    # 5. 综合判断
    # ────────────────────────────────────────
    total = sum(s["score"] for s in result["sub_scores"].values())
    result["total_score"] = total
    if total >= 80:
        result["auto_position"] = "leading"
        result["auto_position_label"] = "高确信领涨"
    elif total >= 60:
        result["auto_position"] = "mid"
        result["auto_position_label"] = "中段持有"
    elif total >= 40:
        result["auto_position"] = "late"
        result["auto_position_label"] = "末段谨慎"
    else:
        result["auto_position"] = "catchup"
        result["auto_position_label"] = "低谷/补涨"

    return result


# =============================================================
# Phase D: 风险定价自动评分 (4 类 × 25/25/30/20 权重)
# =============================================================

# 各行业关键指标中位数 (用于 competitor 风险比较)
INDUSTRY_MEDIAN_GROSS_MARGIN = {
    "Technology": 55,
    "Communication Services": 45,
    "Consumer Cyclical": 28,
    "Consumer Defensive": 38,
    "Healthcare": 65,
    "Financial Services": 60,
    "Industrials": 25,
    "Energy": 35,
    "Utilities": 50,
    "Real Estate": 60,
    "Basic Materials": 30,
}

INDUSTRY_MEDIAN_REVENUE_GROWTH = {
    "Technology": 12,
    "Communication Services": 8,
    "Consumer Cyclical": 6,
    "Consumer Defensive": 4,
    "Healthcare": 10,
    "Financial Services": 7,
    "Industrials": 5,
    "Energy": 3,
    "Utilities": 2,
    "Real Estate": 4,
    "Basic Materials": 5,
}

# 高集中度行业 (竞争对手风险加分)
HIGH_CONCENTRATION_INDUSTRIES = {
    "Semiconductors", "Application Software", "Internet Software & Services",
    "Auto Manufacturers", "Pharmaceutical", "Aerospace & Defense",
    "Internet Content & Information", "Software—Application",
}


def compute_risk_scores(
    snap: StockSnapshot,
    macro_indicators: Optional[Dict[str, Any]] = None,
    sector_history: Optional[Dict[str, Any]] = None,
    spy_history: Optional[Dict[str, Any]] = None,
    ticker_history: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Phase D: 4 类风险自动评分

    权重 (场景 C 默认, 个股风控):
      ① 宏观风险 (macro)   : 25%
      ② 行业风险 (sector)  : 25%
      ③ 竞争对手风险 (competitor): 20%
      ④ 公司内部风险 (company): 30%

    返回:
      sub_scores: 4 类 0-10 分 (越高越危险)
      weighted_score: 0-10 加权综合
      signal: low_risk / medium_risk / high_risk / extreme_risk
      alerts: 高风险触发列表
    """
    sub_scores = {
        "macro": {"score": 0, "details": [], "available": False},
        "sector": {"score": 0, "details": [], "available": False},
        "competitor": {"score": 0, "details": [], "available": False},
        "company": {"score": 0, "details": [], "available": False},
    }
    alerts = []

    # ────────────────────────────────────────
    # ① 宏观风险 (0-10)
    # ────────────────────────────────────────
    if macro_indicators and macro_indicators.get("status") == "ok":
        macro_score = 0
        ind = macro_indicators.get("indicators", {})

        # 10y yield 利率
        yield_10y = ind.get("10y_yield")
        if yield_10y is not None:
            if yield_10y > 4.5:
                macro_score += 3
                sub_scores["macro"]["details"].append(f"10y 利率 {yield_10y:.2f}% 高位 (+3)")
            elif yield_10y > 3.5:
                macro_score += 2
                sub_scores["macro"]["details"].append(f"10y 利率 {yield_10y:.2f}% 偏高 (+2)")
            elif yield_10y > 2.5:
                macro_score += 1
                sub_scores["macro"]["details"].append(f"10y 利率 {yield_10y:.2f}% 中位 (+1)")

        # 联储利率
        fed_funds = ind.get("fed_funds")
        if fed_funds is not None:
            if fed_funds > 5.0:
                macro_score += 2
                sub_scores["macro"]["details"].append(f"联储利率 {fed_funds:.2f}% 限制性 (+2)")
            elif fed_funds > 4.0:
                macro_score += 1
                sub_scores["macro"]["details"].append(f"联储利率 {fed_funds:.2f}% (+1)")

        # CPI
        cpi = ind.get("CPI")
        if cpi is not None:
            # CPI 是水平 (e.g. 320), 不直接用作风险分, 改用其同比
            # 这里没 yoy, 跳过 (FRED API 限制)
            pass

        # 失业率 (过低=过热)
        unrate = ind.get("unemployment")
        if unrate is not None:
            if unrate < 3.5:
                macro_score += 2
                sub_scores["macro"]["details"].append(f"失业率 {unrate:.1f}% 过热 (+2)")

        sub_scores["macro"]["score"] = min(10, macro_score)
        sub_scores["macro"]["available"] = True
    else:
        sub_scores["macro"]["details"].append("FRED 未配置, 用 sentiment 反向 (Phase A 已用 CNN)")
        # 用 CNN sentiment 反向 (越恐惧 = 宏观给机会, 越贪婪 = 风险)
        # 这里由 caller 传 market_sentiment_score, 简单放 5 = 中性
        sub_scores["macro"]["score"] = 5
        sub_scores["macro"]["available"] = False

    # ────────────────────────────────────────
    # ② 行业风险 (0-10)
    # ────────────────────────────────────────
    sector_score = 0
    if sector_history and spy_history:
        sector_closes = sector_history.get('c', [])
        spy_closes = spy_history.get('c', [])

        # 板块 1m vs SPY
        sector_1m = _calc_return(sector_closes, 21)
        spy_1m = _calc_return(spy_closes, 21)
        if sector_1m is not None and spy_1m is not None:
            diff = sector_1m - spy_1m
            if diff < -10:
                sector_score += 5
                sub_scores["sector"]["details"].append(f"板块 1m 跑输 SPY {diff:.1f}% (+5)")
            elif diff < -3:
                sector_score += 3
                sub_scores["sector"]["details"].append(f"板块 1m 跑输 SPY {diff:.1f}% (+3)")
            elif diff < 0:
                sector_score += 1
                sub_scores["sector"]["details"].append(f"板块 1m 微跑输 SPY {diff:.1f}% (+1)")

        # 板块波动率 (20d std / SPY 20d std)
        if len(sector_closes) >= 20 and len(spy_closes) >= 20:
            sector_std = _std(sector_closes[-20:]) / (sum(sector_closes[-20:]) / 20) * 100  # CV%
            spy_std = _std(spy_closes[-20:]) / (sum(spy_closes[-20:]) / 20) * 100
            vol_ratio = sector_std / spy_std if spy_std > 0 else 1
            if vol_ratio > 2:
                sector_score += 3
                sub_scores["sector"]["details"].append(f"板块波动率 {vol_ratio:.2f}x SPY (+3)")
            elif vol_ratio > 1.5:
                sector_score += 2
                sub_scores["sector"]["details"].append(f"板块波动率 {vol_ratio:.2f}x SPY (+2)")
            elif vol_ratio > 1.2:
                sector_score += 1
                sub_scores["sector"]["details"].append(f"板块波动率 {vol_ratio:.2f}x SPY (+1)")

        sub_scores["sector"]["available"] = True
    else:
        sub_scores["sector"]["details"].append("无板块 ETF 历史")

    # ticker 自身波动率 (用 beta 近似)
    if snap.beta:
        if snap.beta > 2:
            sector_score += 2
            sub_scores["sector"]["details"].append(f"Beta {snap.beta:.2f} 高 (+2)")
        elif snap.beta > 1.5:
            sector_score += 1
            sub_scores["sector"]["details"].append(f"Beta {snap.beta:.2f} 偏高 (+1)")

    sub_scores["sector"]["score"] = min(10, sector_score)

    # ────────────────────────────────────────
    # ③ 竞争对手风险 (0-10)
    # ────────────────────────────────────────
    competitor_score = 0

    # 毛利率 vs 行业中位数
    if snap.gross_margin is not None and snap.sector in INDUSTRY_MEDIAN_GROSS_MARGIN:
        industry_gm = INDUSTRY_MEDIAN_GROSS_MARGIN[snap.sector]
        diff = snap.gross_margin - industry_gm
        if diff < -20:
            competitor_score += 5
            sub_scores["competitor"]["details"].append(
                f"毛利率 {snap.gross_margin:.0f}% 远低于行业中位 {industry_gm}% (+5)"
            )
        elif diff < -10:
            competitor_score += 3
            sub_scores["competitor"]["details"].append(
                f"毛利率 {snap.gross_margin:.0f}% 低于行业中位 {industry_gm}% (+3)"
            )
        elif diff < -5:
            competitor_score += 1
            sub_scores["competitor"]["details"].append(
                f"毛利率 {snap.gross_margin:.0f}% 略低 (+1)"
            )

    # 营收增速 vs 行业中位数
    if snap.revenue_growth_yoy is not None and snap.sector in INDUSTRY_MEDIAN_REVENUE_GROWTH:
        industry_g = INDUSTRY_MEDIAN_REVENUE_GROWTH[snap.sector]
        diff = snap.revenue_growth_yoy - industry_g
        if diff < -20:
            competitor_score += 4
            sub_scores["competitor"]["details"].append(
                f"营收 YoY {snap.revenue_growth_yoy:.0f}% 大幅落后行业 {industry_g}% (+4)"
            )
        elif diff < -10:
            competitor_score += 2
            sub_scores["competitor"]["details"].append(
                f"营收 YoY {snap.revenue_growth_yoy:.0f}% 落后行业 {industry_g}% (+2)"
            )

    # 高集中度行业标记 (竞争更激烈)
    if snap.industry and snap.industry in HIGH_CONCENTRATION_INDUSTRIES:
        competitor_score += 2
        sub_scores["competitor"]["details"].append(
            f"高集中度行业: {snap.industry} (+2)"
        )

    sub_scores["competitor"]["score"] = min(10, competitor_score)
    sub_scores["competitor"]["available"] = bool(snap.sector)

    # ────────────────────────────────────────
    # ④ 公司内部风险 (0-10)
    # ────────────────────────────────────────
    company_score = 0

    # 流动比率 (currentRatio)
    if snap.current_ratio is not None:
        if snap.current_ratio < 1:
            company_score += 5
            sub_scores["company"]["details"].append(
                f"流动比率 {snap.current_ratio:.2f} < 1 (流动性危机) (+5)"
            )
            alerts.append(f"流动性危机: current ratio {snap.current_ratio:.2f}")
        elif snap.current_ratio < 1.5:
            company_score += 2
            sub_scores["company"]["details"].append(
                f"流动比率 {snap.current_ratio:.2f} 偏低 (+2)"
            )

    # 负债/权益 (debtToEquity, Finnhub 返百分比, 200 = 200%)
    if snap.debt_to_equity is not None:
        if snap.debt_to_equity > 200:
            company_score += 5
            sub_scores["company"]["details"].append(
                f"负债/权益 {snap.debt_to_equity:.0f}% 极高 (+5)"
            )
            alerts.append(f"高负债: D/E {snap.debt_to_equity:.0f}%")
        elif snap.debt_to_equity > 100:
            company_score += 2
            sub_scores["company"]["details"].append(
                f"负债/权益 {snap.debt_to_equity:.0f}% 高 (+2)"
            )

    # 自由现金流
    if snap.free_cashflow_usd_bil is not None:
        if snap.free_cashflow_usd_bil < 0:
            company_score += 5
            sub_scores["company"]["details"].append(
                f"FCF {snap.free_cashflow_usd_bil:.1f}B 转负 (融资风险) (+5)"
            )
            alerts.append("现金流恶化")
        elif snap.free_cashflow_usd_bil < 0.5:
            company_score += 2
            sub_scores["company"]["details"].append(
                f"FCF {snap.free_cashflow_usd_bil:.1f}B 偏弱 (+2)"
            )

    # 内部人持股
    if snap.held_percent_insiders is not None:
        if snap.held_percent_insiders < 1:
            company_score += 2
            sub_scores["company"]["details"].append(
                f"内部人持股 {snap.held_percent_insiders:.1f}% < 1% (+2)"
            )
        elif snap.held_percent_insiders < 5:
            company_score += 1
            sub_scores["company"]["details"].append(
                f"内部人持股 {snap.held_percent_insiders:.1f}% 偏低 (+1)"
            )

    # 做空比例
    if snap.short_percent_of_float is not None:
        if snap.short_percent_of_float > 20:
            company_score += 3
            sub_scores["company"]["details"].append(
                f"做空比例 {snap.short_percent_of_float:.1f}% 极高 (市场看空) (+3)"
            )
            alerts.append(f"高做空: {snap.short_percent_of_float:.1f}%")
        elif snap.short_percent_of_float > 10:
            company_score += 1
            sub_scores["company"]["details"].append(
                f"做空比例 {snap.short_percent_of_float:.1f}% 高 (+1)"
            )

    sub_scores["company"]["score"] = min(10, company_score)
    sub_scores["company"]["available"] = True

    # ────────────────────────────────────────
    # 综合 (场景 C 默认权重: 25/25/20/30)
    # ────────────────────────────────────────
    WEIGHTS = {"macro": 0.25, "sector": 0.25, "competitor": 0.20, "company": 0.30}
    weighted = (
        sub_scores["macro"]["score"] * WEIGHTS["macro"]
        + sub_scores["sector"]["score"] * WEIGHTS["sector"]
        + sub_scores["competitor"]["score"] * WEIGHTS["competitor"]
        + sub_scores["company"]["score"] * WEIGHTS["company"]
    )
    weighted = round(weighted, 2)

    if weighted >= 7.5:
        signal = "extreme_risk"  # 改个名, 跟 Phase D 语义对齐
        signal_label = "✗ 极高风险, 建议减仓"
    elif weighted >= 6.0:
        signal = "high_risk"
        signal_label = "⚠ 高风险"
    elif weighted >= 4.0:
        signal = "medium_risk"
        signal_label = "中风险"
    else:
        signal = "low_risk"
        signal_label = "✓ 低风险"

    return {
        "sub_scores": sub_scores,
        "weighted_score": weighted,
        "signal": signal,
        "signal_label": signal_label,
        "weights": WEIGHTS,
        "alerts": alerts,
        "sector": snap.sector or "N/A",
        "industry": snap.industry or "N/A",
    }


def _std(values: list) -> float:
    """标准差"""
    if not values or len(values) < 2:
        return 0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return variance ** 0.5


# =============================================================
# Phase B: 蓝海框架 (MPEVL 5 维 + 5 大方法 + 信息差 4 级)
# =============================================================

def compute_blue_ocean_scores(
    snap: StockSnapshot,
    fund: FundamentalScan,
    tb: TopBottomBlock,
    market_sentiment_score: Optional[int] = None,
) -> Dict[str, Any]:
    """蓝海框架综合分析

    来源: mainland-subjective-analysis skill v1.0
    输出:
      - mpevl: 5 维评分 (Macro/Policy/Earnings/Valuation/Liquidity)
      - methods: 5 大方法适用度
      - info_gap: 信息差 4 级 (S/A/B/C)
      - overall: 综合判断

    注: Phase 移除 Step 5 (cal 参数), 政策维度改用固定 P=5
    """
    # ────────────────────────────────────────
    # 1. MPEVL 5 维评分
    # ────────────────────────────────────────
    mpevl = {}

    # M 宏观 (依赖 FRED, 这里用市场情绪近似)
    if market_sentiment_score is not None:
        # 反向: 越恐惧 = 宏观给机会 (低基数效应)
        if market_sentiment_score < 25:
            m_score = 8
            m_detail = f"市场情绪极端恐惧 (F&G {market_sentiment_score}), 宏观给机会"
        elif market_sentiment_score < 45:
            m_score = 6
            m_detail = f"市场情绪恐惧 (F&G {market_sentiment_score}), 宏观偏正面"
        elif market_sentiment_score < 55:
            m_score = 5
            m_detail = f"市场情绪中性 (F&G {market_sentiment_score}), 宏观中性"
        elif market_sentiment_score < 75:
            m_score = 4
            m_detail = f"市场情绪贪婪 (F&G {market_sentiment_score}), 宏观偏负面"
        else:
            m_score = 2
            m_detail = f"市场情绪极端贪婪 (F&G {market_sentiment_score}), 宏观过热"
        m_signals = [f"CNN Fear & Greed: {market_sentiment_score}"]
    else:
        m_score = 5
        m_detail = "无情绪数据, 中性"
        m_signals = []

    mpevl["M"] = {
        "code": "M", "name": "宏观", "score": m_score, "detail": m_detail,
        "signals": m_signals,
    }

    # P 政策 (Phase 移除日历, 改用固定中性)
    p_score = 5
    p_detail = "无重大政策窗口, 中性 (Phase 移除日历事件)"
    mpevl["P"] = {
        "code": "P", "name": "政策", "score": p_score, "detail": p_detail,
        "signals": ["无日历事件追踪"],
    }

    # E 盈利 (用基本面 4 维里的 earnings_score)
    e_score = int(fund.earnings_score)
    e_detail = fund.earnings_detail or "无盈利数据"
    mpevl["E"] = {
        "code": "E", "name": "盈利", "score": e_score, "detail": e_detail,
        "signals": [fund.earnings_signal],
    }

    # V 估值 (用基本面 4 维里的 valuation_score)
    v_score = int(fund.valuation_score)
    v_detail = fund.valuation_detail or "无估值数据"
    mpevl["V"] = {
        "code": "V", "name": "估值", "score": v_score, "detail": v_detail,
        "signals": [f"PE Fwd: {snap.pe_forward}" if snap.pe_forward else "无 PE"],
    }

    # L 流动性 (用 50d/200d MA + ADV)
    l_score = 5
    l_signals = []
    if snap.fifty_day_ma and snap.current_price and snap.two_hundred_day_ma:
        above_50 = (snap.current_price / snap.fifty_day_ma - 1) * 100
        above_200 = (snap.current_price / snap.two_hundred_day_ma - 1) * 100
        # 趋势向上 = 流动性好
        if above_50 > 5 and above_200 > 0:
            l_score = 7
            l_detail = f"现价在 50d/200d MA 之上, 趋势健康 (+{above_50:.0f}% / +{above_200:.0f}%)"
        elif above_50 < -5 or above_200 < 0:
            l_score = 3
            l_detail = f"现价在 50d/200d MA 之下, 趋势走弱 ({above_50:+.0f}% / {above_200:+.0f}%)"
        else:
            l_score = 5
            l_detail = f"现价在 50d/200d MA 附近, 趋势中性 ({above_50:+.0f}% / {above_200:+.0f}%)"
        l_signals = [f"vs 50d MA: {above_50:+.1f}%", f"vs 200d MA: {above_200:+.1f}%"]
    else:
        l_detail = "无均线数据"
    if snap.adv_30d_shares_mil:
        l_signals.append(f"30d 均量: {snap.adv_30d_shares_mil:.1f}M 股")
    mpevl["L"] = {
        "code": "L", "name": "流动性", "score": l_score, "detail": l_detail,
        "signals": l_signals,
    }

    # ────────────────────────────────────────
    # 2. 5 大方法适用度
    # ────────────────────────────────────────
    methods = []

    # 1. 产业链瓶颈定位
    chain_applicable = 8 if (snap.sector or snap.industry) else 0
    methods.append({
        "code": "chain_bottleneck",
        "name": "产业链瓶颈定位",
        "applicable": chain_applicable,
        "rationale": f"行业: {snap.industry or 'N/A'} - 可用 yfinance/Finnhub 行业数据 + LLM 推断瓶颈位置",
        "data_available": bool(snap.industry),
    })

    # 2. 日历+事件叠加 (Phase 移除, 改用固定中性)
    methods.append({
        "code": "calendar_event",
        "name": "日历+事件叠加",
        "applicable": 0,
        "rationale": "❌ Phase 移除 (用户判断长期价值不大), 保留入口便于未来重启用",
        "data_available": False,
    })

    # 3. 轮动规律识别
    methods.append({
        "code": "rotation",
        "name": "轮动规律识别",
        "applicable": 5,  # 需用户主观判断
        "rationale": "需用户填轮动链 + 资金流方向, AI 仅给量化辅助 (Phase C)",
        "data_available": False,
    })

    # 4. 专家访谈加权
    methods.append({
        "code": "expert_interview",
        "name": "专家访谈加权",
        "applicable": 0,
        "rationale": "❌ 柯基无法独立获取 (S 级信息), 需用户提供",
        "data_available": False,
    })

    # 5. 见顶/见底信号
    tb_applicable = 9 if tb.signals else 0
    tb_triggered = sum(1 for s in tb.signals if s.triggered)
    methods.append({
        "code": "top_bottom",
        "name": "见顶/见底信号清单",
        "applicable": tb_applicable,
        "rationale": f"{tb_triggered}/{len(tb.signals)} 触发, 已分类见顶/见底两组 (Phase A)",
        "data_available": True,
    })

    # ────────────────────────────────────────
    # 3. 信息差 4 级评估
    # ────────────────────────────────────────
    info_gap = []

    # S 级 (一手) - 柯基拿不到
    info_gap.append({
        "level": "S",
        "name": "一手信息 (独家)",
        "score": 0,
        "sources": [
            "供应商电话会议 (❌ 需用户参加)",
            "离职高管访谈 (❌ 需用户关系)",
            "大基金私下路演 (❌ 需机构通道)",
            "政策窗口先知 (❌ 提前量是关键)",
        ],
        "available": False,
    })

    # A 级 (二手) - 部分可拉
    a_sources = []
    a_score = 0
    if snap.held_percent_institutions is not None:
        a_sources.append(f"13F 机构持仓: {snap.held_percent_institutions:.1f}%")
        a_score += 3
    if snap.recommendation_mean is not None:
        a_sources.append(f"分析师共识目标: {snap.recommendation_mean:.2f}")
        a_score += 2
    if snap.target_mean_price:
        a_sources.append(f"分析师目标价: ${snap.target_mean_price}")
        a_score += 2
    if not a_sources:
        a_sources = ["13F 持仓变动", "分析师预期差", "大单流向 (Fintel/Quiver Quantitative)"]
        a_score = 2
    info_gap.append({
        "level": "A",
        "name": "二手信息 (机构/分析师)",
        "score": min(a_score, 10),
        "sources": a_sources,
        "available": True,
    })

    # B 级 (公开) - LLM 推断
    b_sources = [
        "财经媒体报道 (LLM 扫描可补)",
        "雪球/Reddit/X 讨论热度",
        "Google Trends 搜索指数 (需 pytrends)",
        "公司投资者电话会议 transcript (需 SEC EDGAR)",
    ]
    info_gap.append({
        "level": "B",
        "name": "公开信息 (媒体/社区)",
        "score": 5,  # LLM 可扫描但有滞后
        "sources": b_sources,
        "available": True,
    })

    # C 级 (低质) - yfinance 永远有
    c_sources = []
    c_score = 8
    if snap.name: c_sources.append(f"公司名: {snap.name}")
    if snap.current_price: c_sources.append(f"现价: ${snap.current_price}")
    if snap.pe_forward: c_sources.append(f"PE Fwd: {snap.pe_forward}")
    if snap.gross_margin: c_sources.append(f"毛利率: {snap.gross_margin:.1f}%")
    if snap.revenue_growth_yoy: c_sources.append(f"营收 YoY: {snap.revenue_growth_yoy:.1f}%")
    if snap.short_percent_of_float: c_sources.append(f"做空比例: {snap.short_percent_of_float:.1f}%")
    if snap.held_percent_insiders is not None: c_sources.append(f"内部人持股: {snap.held_percent_insiders:.1f}%")
    c_sources.append("(其他 ~40 个 yfinance/Finnhub 字段)")
    info_gap.append({
        "level": "C",
        "name": "低质公开数据 (财报/价格)",
        "score": c_score,
        "sources": c_sources,
        "available": True,
    })

    # ────────────────────────────────────────
    # 4. 综合判断
    # ────────────────────────────────────────
    mpevl_avg = sum(d["score"] for d in mpevl.values()) / 5
    methods_avg = sum(m["applicable"] for m in methods) / 5

    # 信息差综合 (越靠 S/A 级越多越好)
    gap_weights = {"S": 4, "A": 3, "B": 2, "C": 1}
    weighted_gap = sum(g["score"] * gap_weights[g["level"]] for g in info_gap)
    max_gap = sum(10 * w for w in gap_weights.values())
    gap_pct = round(weighted_gap / max_gap * 100, 1)

    # 综合建议
    if mpevl_avg >= 7 and gap_pct >= 50:
        overall = "strong_buy_ready"  # 5 维好 + 信息丰富
    elif mpevl_avg >= 6:
        overall = "investable"  # 5 维还行
    elif mpevl_avg >= 4:
        overall = "wait_for_catalyst"  # 中性
    else:
        overall = "avoid"  # 不建议

    return {
        "mpevl": mpevl,
        "methods": methods,
        "info_gap": info_gap,
        "overall": {
            "signal": overall,
            "mpevl_avg": round(mpevl_avg, 2),
            "methods_avg": round(methods_avg, 2),
            "gap_pct": gap_pct,
            "summary": f"MPEVL {mpevl_avg:.1f}/10 · 5方法 {methods_avg:.1f}/10 · 信息差 {gap_pct:.0f}%"
        },
    }

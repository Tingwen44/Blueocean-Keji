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
from typing import List
from schemas import (
    StockSnapshot, FundamentalScan, CalendarBlock,
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
# Step 5: 日历+事件叠加
# ────────────────────────────────────────
def scan_calendar(snap: StockSnapshot) -> CalendarBlock:
    """当前距关键日历节点的天数"""
    today = date.today()

    # 季度判断
    quarter = (today.month - 1) // 3 + 1
    current_quarter = f"Q{quarter} {today.year}"

    # 距中期选举 (2026/11/3)
    try:
        midterm = date(2026, 11, 3)
        days_to_midterm = (midterm - today).days
    except Exception:
        days_to_midterm = None

    # 距鲍威尔卸任 (2026/5/15 假设)
    try:
        powell_end = date(2026, 5, 15)
        days_to_powell = (powell_end - today).days
    except Exception:
        days_to_powell = None

    # 日历效应
    month = today.month
    if month in [9]:
        cal_effect = "9月 (历史最差月份, Citadel 统计)"
    elif month in [10, 11, 12]:
        cal_effect = "10-12月 (Uptober + 圣诞节行情, 历史偏强)"
    elif month in [1, 2]:
        cal_effect = "1-2月 (年初再平衡, 历史中性偏强)"
    elif month in [5, 6, 7, 8]:
        cal_effect = "5-8月 (Sell in May 弱化, 财报季驱动)"
    else:
        cal_effect = "3-4月 (财报季, 中性)"

    # 宏观事件 (根据当前日期 + 已知日历)
    macro_events = []
    if days_to_midterm is not None and 0 < days_to_midterm < 180:
        macro_events.append(f"距中期选举 {days_to_midterm} 天 (政策托底预期)")
    if days_to_powell is not None and 0 < days_to_powell < 90:
        macro_events.append(f"距鲍威尔卸任 {days_to_powell} 天 (宽松交易情绪高峰窗口)")
    elif days_to_powell is not None and 0 < days_to_powell < 180:
        macro_events.append(f"距鲍威尔卸任 {days_to_powell} 天 (宽松交易酝酿)")

    # 周期定位
    if days_to_powell is not None and 0 < days_to_powell < 90:
        position = "1H26 宽松交易窗口后段 (接近情绪高峰)"
    elif days_to_powell is not None and 0 < days_to_powell < 180:
        position = "1H26 宽松交易窗口中段 (宜持有进攻)"
    else:
        position = "2H26 关注 (AI 资本开支是否下修, 警惕见顶)"

    return CalendarBlock(
        ticker=snap.ticker,
        current_quarter=current_quarter,
        days_to_earnings=None,  # 需要 yfinance earnings_dates
        days_to_midterm_election=days_to_midterm,
        days_to_powell_departure=days_to_powell,
        calendar_effect=cal_effect,
        macro_events=macro_events,
        position_in_cycle=position,
    )


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

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


# =============================================================
# Phase B: 蓝海框架 (MPEVL 5 维 + 5 大方法 + 信息差 4 级)
# =============================================================

def compute_blue_ocean_scores(
    snap: StockSnapshot,
    fund: FundamentalScan,
    cal: CalendarBlock,
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

    # P 政策 (用日历位置推断)
    days_to_election = cal.days_to_midterm_election or 999
    days_to_powell = cal.days_to_powell_departure or 999
    if days_to_election < 90:
        p_score = 7
        p_detail = f"距中期选举 {days_to_election} 天, 政策窗口临近, 主题机会"
    elif days_to_powell < 180:
        p_score = 6
        p_detail = f"距鲍威尔卸任 {days_to_powell} 天, 联储换届预期发酵"
    else:
        p_score = 5
        p_detail = "无重大政策窗口, 中性"
    mpevl["P"] = {
        "code": "P", "name": "政策", "score": p_score, "detail": p_detail,
        "signals": [f"距中期选举: {days_to_election} 天", f"距鲍威尔卸任: {days_to_powell} 天"],
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

    # 2. 日历+事件叠加
    cal_applicable = 8 if (cal.days_to_earnings or cal.days_to_midterm_election) else 3
    methods.append({
        "code": "calendar_event",
        "name": "日历+事件叠加",
        "applicable": cal_applicable,
        "rationale": f"距财报: {cal.days_to_earnings or 'N/A'} 天 - 财报季叠加中期选举+鲍威尔卸任",
        "data_available": bool(cal.days_to_earnings),
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

"""
schemas.py
============================================================
Pydantic 数据模型,用于 8 步流程的输入输出
============================================================
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime


# ────────────────────────────────────────
# Step 1: 数据拉取 (自动)
# ────────────────────────────────────────
class StockSnapshot(BaseModel):
    ticker: str
    name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[float] = None
    current_price: Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None
    fifty_day_ma: Optional[float] = None
    two_hundred_day_ma: Optional[float] = None
    beta: Optional[float] = None
    adv_30d_shares_mil: Optional[float] = None
    mcap_usd_bil: Optional[float] = None
    pe_trailing: Optional[float] = None
    pe_forward: Optional[float] = None
    pb: Optional[float] = None
    ps_trailing: Optional[float] = None
    ev_to_ebitda: Optional[float] = None
    ev_to_revenue: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    profit_margin: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None
    revenue_growth_yoy: Optional[float] = None
    earnings_growth_yoy: Optional[float] = None
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    debt_to_equity: Optional[float] = None
    total_cash_usd_bil: Optional[float] = None
    total_debt_usd_bil: Optional[float] = None
    free_cashflow_usd_bil: Optional[float] = None
    operating_cashflow_usd_bil: Optional[float] = None
    target_mean_price: Optional[float] = None
    recommendation_mean: Optional[float] = None
    held_percent_institutions: Optional[float] = None
    held_percent_insiders: Optional[float] = None
    short_percent_of_float: Optional[float] = None
    description: Optional[str] = None
    business_summary: Optional[str] = None
    data_quality: Literal["high", "medium", "low"] = "high"


# ────────────────────────────────────────
# Step 2: 4 维基本面扫描
# ────────────────────────────────────────
class FundamentalScan(BaseModel):
    ticker: str
    earnings_signal: Literal["bullish", "bearish", "neutral"]
    growth_signal: Literal["bullish", "bearish", "neutral"]
    financial_signal: Literal["bullish", "bearish", "neutral"]
    valuation_signal: Literal["bullish", "bearish", "neutral"]
    earnings_detail: str
    growth_detail: str
    financial_detail: str
    valuation_detail: str
    earnings_score: float
    growth_score: float
    financial_score: float
    valuation_score: float
    fund_score: float = Field(..., ge=0, le=10)


# ────────────────────────────────────────
# Step 3: 产业链定位 (LLM 半自动)
# ────────────────────────────────────────
class ChainPositioning(BaseModel):
    ticker: str
    bottleneck_level: Literal["bottleneck_pqp", "bottleneck_vol", "toolmaker", "non_bottleneck"]
    bottleneck_label: str
    customers: List[str]
    pricing_power: Literal["strong", "medium", "weak"]
    volume_price_trend: Literal["pqp", "vp_stable", "vp_down"]
    chain_location: str
    mainline_benefit_score: int = Field(..., ge=0, le=10)
    llm_suggestion: str
    user_confirmed: bool = False


# ────────────────────────────────────────
# Step 4: 催化时点
# ────────────────────────────────────────
class Catalyst(BaseModel):
    event: str
    date: Optional[str] = None
    expected: str
    impact: Literal["positive", "negative", "neutral"]
    probability: int = Field(..., ge=0, le=100)
    source: Optional[str] = None


class CatalystsBlock(BaseModel):
    ticker: str
    catalysts: List[Catalyst]
    total_score: int = Field(..., ge=0, le=10)


# ────────────────────────────────────────
# Step 5: 日历+事件
# ────────────────────────────────────────
# CalendarBlock (Phase 移除于 2026-06-19, 用户判断长期价值不大)
# ────────────────────────────────────────
# (Step 5 删除 - 见 git log)


# ────────────────────────────────────────
# Step 6: 轮动定位
# ────────────────────────────────────────
class RotationBlock(BaseModel):
    ticker: str
    sector: str
    rotation_position: Literal["leading", "mid", "late", "catchup"]
    rotation_chain: str
    capital_flow: str
    relative_performance: str
    # Phase C: 自动量化的轮动指标
    auto_metrics: Optional[dict] = None  # 见 compute_rotation_metrics 返回结构


# ────────────────────────────────────────
# Step 7: 见顶/见底信号
# ────────────────────────────────────────
class TopBottomSignal(BaseModel):
    name: str
    signal_type: Literal["top", "bottom", "neutral"] = "neutral"  # top=见顶警告, bottom=见底信号
    triggered: bool
    value: Optional[str] = None
    note: str


class TopBottomBlock(BaseModel):
    ticker: str
    signals: List[TopBottomSignal]
    triggered_count: int
    total_count: int
    sentiment: Literal["extreme_greed", "greed", "neutral", "fear", "extreme_fear"]
    # Phase A 新增: 真实贪婪指数 (从 CNN Fear & Greed API 拉)
    sentiment_score: Optional[int] = None  # 0-100
    sentiment_label: Optional[str] = None  # CNN 原始标签 "Extreme Greed" / "Greed" / "Neutral" / "Fear" / "Extreme Fear"
    sentiment_source: Optional[str] = None  # "cnn_api" | "rule" | "fallback"
    sentiment_prev_close: Optional[int] = None  # 上一交易日分数
    sentiment_prev_week: Optional[int] = None  # 上周同期分数


# ────────────────────────────────────────
# Step 8: 风险定价
# ────────────────────────────────────────
class RiskItem(BaseModel):
    description: str
    trigger_signal: str
    severity: Literal["high", "medium", "low"]


class RiskBlock(BaseModel):
    ticker: str
    risks: List[RiskItem]
    stop_loss_price: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    # Phase D: 自动 4 类风险评分
    auto_scores: Optional[dict] = None  # 见 compute_risk_scores 返回结构


# ────────────────────────────────────────
# 综合 1 页纸
# ────────────────────────────────────────
class OnePagerReport(BaseModel):
    id: Optional[int] = None
    ticker: str
    name: Optional[str] = None
    sector: Optional[str] = None
    current_price: Optional[float] = None
    target_price: Optional[float] = None
    signal: Literal["bullish", "bearish", "neutral", "neutral_to_bullish", "neutral_to_bearish"]
    confidence: int = Field(..., ge=0, le=100)
    one_liner: str
    snapshot: StockSnapshot
    fundamental: FundamentalScan
    chain: ChainPositioning
    catalysts: CatalystsBlock
    rotation: RotationBlock
    top_bottom: TopBottomBlock
    risk: RiskBlock
    created_at: Optional[datetime] = None
    data_gaps: List[str] = []
    # Phase B: 蓝海框架 (MPEVL 5 维 + 5 大方法 + 信息差 4 级)
    blue_ocean: Optional[dict] = None  # 用 dict 是因为嵌套复杂, 见 compute_blue_ocean_scores

# ────────────────────────────────────────
# Phase B: 蓝海框架模型
# ────────────────────────────────────────
class MPEVLDimension(BaseModel):
    """MPEVL 单维评分"""
    code: Literal["M", "P", "E", "V", "L"]
    name: str  # 宏观/政策/盈利/估值/流动性
    score: int = Field(..., ge=0, le=10)
    detail: str
    signals: List[str] = []  # 具体观察点


class BlueOceanMethod(BaseModel):
    """5 大方法适用度"""
    code: Literal["chain_bottleneck", "rotation", "expert_interview", "top_bottom"]
    name: str
    applicable: int = Field(..., ge=0, le=10)
    rationale: str
    data_available: bool


class InformationGapLevel(BaseModel):
    """信息差 4 级"""
    level: Literal["S", "A", "B", "C"]
    name: str
    score: int = Field(..., ge=0, le=10)  # 该等级信息丰富度
    sources: List[str]  # 具体来源描述
    available: bool  # 柯基是否可独立获取


# ────────────────────────────────────────
# 输入请求
# ────────────────────────────────────────
class AnalysisRequest(BaseModel):
    ticker: str
    use_llm: bool = True
    save_to_db: bool = True


# ────────────────────────────────────────
# 组合管理 (Portfolio)
# ────────────────────────────────────────
class Position(BaseModel):
    ticker: str
    weight_pct: float = Field(..., ge=0, le=100, description="目标权重百分比")
    cost_basis: Optional[float] = Field(None, description="建仓成本价(可选, 用于算浮盈)")
    shares: Optional[float] = Field(None, description="持仓股数(可选, 用于算市值)")
    entry_date: Optional[str] = Field(None, description="建仓日期 YYYY-MM-DD")
    notes: Optional[str] = ""


class PositionCreate(BaseModel):
    ticker: str
    weight_pct: float
    cost_basis: Optional[float] = None
    shares: Optional[float] = None
    entry_date: Optional[str] = None
    notes: Optional[str] = ""


class PositionUpdate(BaseModel):
    weight_pct: Optional[float] = None
    cost_basis: Optional[float] = None
    shares: Optional[float] = None
    entry_date: Optional[str] = None
    notes: Optional[str] = None


class Portfolio(BaseModel):
    id: Optional[int] = None
    name: str
    base_capital: float = 100000.0
    base_currency: str = "USD"
    notes: Optional[str] = ""
    positions: List[Position] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PortfolioCreate(BaseModel):
    name: str
    base_capital: float = 100000.0
    base_currency: str = "USD"
    notes: Optional[str] = ""
    positions: List[PositionCreate] = []


class PortfolioUpdate(BaseModel):
    name: Optional[str] = None
    base_capital: Optional[float] = None
    base_currency: Optional[str] = None
    notes: Optional[str] = None

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
class CalendarBlock(BaseModel):
    ticker: str
    current_quarter: str
    days_to_earnings: Optional[int] = None
    days_to_midterm_election: Optional[int] = None
    days_to_powell_departure: Optional[int] = None
    calendar_effect: str
    macro_events: List[str]
    position_in_cycle: str


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


# ────────────────────────────────────────
# Step 7: 见顶/见底信号
# ────────────────────────────────────────
class TopBottomSignal(BaseModel):
    name: str
    triggered: bool
    value: Optional[str] = None
    note: str


class TopBottomBlock(BaseModel):
    ticker: str
    signals: List[TopBottomSignal]
    triggered_count: int
    total_count: int
    sentiment: Literal["extreme_greed", "greed", "neutral", "fear", "extreme_fear"]


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
    calendar: CalendarBlock
    rotation: RotationBlock
    top_bottom: TopBottomBlock
    risk: RiskBlock
    created_at: Optional[datetime] = None
    data_gaps: List[str] = []


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

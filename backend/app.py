"""
app.py
============================================================
FastAPI 主入口
============================================================
"""
import os
import json
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from data_fetcher import fetch_stock_snapshot, fetch_macro_indicators
from scoring import (
    scan_fundamental, scan_calendar, scan_top_bottom_signals,
    compute_composite_score, derive_signal
)
from llm_helper import suggest_chain_positioning, suggest_catalysts
from database import init_db, save_analysis, list_analyses, get_analysis, get_latest_for_ticker
from pdf_export import generate_html, generate_pdf
from schemas import (
    StockSnapshot, FundamentalScan, ChainPositioning, CatalystsBlock,
    CalendarBlock, RotationBlock, RiskBlock, OnePagerReport,
    PortfolioCreate, PortfolioUpdate, PositionCreate, PositionUpdate,
)


# ────────────────────────────────────────
# FastAPI 实例 + 路径
# ────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")

app = FastAPI(
    title="柯基 1 页纸 API",
    description="基于 BlueOcean Asset 卖方主观分析框架的个股分析",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件 (frontend 下的 css/js)
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# 启动时初始化 DB
init_db()


# ────────────────────────────────────────
# 静态前端
# ────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root():
    """返回前端 SPA"""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse("<h1>请先在 frontend/ 目录创建 index.html</h1>")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


# ────────────────────────────────────────
# API: 数据拉取
# ────────────────────────────────────────
@app.get("/api/snapshot/{ticker}")
async def get_snapshot(ticker: str):
    """拉取单只股票快照 (Step 1)"""
    try:
        snap = fetch_stock_snapshot(ticker)
        return snap.model_dump()
    except Exception as e:
        raise HTTPException(500, f"拉取失败: {str(e)}")


@app.get("/api/macro")
async def get_macro():
    """拉取宏观指标 (Step 5 辅助)"""
    return fetch_macro_indicators()


# ────────────────────────────────────────
# API: 8 步流程 (分步调用)
# ────────────────────────────────────────
@app.get("/api/step2/{ticker}")
async def step2_fundamental(ticker: str):
    """Step 2: 4 维基本面扫描"""
    snap = fetch_stock_snapshot(ticker)
    fund = scan_fundamental(snap)
    return fund.model_dump()


@app.get("/api/step3/{ticker}")
async def step3_chain(ticker: str, use_llm: bool = True):
    """Step 3: 产业链定位 (LLM 半自动)"""
    snap = fetch_stock_snapshot(ticker)
    chain = suggest_chain_positioning(snap) if use_llm else None
    if chain is None:
        # 降级: 用规则推断
        chain = _fallback_chain(snap)
    return chain.model_dump()


def _fallback_chain(snap: StockSnapshot) -> ChainPositioning:
    """LLM 不可用时的规则化降级"""
    sector = (snap.sector or "").lower()
    industry = (snap.industry or "").lower()

    if any(k in industry for k in ["semiconductor", "光器件", "光学", "通信", "electronic"]):
        if snap.gross_margin and snap.gross_margin > 35:
            level = "bottleneck_pqp"
            label = "瓶颈+量价齐升 (电子器件)"
            pricing = "strong"
            vp = "pqp"
        else:
            level = "bottleneck_vol"
            label = "瓶颈+量稳定 (电子)"
            pricing = "medium"
            vp = "vp_stable"
    elif any(k in industry for k in ["银行", "bank", "金融", "保险"]):
        level = "toolmaker"
        label = "基础设施 (金融)"
        pricing = "weak"
        vp = "vp_stable"
    elif any(k in industry for k in ["零售", "消费", "餐饮"]):
        level = "non_bottleneck"
        label = "非瓶颈+周期 (消费)"
        pricing = "weak"
        vp = "vp_down"
    else:
        level = "non_bottleneck"
        label = "非瓶颈 (默认)"
        pricing = "medium"
        vp = "vp_stable"

    return ChainPositioning(
        ticker=snap.ticker,
        bottleneck_level=level,
        bottleneck_label=label,
        customers=[],
        pricing_power=pricing,
        volume_price_trend=vp,
        chain_location=industry or "N/A",
        mainline_benefit_score=5,
        llm_suggestion="(LLM 未启用, 规则降级, 请人工确认)",
        user_confirmed=False,
    )


@app.get("/api/step4/{ticker}")
async def step4_catalysts(ticker: str, use_llm: bool = True):
    """Step 4: 催化扫描 (LLM 半自动)"""
    snap = fetch_stock_snapshot(ticker)
    cats = suggest_catalysts(snap) if use_llm else None
    if cats is None:
        cats = CatalystsBlock(
            ticker=ticker,
            catalysts=[],
            total_score=5,
        )
    return cats.model_dump()


@app.get("/api/step5/{ticker}")
async def step5_calendar(ticker: str):
    """Step 5: 日历+事件"""
    snap = fetch_stock_snapshot(ticker)
    cal = scan_calendar(snap)
    return cal.model_dump()


# Step 6 (轮动), 7 (见顶信号), 8 (风险) - 见 /api/one-pager/{ticker} 一体化输出


# ────────────────────────────────────────
# API: 1 页纸 (一体化)
# ────────────────────────────────────────
class OnePagerRequest(BaseModel):
    use_llm: bool = True
    save_to_db: bool = True
    rotation_position: str = "mid"  # leading/mid/late/catchup
    rotation_chain: str = ""
    capital_flow: str = ""
    relative_performance: str = ""
    risks: List[dict] = []
    stop_loss_price: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    data_gaps: List[str] = []


@app.post("/api/one-pager/{ticker}")
async def generate_one_pager(ticker: str, req: OnePagerRequest):
    """生成 1 页纸 (8 步全过)"""
    try:
        # Step 1
        snap = fetch_stock_snapshot(ticker)
        # Step 2
        fund = scan_fundamental(snap)
        # Step 3
        chain = suggest_chain_positioning(snap) if req.use_llm else _fallback_chain(snap)
        if chain is None:
            chain = _fallback_chain(snap)
        # Step 4
        cats = suggest_catalysts(snap) if req.use_llm else None
        if cats is None:
            cats = CatalystsBlock(ticker=ticker, catalysts=[], total_score=5)
        # Step 5
        cal = scan_calendar(snap)
        # Step 6 (用户填)
        rot = RotationBlock(
            ticker=ticker,
            sector=snap.sector or "N/A",
            rotation_position=req.rotation_position,
            rotation_chain=req.rotation_chain or "未填写",
            capital_flow=req.capital_flow or "未填写",
            relative_performance=req.relative_performance or "未填写",
        )
        # Step 7
        tb = scan_top_bottom_signals(snap)
        # Step 8 (用户填)
        from schemas import RiskItem
        risks_list = []
        for r in req.risks:
            try:
                risks_list.append(RiskItem(**r))
            except Exception:
                pass
        if not risks_list:
            risks_list = [RiskItem(
                description="需手动填写关键风险",
                trigger_signal="—",
                severity="medium",
            )]
        risk = RiskBlock(
            ticker=ticker,
            risks=risks_list,
            stop_loss_price=req.stop_loss_price,
            stop_loss_pct=req.stop_loss_pct,
        )

        # 综合分
        composite = compute_composite_score(fund, tb)
        signal, _ = derive_signal(composite)
        confidence = int(min(100, max(0, composite * 10)))

        # 1 句结论
        one_liner = f"{fund.earnings_signal.upper()} 盈利, {fund.growth_signal.upper()} 增长, {fund.valuation_signal.upper()} 估值; 情绪 {tb.sentiment}; 综合分 {composite}/10 → {signal}"

        report = OnePagerReport(
            ticker=snap.ticker,
            name=snap.name,
            sector=snap.sector,
            current_price=snap.current_price,
            target_price=snap.target_mean_price,
            signal=signal,
            confidence=confidence,
            one_liner=one_liner,
            snapshot=snap,
            fundamental=fund,
            chain=chain,
            catalysts=cats,
            calendar=cal,
            rotation=rot,
            top_bottom=tb,
            risk=risk,
            data_gaps=req.data_gaps,
        )

        # 存档
        rid = None
        if req.save_to_db:
            rid = save_analysis(report)

        return {
            "id": rid,
            "report": report.model_dump(mode="json"),
        }
    except Exception as e:
        raise HTTPException(500, f"生成失败: {str(e)}")


# ────────────────────────────────────────
# API: 1 页纸导出
# ────────────────────────────────────────
@app.post("/api/export/html/{ticker}")
async def export_html(ticker: str, req: OnePagerRequest):
    """导出 1 页纸为 HTML"""
    try:
        # 复用 one-pager 逻辑
        result = await generate_one_pager(ticker, req)
        report_dict = result["report"]
        report = OnePagerReport.model_validate(report_dict)
        html = generate_html(report)
        return HTMLResponse(content=html)
    except Exception as e:
        raise HTTPException(500, f"导出 HTML 失败: {str(e)}")


@app.post("/api/export/pdf/{ticker}")
async def export_pdf(ticker: str, req: OnePagerRequest):
    """导出 1 页纸为 PDF"""
    try:
        result = await generate_one_pager(ticker, req)
        report_dict = result["report"]
        report = OnePagerReport.model_validate(report_dict)
        pdf_bytes = generate_pdf(report)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={ticker}_one_pager.pdf"},
        )
    except Exception as e:
        raise HTTPException(500, f"导出 PDF 失败: {str(e)}")


# ────────────────────────────────────────
# API: 历史分析
# ────────────────────────────────────────
@app.get("/api/history")
async def history(ticker: Optional[str] = None, limit: int = 50):
    """列出历史分析"""
    return list_analyses(ticker=ticker, limit=limit)


@app.get("/api/history/{analysis_id}")
async def history_detail(analysis_id: int):
    """获取单条历史分析"""
    result = get_analysis(analysis_id)
    if not result:
        raise HTTPException(404, "分析不存在")
    return result


@app.get("/api/latest/{ticker}")
async def latest_for_ticker(ticker: str):
    """获取某 ticker 的最新分析"""
    result = get_latest_for_ticker(ticker)
    if not result:
        raise HTTPException(404, f"无 {ticker} 的历史分析")
    return result


# ────────────────────────────────────────
# 健康检查
# ────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": "1.0.0",
        "llm_enabled": bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
        "fred_enabled": bool(os.environ.get("FRED_API_KEY")),
    }


# =============================================================
# Portfolio API (组合管理)
# =============================================================
from database import (
    create_portfolio, list_portfolios, get_portfolio, update_portfolio,
    delete_portfolio, add_position, update_position, delete_position,
    seed_current_holdings,
)


@app.get("/api/portfolio/list")
async def api_list_portfolios():
    """列出所有组合 (含仓位统计)"""
    return list_portfolios()


@app.post("/api/portfolio/seed")
async def api_seed_portfolio(name: str = "AI 产业链核心组合 (2026 H1)", base_capital: float = 100000.0):
    """预置当前 20 只持仓 (一次性, 重复调用会创建多个组合)"""
    pid = seed_current_holdings(name=name, base_capital=base_capital)
    return {"id": pid, "name": name, "message": "已预置 20 只持仓"}


@app.post("/api/portfolio")
async def api_create_portfolio(req: PortfolioCreate):
    """新建组合 (可同时带 positions)"""
    pid = create_portfolio(
        name=req.name,
        base_capital=req.base_capital,
        base_currency=req.base_currency,
        notes=req.notes or "",
    )
    for pos in req.positions:
        add_position(
            portfolio_id=pid,
            ticker=pos.ticker,
            weight_pct=pos.weight_pct,
            cost_basis=pos.cost_basis,
            shares=pos.shares,
            entry_date=pos.entry_date,
            notes=pos.notes or "",
        )
    return {"id": pid, "message": f"组合 {req.name} 已创建"}


@app.get("/api/portfolio/{portfolio_id}")
async def api_get_portfolio(portfolio_id: int):
    """获取组合详情"""
    result = get_portfolio(portfolio_id)
    if not result:
        raise HTTPException(404, f"组合 {portfolio_id} 不存在")
    return result


@app.put("/api/portfolio/{portfolio_id}")
async def api_update_portfolio(portfolio_id: int, req: PortfolioUpdate):
    """更新组合元数据"""
    ok = update_portfolio(
        portfolio_id=portfolio_id,
        name=req.name,
        base_capital=req.base_capital,
        base_currency=req.base_currency,
        notes=req.notes,
    )
    if not ok:
        raise HTTPException(404, f"组合 {portfolio_id} 不存在或无更新")
    return {"message": "已更新"}


@app.delete("/api/portfolio/{portfolio_id}")
async def api_delete_portfolio(portfolio_id: int):
    """删除组合 (级联删除 positions)"""
    ok = delete_portfolio(portfolio_id)
    if not ok:
        raise HTTPException(404, f"组合 {portfolio_id} 不存在")
    return {"message": f"组合 {portfolio_id} 已删除"}


@app.post("/api/portfolio/{portfolio_id}/position")
async def api_add_position(portfolio_id: int, req: PositionCreate):
    """添加/更新持仓 (已存在则更新)"""
    p = get_portfolio(portfolio_id)
    if not p:
        raise HTTPException(404, f"组合 {portfolio_id} 不存在")
    pos_id = add_position(
        portfolio_id=portfolio_id,
        ticker=req.ticker,
        weight_pct=req.weight_pct,
        cost_basis=req.cost_basis,
        shares=req.shares,
        entry_date=req.entry_date,
        notes=req.notes or "",
    )
    return {"id": pos_id, "ticker": req.ticker.upper(), "message": "持仓已添加/更新"}


@app.put("/api/portfolio/{portfolio_id}/position/{ticker}")
async def api_update_position(portfolio_id: int, ticker: str, req: PositionUpdate):
    """更新单只持仓"""
    ok = update_position(
        portfolio_id=portfolio_id,
        ticker=ticker,
        weight_pct=req.weight_pct,
        cost_basis=req.cost_basis,
        shares=req.shares,
        entry_date=req.entry_date,
        notes=req.notes,
    )
    if not ok:
        raise HTTPException(404, f"持仓 {ticker} 不存在或无更新")
    return {"message": f"持仓 {ticker.upper()} 已更新"}


@app.delete("/api/portfolio/{portfolio_id}/position/{ticker}")
async def api_delete_position(portfolio_id: int, ticker: str):
    """删除持仓"""
    ok = delete_position(portfolio_id, ticker)
    if not ok:
        raise HTTPException(404, f"持仓 {ticker} 不存在")
    return {"message": f"持仓 {ticker.upper()} 已删除"}


# ────────────────────────────────────────
# 启动
# ────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

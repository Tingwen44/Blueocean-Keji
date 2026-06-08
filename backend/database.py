"""
database.py
============================================================
SQLite 存储: 1 页纸分析结果 + 历史回溯
============================================================
"""
import os
import sqlite3
import json
from datetime import datetime
from typing import List, Optional
from schemas import OnePagerReport


DEFAULT_DB_PATH = os.environ.get('DATABASE_PATH', '../data/keji.db')


def get_db_path() -> str:
    """确保目录存在,返回绝对路径"""
    path = DEFAULT_DB_PATH
    if not os.path.isabs(path):
        # 相对路径基于 backend 目录
        path = os.path.join(os.path.dirname(__file__), path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def init_db():
    """初始化数据库 schema"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            name TEXT,
            sector TEXT,
            current_price REAL,
            target_price REAL,
            signal TEXT,
            confidence INTEGER,
            one_liner TEXT,
            report_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_ticker ON analyses(ticker)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_created ON analyses(created_at DESC)
    """)
    conn.commit()
    conn.close()
    init_portfolio_tables()


def init_portfolio_tables():
    """组合管理模块的表"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS portfolios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            base_capital REAL DEFAULT 100000,
            base_currency TEXT DEFAULT 'USD',
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            weight_pct REAL NOT NULL,
            cost_basis REAL,
            shares REAL,
            entry_date TEXT,
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pos_portfolio ON positions(portfolio_id)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_pos_ticker ON positions(portfolio_id, ticker)")
    conn.commit()
    conn.close()


def save_analysis(report: OnePagerReport) -> int:
    """保存一份分析到数据库,返回 id"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO analyses (ticker, name, sector, current_price, target_price,
                              signal, confidence, one_liner, report_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        report.ticker,
        report.name,
        report.sector,
        report.current_price,
        report.target_price,
        report.signal,
        report.confidence,
        report.one_liner,
        report.model_dump_json(),
        datetime.now().isoformat(),
    ))
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid


def list_analyses(ticker: Optional[str] = None, limit: int = 50) -> List[dict]:
    """列出历史分析 (可按 ticker 过滤)"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    if ticker:
        cur.execute("""
            SELECT id, ticker, name, sector, current_price, target_price, signal,
                   confidence, one_liner, created_at
            FROM analyses WHERE ticker = ? ORDER BY created_at DESC LIMIT ?
        """, (ticker.upper(), limit))
    else:
        cur.execute("""
            SELECT id, ticker, name, sector, current_price, target_price, signal,
                   confidence, one_liner, created_at
            FROM analyses ORDER BY created_at DESC LIMIT ?
        """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "id": r[0], "ticker": r[1], "name": r[2], "sector": r[3],
            "current_price": r[4], "target_price": r[5], "signal": r[6],
            "confidence": r[7], "one_liner": r[8], "created_at": r[9],
        }
        for r in rows
    ]


def get_analysis(analysis_id: int) -> Optional[dict]:
    """根据 id 拉取完整分析 (含 report_json)"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    cols = [d[0] for d in cur.description]
    result = dict(zip(cols, row))
    # 解析 report_json
    if result.get("report_json"):
        result["report"] = json.loads(result["report_json"])
    return result


def get_latest_for_ticker(ticker: str) -> Optional[dict]:
    """拉取某 ticker 的最新分析"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM analyses WHERE ticker = ? ORDER BY created_at DESC LIMIT 1
    """, (ticker.upper(),))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    cols = [d[0] for d in cur.description]
    result = dict(zip(cols, row))
    if result.get("report_json"):
        result["report"] = json.loads(result["report_json"])
    return result


# =============================================================
# Portfolio CRUD
# =============================================================

def create_portfolio(
    name: str,
    base_capital: float = 100000.0,
    base_currency: str = "USD",
    notes: str = "",
) -> int:
    """新建组合, 返回 portfolio id"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO portfolios (name, base_capital, base_currency, notes)
        VALUES (?, ?, ?, ?)
    """, (name, base_capital, base_currency, notes))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def list_portfolios() -> List[dict]:
    """列出所有组合 (含仓位统计)"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT p.id, p.name, p.base_capital, p.base_currency, p.notes,
               p.created_at, p.updated_at,
               COUNT(pos.id) as position_count,
               COALESCE(SUM(pos.weight_pct), 0) as total_weight
        FROM portfolios p
        LEFT JOIN positions pos ON pos.portfolio_id = p.id
        GROUP BY p.id
        ORDER BY p.created_at DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "id": r[0], "name": r[1], "base_capital": r[2], "base_currency": r[3],
            "notes": r[4], "created_at": r[5], "updated_at": r[6],
            "position_count": r[7], "total_weight_pct": r[8],
        }
        for r in rows
    ]


def get_portfolio(portfolio_id: int) -> Optional[dict]:
    """获取组合详情 (含 positions)"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM portfolios WHERE id = ?", (portfolio_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    cols = [d[0] for d in cur.description]
    result = dict(zip(cols, row))
    # 拉 positions
    cur.execute("""
        SELECT id, ticker, weight_pct, cost_basis, shares, entry_date, notes, created_at
        FROM positions WHERE portfolio_id = ? ORDER BY weight_pct DESC
    """, (portfolio_id,))
    positions = cur.fetchall()
    pcols = [d[0] for d in cur.description]
    result["positions"] = [dict(zip(pcols, p)) for p in positions]
    result["total_weight_pct"] = sum(p["weight_pct"] for p in result["positions"])
    conn.close()
    return result


def update_portfolio(
    portfolio_id: int,
    name: Optional[str] = None,
    base_capital: Optional[float] = None,
    base_currency: Optional[str] = None,
    notes: Optional[str] = None,
) -> bool:
    """更新组合元数据"""
    updates = []
    params = []
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if base_capital is not None:
        updates.append("base_capital = ?")
        params.append(base_capital)
    if base_currency is not None:
        updates.append("base_currency = ?")
        params.append(base_currency)
    if notes is not None:
        updates.append("notes = ?")
        params.append(notes)
    if not updates:
        return False
    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(portfolio_id)
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(f"UPDATE portfolios SET {', '.join(updates)} WHERE id = ?", params)
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


def delete_portfolio(portfolio_id: int) -> bool:
    """删除组合 (级联删除 positions)"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM positions WHERE portfolio_id = ?", (portfolio_id,))
    cur.execute("DELETE FROM portfolios WHERE id = ?", (portfolio_id,))
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


def add_position(
    portfolio_id: int,
    ticker: str,
    weight_pct: float,
    cost_basis: Optional[float] = None,
    shares: Optional[float] = None,
    entry_date: Optional[str] = None,
    notes: str = "",
) -> int:
    """添加持仓 (已存在则更新)"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO positions (portfolio_id, ticker, weight_pct, cost_basis, shares, entry_date, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(portfolio_id, ticker) DO UPDATE SET
            weight_pct = excluded.weight_pct,
            cost_basis = excluded.cost_basis,
            shares = excluded.shares,
            entry_date = excluded.entry_date,
            notes = excluded.notes
    """, (portfolio_id, ticker.upper(), weight_pct, cost_basis, shares, entry_date, notes))
    pos_id = cur.lastrowid
    # 触发 portfolio.updated_at
    cur.execute("UPDATE portfolios SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (portfolio_id,))
    conn.commit()
    conn.close()
    return pos_id


def update_position(
    portfolio_id: int,
    ticker: str,
    weight_pct: Optional[float] = None,
    cost_basis: Optional[float] = None,
    shares: Optional[float] = None,
    entry_date: Optional[str] = None,
    notes: Optional[str] = None,
) -> bool:
    """更新持仓"""
    updates = []
    params = []
    if weight_pct is not None:
        updates.append("weight_pct = ?")
        params.append(weight_pct)
    if cost_basis is not None:
        updates.append("cost_basis = ?")
        params.append(cost_basis)
    if shares is not None:
        updates.append("shares = ?")
        params.append(shares)
    if entry_date is not None:
        updates.append("entry_date = ?")
        params.append(entry_date)
    if notes is not None:
        updates.append("notes = ?")
        params.append(notes)
    if not updates:
        return False
    params.extend([portfolio_id, ticker.upper()])
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(f"UPDATE positions SET {', '.join(updates)} WHERE portfolio_id = ? AND ticker = ?", params)
    ok = cur.rowcount > 0
    if ok:
        cur.execute("UPDATE portfolios SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (portfolio_id,))
    conn.commit()
    conn.close()
    return ok


def delete_position(portfolio_id: int, ticker: str) -> bool:
    """删除持仓"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM positions WHERE portfolio_id = ? AND ticker = ?", (portfolio_id, ticker.upper()))
    ok = cur.rowcount > 0
    if ok:
        cur.execute("UPDATE portfolios SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (portfolio_id,))
    conn.commit()
    conn.close()
    return ok


def seed_current_holdings(
    name: str = "AI 产业链核心组合 (2026 H1)",
    base_capital: float = 100000.0,
) -> int:
    """预置当前 20 只持仓 (上轮实盘配置)

    来源: 6/5 建仓方案 + 后续实操调整
    总权重 110% (1.1x 杠杆)
    """
    holdings = [
        # ticker, weight_pct
        ("NVDA", 3.0),  ("AVGO", 5.0),  ("AMD", 1.0),   ("MRVL", 3.0),
        ("AMZN", 6.0),  ("GOOG", 4.0),  ("ORCL", 4.0),  ("NBIS", 2.0),
        ("SNOW", 2.0),  ("MU", 10.0),   ("SNDK", 20.0), ("LITE", 15.0),
        ("AAOI", 10.0), ("CIEN", 5.0),  ("AXTI", 10.0), ("BE", 1.0),
        ("GEV", 1.0),   ("VST", 3.0),   ("CRWV", 2.0),  ("CIFR", 3.0),
    ]
    pid = create_portfolio(
        name=name,
        base_capital=base_capital,
        base_currency="USD",
        notes="预置: 6/5 建仓方案 (Core 7 + Satellite 11 + Watchlist 9 调整而来). 集中度偏高, SNDK 20% + LITE 15% + AAOI 10% + AXTI 10% 合计 55% 在光通信+存储, 注意风险.",
    )
    for ticker, weight in holdings:
        add_position(
            portfolio_id=pid,
            ticker=ticker,
            weight_pct=weight,
            notes="" if weight < 5 else "高权重, 关注回撤",
        )
    return pid

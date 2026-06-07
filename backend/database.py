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

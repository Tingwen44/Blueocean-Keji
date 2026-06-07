"""
pdf_export.py
============================================================
1 页纸 PDF 导出
============================================================
"""
import io
from datetime import datetime
from schemas import OnePagerReport


def generate_html(report: OnePagerReport) -> str:
    """生成 1 页纸的 HTML (浏览器友好,可右键打印)"""
    fund = report.fundamental
    chain = report.chain
    cal = report.calendar
    rot = report.rotation
    tb = report.top_bottom
    risk = report.risk
    cat = report.catalysts

    # 颜色
    signal_colors = {
        "bullish": "#10b981",
        "neutral_to_bullish": "#22d3ee",
        "neutral": "#6b7280",
        "neutral_to_bearish": "#f59e0b",
        "bearish": "#ef4444",
    }
    sig_color = signal_colors.get(report.signal, "#6b7280")
    sig_label = {
        "bullish": "看多 BULLISH",
        "neutral_to_bullish": "中性偏多",
        "neutral": "中性 NEUTRAL",
        "neutral_to_bearish": "中性偏空",
        "bearish": "看空 BEARISH",
    }.get(report.signal, report.signal)

    def sig_color_2(s):
        return {"bullish": "#10b981", "neutral": "#6b7280", "bearish": "#ef4444"}.get(s, "#6b7280")

    catalysts_html = ""
    for c in cat.catalysts:
        impact_color = {"positive": "#10b981", "negative": "#ef4444", "neutral": "#6b7280"}[c.impact]
        catalysts_html += f"""
        <tr>
          <td>{c.event}</td>
          <td style="white-space:nowrap">{c.date or 'N/A'}</td>
          <td>{c.expected}</td>
          <td style="color:{impact_color}">{c.impact}</td>
          <td>{c.probability}%</td>
        </tr>"""

    signals_html = ""
    for s in tb.signals:
        triggered_label = "✓ 触发" if s.triggered else "— 未触发"
        triggered_color = "#ef4444" if s.triggered else "#6b7280"
        signals_html += f"""
        <tr>
          <td>{s.name}</td>
          <td style="color:{triggered_color}">{triggered_label}</td>
          <td>{s.value or 'N/A'}</td>
          <td style="font-size:11px">{s.note}</td>
        </tr>"""

    risks_html = ""
    for r in risk.risks:
        sev_color = {"high": "#ef4444", "medium": "#f59e0b", "low": "#10b981"}[r.severity]
        risks_html += f"""
        <div style="margin-bottom:6px">
          <span style="background:{sev_color};color:white;padding:1px 6px;border-radius:3px;font-size:10px">{r.severity.upper()}</span>
          <b>{r.description}</b><br>
          <span style="font-size:11px;color:#666">触发信号: {r.trigger_signal}</span>
        </div>"""

    html = f"""
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{report.ticker} 1 页纸</title>
<style>
  body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; padding: 20px; max-width: 1100px; margin: 0 auto; color: #1f2937; line-height: 1.5; }}
  .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid {sig_color}; padding-bottom: 12px; margin-bottom: 16px; }}
  .title {{ font-size: 24px; font-weight: 800; }}
  .ticker {{ font-size: 32px; font-weight: 800; color: {sig_color}; }}
  .signal-badge {{ background: {sig_color}; color: white; padding: 6px 14px; border-radius: 6px; font-size: 14px; font-weight: 700; }}
  .one-liner {{ background: #f3f4f6; padding: 10px 14px; border-left: 4px solid {sig_color}; margin-bottom: 16px; font-size: 14px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px; }}
  .section {{ background: #fafafa; border: 1px solid #e5e7eb; padding: 12px; border-radius: 6px; }}
  .section h3 {{ margin: 0 0 8px 0; font-size: 13px; text-transform: uppercase; color: #6b7280; letter-spacing: 0.5px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 5px 8px; text-align: left; border-bottom: 1px solid #e5e7eb; }}
  th {{ background: #f3f4f6; font-weight: 600; color: #4b5563; }}
  .metric {{ display: flex; justify-content: space-between; padding: 3px 0; font-size: 13px; }}
  .metric .label {{ color: #6b7280; }}
  .signal-pill {{ padding: 1px 6px; border-radius: 3px; font-size: 11px; font-weight: 600; color: white; }}
  .footer {{ margin-top: 16px; padding-top: 10px; border-top: 1px solid #e5e7eb; font-size: 10px; color: #9ca3af; text-align: center; }}
  @media print {{ .no-print {{ display: none; }} body {{ padding: 10px; }} }}
</style></head><body>

<div class="header">
  <div>
    <div class="title">{report.name or report.ticker}</div>
    <div style="color:#6b7280;font-size:13px">{report.ticker} · {report.sector or 'N/A'}</div>
  </div>
  <div style="text-align:right">
    <div class="ticker">${report.current_price or 'N/A'}</div>
    <div style="font-size:12px;color:#6b7280">目标价 ${report.target_price or 'N/A'}</div>
    <div class="signal-badge" style="margin-top:4px">{sig_label} (置信度 {report.confidence})</div>
  </div>
</div>

<div class="one-liner">{report.one_liner}</div>

<div class="grid">
  <div class="section">
    <h3>① 数据快照</h3>
    <div class="metric"><span class="label">市值</span><span>{report.snapshot.mcap_usd_bil or 'N/A'} B$</span></div>
    <div class="metric"><span class="label">52w 区间</span><span>${report.snapshot.fifty_two_week_low or '?'} - ${report.snapshot.fifty_two_week_high or '?'}</span></div>
    <div class="metric"><span class="label">50d MA</span><span>${report.snapshot.fifty_day_ma or '?'}</span></div>
    <div class="metric"><span class="label">200d MA</span><span>${report.snapshot.two_hundred_day_ma or '?'}</span></div>
    <div class="metric"><span class="label">Beta</span><span>{report.snapshot.beta or '?'}</span></div>
    <div class="metric"><span class="label">PE Fwd</span><span>{report.snapshot.pe_forward or '?'} x</span></div>
    <div class="metric"><span class="label">EV/EBITDA</span><span>{report.snapshot.ev_to_ebitda or '?'} x</span></div>
    <div class="metric"><span class="label">毛利率</span><span>{report.snapshot.gross_margin or '?'}%</span></div>
  </div>

  <div class="section">
    <h3>② 4 维基本面扫描</h3>
    <table>
      <tr><th>维度</th><th>信号</th><th>详情</th></tr>
      <tr><td>盈利</td><td><span class="signal-pill" style="background:{sig_color_2(fund.earnings_signal)}">{fund.earnings_signal}</span></td><td>{fund.earnings_detail}</td></tr>
      <tr><td>增长</td><td><span class="signal-pill" style="background:{sig_color_2(fund.growth_signal)}">{fund.growth_signal}</span></td><td>{fund.growth_detail}</td></tr>
      <tr><td>财务</td><td><span class="signal-pill" style="background:{sig_color_2(fund.financial_signal)}">{fund.financial_signal}</span></td><td>{fund.financial_detail}</td></tr>
      <tr><td>估值</td><td><span class="signal-pill" style="background:{sig_color_2(fund.valuation_signal)}">{fund.valuation_signal}</span></td><td>{fund.valuation_detail}</td></tr>
    </table>
    <div style="margin-top:8px;font-size:13px">基本面综合分: <b>{fund.fund_score}/10</b></div>
  </div>

  <div class="section">
    <h3>③ 产业链定位</h3>
    <div class="metric"><span class="label">定位</span><span><b>{chain.bottleneck_label}</b></span></div>
    <div class="metric"><span class="label">主要客户</span><span>{', '.join(chain.customers[:3]) if chain.customers else 'N/A'}</span></div>
    <div class="metric"><span class="label">涨价权</span><span>{chain.pricing_power}</span></div>
    <div class="metric"><span class="label">量价</span><span>{chain.volume_price_trend}</span></div>
    <div class="metric"><span class="label">产业链位置</span><span>{chain.chain_location}</span></div>
    <div class="metric"><span class="label">主线受益</span><span>{chain.mainline_benefit_score}/10</span></div>
    <div style="margin-top:6px;font-size:11px;color:#6b7280;font-style:italic">{chain.llm_suggestion}</div>
  </div>

  <div class="section">
    <h3>④ 催化时点</h3>
    <table>
      <tr><th>事件</th><th>日期</th><th>预期</th><th>影响</th><th>概率</th></tr>
      {catalysts_html or '<tr><td colspan="5" style="text-align:center;color:#9ca3af">未填写</td></tr>'}
    </table>
  </div>

  <div class="section">
    <h3>⑤ 日历 + 事件</h3>
    <div class="metric"><span class="label">当前季度</span><span>{cal.current_quarter}</span></div>
    <div class="metric"><span class="label">距中期选举</span><span>{cal.days_to_midterm_election or '?'} 天</span></div>
    <div class="metric"><span class="label">距鲍威尔卸任</span><span>{cal.days_to_powell_departure or '?'} 天</span></div>
    <div class="metric"><span class="label">日历效应</span><span>{cal.calendar_effect}</span></div>
    <div style="margin-top:6px;font-size:12px;color:#6b7280">周期定位: {cal.position_in_cycle}</div>
  </div>

  <div class="section">
    <h3>⑥ 轮动定位</h3>
    <div class="metric"><span class="label">轮动位置</span><span>{rot.rotation_position}</span></div>
    <div class="metric"><span class="label">轮动链</span><span>{rot.rotation_chain}</span></div>
    <div class="metric"><span class="label">资金流</span><span>{rot.capital_flow}</span></div>
    <div class="metric"><span class="label">相对表现</span><span>{rot.relative_performance}</span></div>
  </div>

  <div class="section">
    <h3>⑦ 见顶/见底信号 ({tb.triggered_count}/{tb.total_count} 触发)</h3>
    <table>
      <tr><th>指标</th><th>状态</th><th>值</th><th>说明</th></tr>
      {signals_html or '<tr><td colspan="4" style="text-align:center;color:#9ca3af">无信号</td></tr>'}
    </table>
    <div style="margin-top:6px;font-size:12px">情绪: <b>{tb.sentiment}</b></div>
  </div>

  <div class="section">
    <h3>⑧ 风险定价</h3>
    {risks_html or '<div style="color:#9ca3af;text-align:center">未填写</div>'}
    <div style="margin-top:8px;font-size:13px">止损线: <b>${risk.stop_loss_price or '未设'} ({(risk.stop_loss_pct or 0):.1f}%)</b></div>
  </div>
</div>

<div class="footer">
  柯基 1 页纸 v1.0 · 基于 BlueOcean Asset 卖方主观分析框架 · {datetime.now().strftime('%Y-%m-%d %H:%M')}<br>
  ⚠️ 免责声明: 本报告由 AI 基于公开数据 + 主观判断生成,不构成投资建议,仅供参考。投资有风险,决策需谨慎。
</div>

<div class="no-print" style="text-align:center;margin-top:20px">
  <button onclick="window.print()" style="padding:8px 20px;background:#3b82f6;color:white;border:none;border-radius:4px;cursor:pointer">打印/保存为 PDF</button>
</div>

</body></html>
"""
    return html


def generate_pdf(report: OnePagerReport) -> bytes:
    """生成 PDF 字节流 (用 weasyprint)"""
    try:
        from weasyprint import HTML
        html_str = generate_html(report)
        pdf_bytes = HTML(string=html_str).write_pdf()
        return pdf_bytes
    except Exception as e:
        # Fallback: 返回 HTML 字节 (前端可转 PDF)
        print(f"PDF generation failed: {e}, returning HTML")
        return generate_html(report).encode("utf-8")

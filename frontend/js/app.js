function appData() {
  return {
    // 状态
    ticker: '',
    loading: false,
    exporting: false,
    showHistory: false,
    activeStep: 1,
    report: null,
    history: [],

    // 表单 (Step 6 + 8 用户填)
    form: {
      rotation_position: 'mid',
      rotation_chain: '',
      capital_flow: '',
      relative_performance: '',
      risks: [
        { severity: 'medium', description: '', trigger_signal: '' },
        { severity: 'medium', description: '', trigger_signal: '' },
        { severity: 'medium', description: '', trigger_signal: '' },
      ],
      stop_loss_price: null,
      stop_loss_pct: null,
    },

    // 8 步流程
    steps: [
      { id: 1, label: '数据快照', status: '✓' },
      { id: 2, label: '4 维基本面', status: '🤖' },
      { id: 3, label: '产业链定位', status: '🤖' },
      { id: 4, label: '催化时点', status: '🤖' },
      { id: 5, label: '日历+事件', status: '🤖' },
      { id: 6, label: '轮动定位', status: '✍' },
      { id: 7, label: '见顶信号', status: '🤖' },
      { id: 8, label: '风险定价', status: '✍' },
    ],

    async init() {
      await this.loadHistory();
    },

    async loadHistory() {
      try {
        const r = await fetch('/api/history?limit=20');
        this.history = await r.json();
      } catch (e) { console.error('loadHistory error:', e); }
    },

    async runAnalysis() {
      if (!this.ticker) return;
      this.loading = true;
      this.activeStep = 1;
      try {
        const r = await fetch(`/api/one-pager/${this.ticker.toUpperCase()}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            use_llm: true,
            save_to_db: true,
            rotation_position: this.form.rotation_position,
            rotation_chain: this.form.rotation_chain,
            capital_flow: this.form.capital_flow,
            relative_performance: this.form.relative_performance,
            risks: this.form.risks.filter(r => r.description),
            stop_loss_price: this.form.stop_loss_price,
            stop_loss_pct: this.form.stop_loss_pct,
            data_gaps: [],
          }),
        });
        if (!r.ok) throw new Error(await r.text());
        const data = await r.json();
        this.report = data.report;
        this.activeStep = 8;  // 跳到最后,看到完整 1 页纸
        await this.loadHistory();
      } catch (e) {
        alert('分析失败: ' + e.message);
        console.error(e);
      } finally {
        this.loading = false;
      }
    },

    async exportOnePager(format) {
      if (!this.ticker) return;
      this.exporting = true;
      try {
        const r = await fetch(`/api/export/${format}/${this.ticker.toUpperCase()}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            use_llm: true,
            save_to_db: false,
            rotation_position: this.form.rotation_position,
            rotation_chain: this.form.rotation_chain,
            capital_flow: this.form.capital_flow,
            relative_performance: this.form.relative_performance,
            risks: this.form.risks.filter(r => r.description),
            stop_loss_price: this.form.stop_loss_price,
            stop_loss_pct: this.form.stop_loss_pct,
          }),
        });
        if (!r.ok) throw new Error(await r.text());
        if (format === 'html') {
          const html = await r.text();
          const blob = new Blob([html], { type: 'text/html' });
          const url = URL.createObjectURL(blob);
          window.open(url, '_blank');
        } else {
          const blob = await r.blob();
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `${this.ticker}_one_pager.pdf`;
          a.click();
        }
      } catch (e) {
        alert('导出失败: ' + e.message);
      } finally {
        this.exporting = false;
      }
    },

    async saveToHistory() {
      await this.runAnalysis();
    },

    async loadHistoryItem(id) {
      try {
        const r = await fetch(`/api/history/${id}`);
        const data = await r.json();
        this.ticker = data.ticker;
        this.report = data.report;
        this.showHistory = false;
        this.activeStep = 8;
      } catch (e) { console.error(e); }
    },

    // 计算属性
    get signalColor() {
      const s = this.report?.signal;
      if (s === 'bullish' || s === 'neutral_to_bullish') return 'text-green-600';
      if (s === 'bearish' || s === 'neutral_to_bearish') return 'text-red-600';
      return 'text-slate-600';
    },

    get signalBg() {
      const s = this.report?.signal;
      if (s === 'bullish') return 'bg-green-500';
      if (s === 'neutral_to_bullish') return 'bg-cyan-500';
      if (s === 'bearish') return 'bg-red-500';
      if (s === 'neutral_to_bearish') return 'bg-orange-500';
      return 'bg-slate-400';
    },

    impactBg(impact) {
      return impact === 'positive' ? 'bg-green-500' : impact === 'negative' ? 'bg-red-500' : 'bg-slate-400';
    },

    get fundamentalRows() {
      const f = this.report?.fundamental;
      if (!f) return [];
      const sig = (s) => s === 'bullish' ? 'bg-green-500' : s === 'bearish' ? 'bg-red-500' : 'bg-slate-400';
      return [
        { name: '盈利', signal: f.earnings_signal, detail: f.earnings_detail, score: f.earnings_score, bg: sig(f.earnings_signal) },
        { name: '增长', signal: f.growth_signal, detail: f.growth_detail, score: f.growth_score, bg: sig(f.growth_signal) },
        { name: '财务', signal: f.financial_signal, detail: f.financial_detail, score: f.financial_score, bg: sig(f.financial_signal) },
        { name: '估值', signal: f.valuation_signal, detail: f.valuation_detail, score: f.valuation_score, bg: sig(f.valuation_signal) },
      ];
    },
  };
}

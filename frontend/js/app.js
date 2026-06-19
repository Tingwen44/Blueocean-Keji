// =============================================================
// localStorage keys
// =============================================================
const LS_LLM = {
  provider: 'keji_llm_provider',
  apiKey: 'keji_llm_api_key',
  model: 'keji_llm_model',
};

function loadLLMSettings() {
  return {
    provider: localStorage.getItem(LS_LLM.provider) || 'off',
    apiKey: localStorage.getItem(LS_LLM.apiKey) || '',
    model: localStorage.getItem(LS_LLM.model) || '',
  };
}

function saveLLMSettings(s) {
  localStorage.setItem(LS_LLM.provider, s.provider);
  if (s.apiKey) localStorage.setItem(LS_LLM.apiKey, s.apiKey);
  else localStorage.removeItem(LS_LLM.apiKey);
  if (s.model) localStorage.setItem(LS_LLM.model, s.model);
  else localStorage.removeItem(LS_LLM.model);
}

function llmHeaders(settings) {
  // 如果用户配了 LLM, 把设置塞到 header
  if (settings.provider && settings.provider !== 'off' && settings.apiKey) {
    return {
      'X-LLM-Provider': settings.provider,
      'X-LLM-Key': settings.apiKey,
      ...(settings.model ? { 'X-LLM-Model': settings.model } : {}),
    };
  }
  return {};
}

// =============================================================
// Alpine.js 组件
// =============================================================
function appData() {
  return {
    // 状态
    ticker: '',
    loading: false,
    exporting: false,
    showHistory: false,
    showSettings: false,
    activeStep: 1,
    report: null,
    history: [],

    // LLM 设置 (从 localStorage 加载)
    llm: loadLLMSettings(),
    llmTesting: false,
    llmTestResult: null,
    showApiKey: false,

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

    // LLM 相关方法
    get llmEnabled() {
      return this.llm.provider && this.llm.provider !== 'off' && this.llm.apiKey;
    },

    get llmStatusLabel() {
      if (this.llm.provider === 'off' || !this.llm.apiKey) return '关闭';
      const p = this.llm.provider === 'openai' ? 'OpenAI' : 'Gemini';
      return p + (this.llm.model ? ` (${this.llm.model})` : '');
    },

    get providerOptions() {
      return [
        { value: 'off', label: '关闭 (仅规则分析)' },
        { value: 'openai', label: 'OpenAI (gpt-4o-mini 默认, 兼容 DeepSeek/其他)' },
        { value: 'gemini', label: 'Google Gemini (gemini-2.5-flash 默认)' },
      ];
    },

    get modelPlaceholder() {
      if (this.llm.provider === 'openai') return 'gpt-4o-mini (或 deepseek-chat, gpt-4o)';
      if (this.llm.provider === 'gemini') return 'gemini-2.5-flash (或 gemini-2.5-pro)';
      return '';
    },

    openSettings() {
      this.showSettings = true;
      this.llmTestResult = null;
    },

    saveSettings() {
      saveLLMSettings(this.llm);
      this.showSettings = false;
    },

    clearApiKey() {
      this.llm.apiKey = '';
      this.llm.model = '';
      saveLLMSettings(this.llm);
    },

    async testLLM() {
      if (!this.llm.apiKey || this.llm.provider === 'off') {
        this.llmTestResult = { ok: false, message: '请先选 provider 并填 API key' };
        return;
      }
      this.llmTesting = true;
      this.llmTestResult = null;
      try {
        const r = await fetch('/api/llm/test', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            provider: this.llm.provider,
            api_key: this.llm.apiKey,
            model: this.llm.model,
          }),
        });
        this.llmTestResult = await r.json();
      } catch (e) {
        this.llmTestResult = { ok: false, message: '网络错误: ' + e.message };
      } finally {
        this.llmTesting = false;
      }
    },

    // 统一 fetch 包装, 自动加 LLM header
    async apiFetch(url, options = {}) {
      options.headers = {
        ...(options.body && !options.headers?.['Content-Type'] ? { 'Content-Type': 'application/json' } : (options.headers || {})),
        ...llmHeaders(this.llm),
        ...(options.headers || {}),
      };
      return fetch(url, options);
    },

    async runAnalysis() {
      if (!this.ticker) return;
      this.loading = true;
      this.activeStep = 1;
      try {
        const r = await this.apiFetch(`/api/one-pager/${this.ticker.toUpperCase()}`, {
          method: 'POST',
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
        const r = await this.apiFetch(`/api/export/${format}/${this.ticker.toUpperCase()}`, {
          method: 'POST',
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

    // Phase A: 情绪分数对应的 Tailwind 颜色
    get sentimentScoreColor() {
      const s = this.report?.top_bottom?.sentiment_score;
      if (s === null || s === undefined) return 'text-slate-400';
      if (s >= 75) return 'text-green-700';      // extreme greed
      if (s >= 55) return 'text-green-600';      // greed
      if (s >= 45) return 'text-yellow-600';     // neutral
      if (s >= 25) return 'text-orange-500';     // fear
      return 'text-red-600';                     // extreme fear
    },

    // Phase B: 蓝海框架 helpers
    get blueOceanSignalLabel() {
      const s = this.report?.blue_ocean?.overall?.signal;
      const map = {
        strong_buy_ready: '✓ 5 维好 + 信息丰富, 可建仓',
        investable: '可投, 关注催化',
        wait_for_catalyst: '⏸ 等催化, 中性',
        avoid: '✗ 不建议',
      };
      return map[s] || 'N/A';
    },
    get blueOceanSignalColor() {
      const s = this.report?.blue_ocean?.overall?.signal;
      if (s === 'strong_buy_ready') return 'text-green-700';
      if (s === 'investable') return 'text-blue-600';
      if (s === 'wait_for_catalyst') return 'text-yellow-600';
      if (s === 'avoid') return 'text-red-600';
      return 'text-slate-500';
    },
    mpevlScoreColor(score) {
      if (score >= 7) return 'bg-green-500 text-white';
      if (score >= 5) return 'bg-yellow-400 text-slate-800';
      if (score >= 3) return 'bg-orange-400 text-white';
      return 'bg-red-500 text-white';
    },
    mpevlBarColor(score) {
      if (score >= 7) return 'bg-green-500';
      if (score >= 5) return 'bg-yellow-400';
      if (score >= 3) return 'bg-orange-400';
      return 'bg-red-500';
    },
    infoGapBorderColor(level) {
      const map = {
        S: 'border-amber-300 bg-amber-50',
        A: 'border-slate-300 bg-slate-50',
        B: 'border-blue-300 bg-blue-50',
        C: 'border-slate-200 bg-slate-50',
      };
      return map[level] || 'border-slate-200';
    },
    infoGapTextColor(level) {
      const map = {
        S: 'text-amber-700',
        A: 'text-slate-700',
        B: 'text-blue-700',
        C: 'text-slate-500',
      };
      return map[level] || 'text-slate-500';
    },

    // Phase C: 轮动定位 helper
    get rotationAutoColor() {
      const p = this.report?.rotation?.auto_metrics?.auto_position;
      if (p === 'leading') return 'text-green-700';
      if (p === 'mid') return 'text-blue-600';
      if (p === 'late') return 'text-orange-500';
      if (p === 'catchup') return 'text-red-600';
      return 'text-slate-500';
    },
    rotationSubName(key) {
      const map = {
        sector_relative: '① 板块相对强弱',
        fund_heat: '② 板块资金热度',
        google_trend: '③ 谷歌搜索指数',
        ticker_relative: '④ 个股相对表现',
      };
      return map[key] || key;
    },

    // Phase D: 风险评分 helper
    get riskSignalColor() {
      const s = this.report?.risk?.auto_scores?.signal;
      if (s === 'extreme_risk') return 'text-red-700';
      if (s === 'high_risk') return 'text-red-600';
      if (s === 'medium_risk') return 'text-orange-500';
      if (s === 'low_risk') return 'text-green-600';
      return 'text-slate-500';
    },
    riskSubName(key) {
      const map = {
        macro: '① 宏观风险',
        sector: '② 行业风险',
        competitor: '③ 竞争对手风险',
        company: '④ 公司内部风险',
      };
      return map[key] || key;
    },
  };
}

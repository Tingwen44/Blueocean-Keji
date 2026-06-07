# 柯基 1 页纸 (Keji One-Pager)

> 基于 BlueOcean Asset 卖方主观分析框架的个股分析工具
> 一键生成 8 步流程 + 1 页纸可执行分析报告

## 快速开始 (本地)

```bash
# 1. 装依赖
python -m pip install -r backend/requirements.txt

# 2. 启动后端
cd backend
python app.py
# → http://localhost:8000

# 3. 打开前端
# 浏览器打开 frontend/index.html
# 或用 python -m http.server 8080
```

## 环境变量

```bash
OPENAI_API_KEY=sk-...           # LLM 辅助(产业链定位 + 催化扫描)
FRED_API_KEY=...                 # 宏观数据(可选, 免费申请)
```

## 项目结构

```
keji-one-pager/
├── backend/          # FastAPI 后端
│   ├── app.py        # 主入口
│   ├── data_fetcher.py
│   ├── scoring.py
│   ├── llm_helper.py
│   ├── pdf_export.py
│   ├── database.py
│   └── requirements.txt
├── frontend/         # SPA 前端
│   ├── index.html
│   ├── css/
│   └── js/
├── data/             # SQLite 数据库
├── .env.example
└── README.md
```

## 8 步流程

1. **数据拉取** (yfinance) - 价格/财务/估值
2. **4 维基本面扫描** - 盈利/增长/财务/估值
3. **产业链定位** (LLM 半自动) - 瓶颈/卖铲子/非瓶颈
4. **催化时点** (LLM + 手动) - 6 个月内关键事件
5. **日历+事件** - 1H26 宽松交易窗口等
6. **轮动定位** - 在产业链轮动中的位置
7. **见顶/见底信号** - 30 个量化指标族
8. **风险定价** - 3 个关键风险 + 止损线

## 输出

- 1 页纸 HTML(浏览器查看)
- 1 页纸 PDF(下载分享)
- 存档到 SQLite(历史回溯)

## 部署

参考 `DEPLOY.md`(Railway 一键部署)

# Railway 部署 (D2=C)

## 1 步: Railway 关联 GitHub

访问 https://railway.app/new

- "Deploy from GitHub repo"
- 选 `Tingwen44/Blueocean-Keji`
- Railway 自动检测 Python,会自动跑 `pip install -r backend/requirements.txt`
- 启动命令: `cd backend && python app.py`(railway.toml 已配)

## 2 步: 配环境变量

Railway → Service → Variables, 添加:

| 变量 | 值 |
|---|---|
| `OPENAI_API_KEY` | `sk-...` (你的 OpenAI key) |
| `FRED_API_KEY` | (可选, 申请 https://fred.stlouisfed.org/docs/api/api_key.html) |
| `PORT` | Railway 自动注入, 不用设 |

## 3 步: 加持久卷 (D5=A)

Railway → Service → Settings → Volumes

- Mount Path: `/app/data`
- Size: 1GB

这样 SQLite 文件就持久化了, 重新部署不丢。

## 4 步: 等部署完成 + 验证

Railway 会生成 URL: `https://blueocean-keji.up.railway.app`

访问应该看到前端 SPA。

健康检查: `https://blueocean-keji.up.railway.app/api/health`

返回:
```json
{
  "status": "ok",
  "version": "1.0.0",
  "llm_enabled": true,
  "fred_enabled": true
}
```

## 5 步: 测一只股票

1. 打开 Railway URL
2. 输入 "COHR" 或 "NVDA"
3. 等待 5-10 秒
4. 看 8 步流程 + 1 页纸
5. 点 "导出 HTML" 或 "导出 PDF"

## 注意事项

- Railway 免费额度: $5/月 (够个人用)
- 国内访问可能慢,可考虑 Cloudflare 代理
- yfinance 需代理 (国内): Railway 服务器在海外,可能不需要,先测
- SQLite 卷 1GB 约可存 50 万份分析,够用

## 本地 vs 云端

- 本地: `cd backend && python app.py` → http://localhost:8000
- 云端: Railway URL
- 数据: 两端独立 (本地 SQLite 一个文件,云端一个文件)

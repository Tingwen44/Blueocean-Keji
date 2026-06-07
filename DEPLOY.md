# 一键部署到 Railway

## 步骤

### 1. 推送代码到 GitHub
```bash
git remote add origin https://github.com/你的用户名/keji-one-pager.git
git branch -M main
git push -u origin main
```

### 2. Railway 部署
1. 访问 https://railway.app
2. "New Project" → "Deploy from GitHub repo"
3. 选择 keji-one-pager
4. 等待自动部署完成

### 3. 配置环境变量
在 Railway dashboard → Variables,添加:
- `OPENAI_API_KEY` = sk-...
- `FRED_API_KEY` = (可选)
- `PORT` = 8000

### 4. 添加持久化卷
Railway → Service → "Add Volume"
- Mount Path: `/app/data`
- Size: 1GB

### 5. 验证
Railway 会生成一个 URL,如 `https://keji-one-pager.up.railway.app`
访问该 URL 即可使用。

## 注意事项

- Railway 免费额度: $5/月(够用)
- 持久化卷: SQLite 文件存在卷里,重启不丢
- 国内访问: 可能需要 Cloudflare 代理

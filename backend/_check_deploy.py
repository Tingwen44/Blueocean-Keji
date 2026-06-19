"""检查 Railway 部署状态"""
import os
import sys
import httpx
from pathlib import Path

# 从 .env 读 token
env_path = Path(__file__).parent.parent / ".env"
token = None
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("RAILWAY_TOKEN="):
            token = line.split("=", 1)[1].strip()
            break

if not token:
    print("NO TOKEN")
    sys.exit(1)

print(f"Token: {token[:8]}...{token[-4:]} (length: {len(token)})")

# 列最近 5 个部署
r = httpx.post(
    "https://backboard.railway.app/graphql/v2",
    json={"query": "{ deployments(first: 5) { edges { node { id status createdAt project { name } } } } }"},
    headers={"Authorization": f"Bearer {token}"},
    timeout=15,
)
data = r.json()
deploys = data.get("data", {}).get("deployments", {}).get("edges", [])
if not deploys:
    print(f"No deployments or error: {data}")
    sys.exit(1)

for d in deploys:
    n = d["node"]
    p = n.get("project") or {}
    proj = p.get("name", "?") if isinstance(p, dict) else "?"
    print(f"  {n['status']:12s} {n['createdAt']} project={proj} id={n['id'][:8]}")

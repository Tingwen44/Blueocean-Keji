"""
Railway 配置脚本 (一次性):
1. 列出所有项目, 找 BlueOcean-Keji
2. 找到 service + environment IDs
3. 设置 FINNHUB_API_KEY 环境变量
4. (可选) 触发 redeploy

用法: python _railway_setup.py
"""
import os
import sys
import json
import httpx
from pathlib import Path

# 从 env var 或 .env 读 token
token = os.environ.get("RAILWAY_TOKEN")
if not token:
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("RAILWAY_TOKEN="):
                token = line.split("=", 1)[1].strip()
                break

if not token:
    print("ERROR: RAILWAY_TOKEN not set")
    print("Run: RAILWAY_TOKEN=*** _railway_setup.py")
    sys.exit(1)

print(f"Token loaded: {token[:8]}...{token[-4:]} (length: {len(token)})")

RAILWAY_API = "https://backboard.railway.app/graphql/v2"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}",
}


def gql(query: str, variables: dict = None) -> dict:
    """执行 GraphQL query"""
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    r = httpx.post(RAILWAY_API, json=payload, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


# 1) 列出所有项目
print("\n=== 1) 列出所有项目 ===")
res = gql("""
    query {
        projects {
            edges {
                node {
                    id
                    name
                    description
                    services { edges { node { id name } } }
                    environments { edges { node { id name } } }
                    deployments { edges { node { id status url } } }
                }
            }
        }
    }
""")

projects = res.get("data", {}).get("projects", {}).get("edges", [])
for p in projects:
    n = p["node"]
    print(f"\n  📦 {n['name']} ({n['id']})")
    print(f"     desc: {n.get('description', '(none)')}")
    for s in n.get("services", {}).get("edges", []):
        print(f"     service: {s['node']['name']} ({s['node']['id']})")
    for e in n.get("environments", {}).get("edges", []):
        print(f"     env: {e['node']['name']} ({e['node']['id']})")
    for d in n.get("deployments", {}).get("edges", [])[:1]:
        print(f"     deploy: {d['node']['status']} url={d['node'].get('url', '?')}")

# 2) 自动识别 BlueOcean-Keji 项目
print("\n=== 2) 找 BlueOcean-Keji 项目 ===")
target = None
for p in projects:
    n = p["node"]
    name = (n.get("name") or "").lower()
    desc = (n.get("description") or "").lower()
    if "keji" in name or "keji" in desc or "blueocean" in name or "blueocean" in desc or "blue" in name:
        target = n
        print(f"  ✓ 命中: {n['name']}")
        break

# 也检查部署 URL 是否匹配 keji-one-pager / blueocean
if not target:
    for p in projects:
        n = p["node"]
        for d in n.get("deployments", {}).get("edges", []):
            url = d["node"].get("url") or ""
            if "keji" in url or "blueocean" in url or "blue" in url:
                target = n
                print(f"  ✓ 通过部署 URL 命中: {n['name']} (url: {url})")
                break
        if target:
            break

if not target:
    print("  ✗ 没自动找到, 请看上面列表手动指定")
    sys.exit(1)

# 3) 拿 service 和 environment
services = target.get("services", {}).get("edges", [])
environments = target.get("environments", {}).get("edges", [])

if not services or not environments:
    print(f"  ✗ 项目 {target['name']} 缺 service 或 environment")
    sys.exit(1)

service = services[0]["node"]
environment = environments[0]["node"]  # 通常是 production

print(f"\n=== 3) 准备设置环境变量 ===")
print(f"  project:    {target['name']} ({target['id']})")
print(f"  service:    {service['name']} ({service['id']})")
print(f"  environment: {environment['name']} ({environment['id']})")

# 4) 读 .env 拿 FINNHUB_API_KEY
finnhub_key = os.environ.get("FINNHUB_API_KEY")
if not finnhub_key:
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("FINNHUB_API_KEY="):
                finnhub_key = line.split("=", 1)[1].strip()
                break

if not finnhub_key:
    print("  ✗ FINNHUB_API_KEY 不在 .env")
    sys.exit(1)

print(f"  FINNHUB_API_KEY: {finnhub_key[:8]}...{finnhub_key[-4:]} (length: {len(finnhub_key)})")

# 5) 设置环境变量
print(f"\n=== 4) 设置 FINNHUB_API_KEY ===")
res = gql("""
    mutation VariableUpsert($input: VariableUpsertInput!) {
        variableUpsert(input: $input)
    }
""", {
    "input": {
        "projectId": target["id"],
        "environmentId": environment["id"],
        "serviceId": service["id"],
        "name": "FINNHUB_API_KEY",
        "value": finnhub_key,
    }
})

if res.get("errors"):
    print(f"  ✗ 设置失败: {res['errors']}")
    sys.exit(1)
else:
    print(f"  ✅ FINNHUB_API_KEY 已设置到 {target['name']} / {environment['name']}")

# 6) 验证一下
print(f"\n=== 5) 验证环境变量已设置 ===")
res = gql("""
    query Vars($projectId: String!, $environmentId: String!) {
        variables(projectId: $projectId, environmentId: $environmentId, serviceId: null)
    }
""".replace("$projectId: String!", "$projectId: String!").replace("$environmentId: String!", "$environmentId: String!"), {
    "projectId": target["id"],
    "environmentId": environment["id"],
})

# Railway variables query 可能 schema 不同, 用 serviceVariables
res = gql("""
    query Vars($projectId: String!, $environmentId: String!, $serviceId: String!) {
        variables(projectId: $projectId, environmentId: $environmentId, serviceId: $serviceId)
    }
""", {
    "projectId": target["id"],
    "environmentId": environment["id"],
    "serviceId": service["id"],
})

if res.get("data", {}).get("variables"):
    found = False
    for v in res["data"]["variables"]:
        if v["name"] == "FINNHUB_API_KEY":
            print(f"  ✅ 验证通过: FINNHUB_API_KEY = {v['value'][:8]}...{v['value'][-4:]}")
            found = True
            break
    if not found:
        print(f"  ⚠️ 变量列表里没找到 FINNHUB_API_KEY (可能 set 失败或 query 错误)")
        print(f"  当前变量: {[v['name'] for v in res['data']['variables']]}")
else:
    print(f"  ⚠️ 验证 query 没拿到结果: {res}")

print(f"\n=== 完成 ===")
print(f"下一步: git push 触发 Railway 自动部署 (或手动 Redeploy)")

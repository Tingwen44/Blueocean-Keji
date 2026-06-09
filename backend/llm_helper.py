"""
llm_helper.py
============================================================
LLM 辅助 (OpenAI / Gemini / DeepSeek 通用接口)
- Step 3: 产业链定位
- Step 4: 催化扫描

环境变量:
  LLM_PROVIDER = openai | gemini  (默认 openai)
  OPENAI_API_KEY = ... (OpenAI 用)
  OPENAI_BASE_URL = ... (DeepSeek 等 OpenAI 兼容用)
  OPENAI_MODEL = gpt-4o-mini (默认)
  GOOGLE_API_KEY = ... (Gemini 用, 也可写 GEMINI_API_KEY)
  GEMINI_MODEL = gemini-2.5-pro (默认)
============================================================
"""
import os
import json
import httpx
from typing import Optional, Tuple
from schemas import StockSnapshot, ChainPositioning, CatalystsBlock, Catalyst


def _setup_proxy():
    """在本地开发时, 如果没设代理且能连上 127.0.0.1:7890, 自动配上 (仅本地便利)
    Railway/云端: 由用户自己设 HTTP_PROXY env var, 这里不强制
    """
    # 检测是否在云端 (Railway 注入 PORT 或 RAILWAY_ENVIRONMENT)
    if os.environ.get('PORT') or os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('RENDER'):
        return  # 云端: 不动, 用户自己配
    # 本地: 只在用户没设过且 7890 端口可达时, 自动加
    if not os.environ.get('HTTP_PROXY'):
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.3)
            s.connect(('127.0.0.1', 7890))
            s.close()
            os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7890'
            os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'
        except Exception:
            pass  # 连不上就别管, 走直连


def _get_provider(provider: Optional[str] = None) -> str:
    """获取 provider, 优先用入参, 其次 env"""
    if provider:
        return provider.lower().strip()
    return os.environ.get('LLM_PROVIDER', 'openai').lower().strip()


def _is_available(provider: Optional[str] = None, api_key: Optional[str] = None) -> bool:
    """检查当前 provider 的 API key 是否就绪 (允许覆盖)"""
    p = _get_provider(provider)
    if api_key:
        return True  # 显式传了 key 就当作可用
    if p == 'gemini':
        return bool(os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY'))
    return bool(os.environ.get('OPENAI_API_KEY'))


def call_llm_json(
    system: str,
    user: str,
    temperature: float = 0.3,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[dict]:
    """
    统一 LLM 调用接口,返回 parsed JSON dict
    - OpenAI 兼容: OpenAI / DeepSeek
    - Gemini: 直接 HTTP API (避开 SDK 在国内的卡顿)
    - provider/api_key/model 可选, 不传则用 env 默认
    """
    _setup_proxy()
    p = _get_provider(provider)

    try:
        if p == 'gemini':
            return _call_gemini_json(system, user, temperature, api_key=api_key, model=model)
        else:
            return _call_openai_json(system, user, temperature, api_key=api_key, model=model)
    except Exception as e:
        print(f"LLM call error ({p}): {e}")
        return None


def _call_openai_json(
    system: str, user: str, temperature: float,
    api_key: Optional[str] = None, model: Optional[str] = None,
) -> Optional[dict]:
    key = api_key or os.environ.get('OPENAI_API_KEY')
    if not key:
        return None
    base_url = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
    m = model or os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')

    from openai import OpenAI
    client = OpenAI(api_key=key, base_url=base_url)
    resp = client.chat.completions.create(
        model=m,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=temperature,
    )
    text = resp.choices[0].message.content
    return json.loads(text)


def _call_gemini_json(
    system: str, user: str, temperature: float,
    api_key: Optional[str] = None, model: Optional[str] = None,
) -> Optional[dict]:
    key = api_key or os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')
    if not key:
        return None
    m = model or os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')

    url = f'https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}'
    # Gemini 的 system 指令合并到 user 里
    combined = f"[System]\n{system}\n\n[User]\n{user}"

    payload = {
        "contents": [{"parts": [{"text": combined}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": temperature,
        }
    }

    with httpx.Client(timeout=60.0) as c:
        r = c.post(url, json=payload)
    if r.status_code != 200:
        print(f"Gemini API error {r.status_code}: {r.text[:200]}")
        return None

    data = r.json()
    text = data['candidates'][0]['content']['parts'][0]['text']
    # Gemini 偶尔会在 JSON 外包 ```json ... ``` 标记,剥掉
    text = text.strip()
    if text.startswith('```'):
        text = text.split('```', 2)[1]
        if text.startswith('json'):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


# ────────────────────────────────────────
# Step 3: 产业链定位 (LLM 半自动)
# ────────────────────────────────────────
CHAIN_POSITIONING_PROMPT = """你是一名资深卖方股票分析师,擅长判断公司在产业链中的位置。

分析公司: {ticker} - {name}
行业: {sector} / {industry}
主营业务摘要: {summary}

请判断这家公司在产业链中的位置,按以下 4 类之一:
1. **bottleneck_pqp** (瓶颈 + 量价齐升): 产业链上供给紧张、可涨价、量价齐升的环节, 如: AI 电力、EML 光芯片、HBM、稀有金属
2. **bottleneck_vol** (瓶颈 + 量稳定): 卖铲子型, 需求确定但单价稳定, 如: 台积电、EUV 准分子激光、代工厂
3. **non_bottleneck** (非瓶颈 + 高增长): 主题轮动型, 高增长但无定价权, 估值贵, 易暴跌, 如: AI 应用 SaaS、初创新势力
4. **toolmaker** (工具/基础设施): 中性, 不卡脖子的工具型公司

输出 JSON 格式:
{{
  "bottleneck_level": "bottleneck_pqp/bottleneck_vol/non_bottleneck/toolmaker",
  "bottleneck_label": "中文短标签 (如: 瓶颈+量价齐升, 卖铲子型等)",
  "customers": ["主要客户1", "主要客户2", "..."] ,
  "pricing_power": "strong/medium/weak",
  "volume_price_trend": "pqp/vp_stable/vp_down",
  "chain_location": "产业链位置描述 (上游/中游/下游 + 哪个环节)",
  "mainline_benefit_score": 0-10 的整数 (主线受益度, AI/电力/存储/创新药 等),
  "llm_suggestion": "1-2 句话解释判断理由"
}}
"""


def suggest_chain_positioning(
    snap: StockSnapshot,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[ChainPositioning]:
    """LLM 建议产业链定位 (用户可在前端确认/修改)"""
    if not _is_available(provider, api_key):
        return None

    summary = (snap.business_summary or snap.description or "")[:1000]

    system = "你是卖方股票分析师,只输出 JSON,不要其他文字。"
    user = CHAIN_POSITIONING_PROMPT.format(
        ticker=snap.ticker,
        name=snap.name or snap.ticker,
        sector=snap.sector or "N/A",
        industry=snap.industry or "N/A",
        summary=summary,
    )

    data = call_llm_json(system, user, temperature=0.3, provider=provider, api_key=api_key, model=model)
    if not data:
        return None
    return ChainPositioning(
        ticker=snap.ticker,
        bottleneck_level=data.get("bottleneck_level", "non_bottleneck"),
        bottleneck_label=data.get("bottleneck_label", ""),
        customers=data.get("customers", []),
        pricing_power=data.get("pricing_power", "medium"),
        volume_price_trend=data.get("volume_price_trend", "vp_stable"),
        chain_location=data.get("chain_location", ""),
        mainline_benefit_score=int(data.get("mainline_benefit_score", 5)),
        llm_suggestion=data.get("llm_suggestion", ""),
        user_confirmed=False,
    )


# ────────────────────────────────────────
# Step 4: 催化扫描 (LLM 半自动)
# ────────────────────────────────────────
CATALYSTS_PROMPT = """你是卖方股票分析师,识别未来 6 个月内可能影响股价的关键催化事件。

公司: {ticker} - {name}
行业: {sector}
当前日期: {today}

请识别 1-3 个最可能影响股价的催化事件(财报、订单、产品、政策、BD 收购、监管等)。

输出 JSON 格式:
{{
  "catalysts": [
    {{
      "event": "事件描述",
      "date": "预期日期 (YYYY-MM-DD 或 Q?CY 格式)",
      "expected": "市场预期 (具体数字或定性)",
      "impact": "positive/negative/neutral",
      "probability": 0-100 整数 (发生概率),
      "source": "信息源 (财报/SEC 文件/媒体报道/分析师等)"
    }}
  ]
}}
"""


def suggest_catalysts(
    snap: StockSnapshot,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[CatalystsBlock]:
    """LLM 建议未来 6 个月催化"""
    if not _is_available(provider, api_key):
        return None

    from datetime import date
    system = "你是卖方股票分析师,只输出 JSON,不要其他文字。"
    user = CATALYSTS_PROMPT.format(
        ticker=snap.ticker,
        name=snap.name or snap.ticker,
        sector=snap.sector or "N/A",
        today=date.today().isoformat(),
    )

    data = call_llm_json(system, user, temperature=0.4, provider=provider, api_key=api_key, model=model)
    if not data:
        return None

    catalysts_data = data.get("catalysts", [])
    catalysts = [Catalyst(**c) for c in catalysts_data[:3] if isinstance(c, dict)]

    score = 0
    if catalysts:
        avg = sum(c.probability for c in catalysts) / len(catalysts)
        score = min(10, int(avg / 10))

    return CatalystsBlock(
        ticker=snap.ticker,
        catalysts=catalysts,
        total_score=score,
    )

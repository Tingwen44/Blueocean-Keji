"""
llm_helper.py
============================================================
LLM 辅助 (OpenAI / Claude / DeepSeek 通用接口)
- Step 3: 产业链定位
- Step 4: 催化扫描
============================================================
"""
import os
import json
from typing import Optional
from schemas import StockSnapshot, ChainPositioning, CatalystsBlock, Catalyst


def _setup_proxy():
    if not os.environ.get('HTTP_PROXY'):
        os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7890'
        os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'


def _get_client():
    """获取 LLM 客户端 (统一用 OpenAI 兼容接口)"""
    _setup_proxy()
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        return None

    # 默认用 OpenAI; 如果用 DeepSeek 改 base_url
    base_url = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')

    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key, base_url=base_url)
    except Exception as e:
        print(f"LLM client error: {e}")
        return None


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


def suggest_chain_positioning(snap: StockSnapshot) -> Optional[ChainPositioning]:
    """LLM 建议产业链定位 (用户可在前端确认/修改)"""
    client = _get_client()
    if not client:
        return None

    summary = (snap.business_summary or snap.description or "")[:1000]

    prompt = CHAIN_POSITIONING_PROMPT.format(
        ticker=snap.ticker,
        name=snap.name or snap.ticker,
        sector=snap.sector or "N/A",
        industry=snap.industry or "N/A",
        summary=summary,
    )

    try:
        model = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是卖方股票分析师,只输出 JSON,不要其他文字。"},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        content = resp.choices[0].message.content
        data = json.loads(content)
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
    except Exception as e:
        print(f"LLM chain positioning error: {e}")
        return None


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


def suggest_catalysts(snap: StockSnapshot) -> Optional[CatalystsBlock]:
    """LLM 建议未来 6 个月催化"""
    client = _get_client()
    if not client:
        return None

    prompt = CATALYSTS_PROMPT.format(
        ticker=snap.ticker,
        name=snap.name or snap.ticker,
        sector=snap.sector or "N/A",
    )

    try:
        model = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是卖方股票分析师,只输出 JSON,不要其他文字。"},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
        )
        content = resp.choices[0].message.content
        data = json.loads(content)
        catalysts_data = data.get("catalysts", [])
        catalysts = [Catalyst(**c) for c in catalysts_data[:3]]

        # 总分
        score = 0
        for c in catalysts:
            score += c.probability
        score = min(10, score // max(1, len(catalysts)) // 10)

        return CatalystsBlock(
            ticker=snap.ticker,
            catalysts=catalysts,
            total_score=score,
        )
    except Exception as e:
        print(f"LLM catalysts error: {e}")
        return None

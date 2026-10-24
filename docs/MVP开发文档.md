# 企业画像 × 产业链图谱融合分析平台 — MVP 详细开发文档

> 版本：v1.0 | 日期：2025-01 | 适用阶段：MVP（4-6周交付）

---

## 一、可行性分析结论

### 1.1 总体判断：**可行，建议推进**

| 维度 | 评估 | 说明 |
|------|------|------|
| 技术可行性 | ✅ 高 | Prompt 设计成熟，JSON Schema 输出可稳定解析，CoT 推理路径在 GPT-4/Claude 级别模型上表现稳定 |
| 业务价值 | ✅ 高 | 招商局、投资机构、产业规划部均有明确需求，决策建议矩阵直接可执行 |
| 数据依赖 | ⚠️ 中 | 核心瓶颈在于企业画像 + 产业链图谱双数据源的获取与整合，MVP 阶段可用 Mock 数据验证流程 |
| 工程复杂度 | ✅ 低-中 | 核心逻辑是 LLM 调用 + 结构化渲染，无需复杂算法；前端展示模块工作量适中 |
| 合规风险 | ⚠️ 低 | 分析结论仅供参考，需标注"AI 辅助分析，不构成投资建议" |

### 1.2 主要风险与应对

**风险 1：LLM 评分一致性差**
- 应对：在 Prompt 中嵌入锚点示例（Few-Shot），对同一企业多次调用取均值或众数，评分差异 > 1.5 分时触发人工复核标记

**风险 2：数据不完整导致置信度低**
- 应对：数据预处理层计算 `completeness_score`，前端展示 ⚠️ 警告；字段缺失时用规则引擎填充保守默认值

**风险 3：产业链图谱数据缺乏**
- 应对：MVP 阶段内置 3-5 条典型产业链的静态数据（新能源汽车、半导体、生物医药），验证端到端流程后再接入外部图谱 API

---

## 二、MVP 范围定义

### 2.1 In Scope（MVP 必须交付）

- [ ] 企业查询入口：输入企业名称，返回分析报告
- [ ] 数据层：Mock 企业画像数据 + 静态产业链图谱（3条链）
- [ ] AI 分析引擎：完整 System Prompt 调用，返回结构化 JSON
- [ ] 前端展示：产业链定位卡片 + 五维雷达图 + 决策建议面板 + 推理溯源
- [ ] 对话式追问：基于分析结果的上下文对话
- [ ] 快捷指令：`/explain` `/compare` `/report`

### 2.2 Out of Scope（MVP 暂不交付）

- 对接真实企业画像 API（天眼查、企查查）
- 对接真实产业链图谱数据库
- 用户权限管理 / 多租户
- 批量分析 / 定时刷新
- 与 BI/CRM 系统集成

---

## 三、系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端（React + Vite）                       │
│  ┌──────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────┐  │
│  │ 查询入口  │  │ 分析报告页面  │  │ 对话助手   │  │ 对比面板 │  │
│  └────┬─────┘  └──────┬───────┘  └─────┬──────┘  └────┬─────┘  │
└───────┼────────────────┼────────────────┼───────────────┼────────┘
        │                │                │               │
        └────────────────┴────────────────┴───────────────┘
                                  │ REST API / SSE
┌─────────────────────────────────▼───────────────────────────────┐
│                    后端（FastAPI + Python）                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │               Context Assembly Service                    │   │
│  │  · 企业画像查询（Mock / 外部 API）                         │   │
│  │  · 产业链图谱匹配（静态 JSON / 图数据库）                   │   │
│  │  · 数据融合预处理（匹配度计算 / 质量评估 / 异常检测）        │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  LLM Analysis Engine                      │   │
│  │  · System Prompt 管理                                     │   │
│  │  · Few-Shot 示例注入                                       │   │
│  │  · LLM 调用（OpenAI / Azure / Anthropic）                  │   │
│  │  · 输出解析与校验（JSON Schema Validation）                 │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  Cache & Storage                          │   │
│  │  · Redis（分析结果缓存，TTL 24h）                          │   │
│  │  · SQLite / PostgreSQL（历史记录）                         │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 四、技术选型

| 层级 | 技术 | 版本 | 选型理由 |
|------|------|------|---------|
| 前端框架 | React | 18.x | 生态丰富，组件复用性强 |
| 前端构建 | Vite | 5.x | 开发启动快，HMR 友好 |
| UI 组件库 | shadcn/ui + Tailwind CSS | latest | 可定制性强，无样式锁定 |
| 图表库 | Recharts | 2.x | React 原生，雷达图支持好 |
| 后端框架 | FastAPI | 0.111.x | 异步支持好，自动生成 OpenAPI 文档 |
| LLM 调用 | openai SDK | 1.x | 兼容 OpenAI / Azure / 本地模型 |
| 数据验证 | Pydantic v2 | 2.x | 与 FastAPI 深度集成，JSON Schema 校验 |
| 缓存 | Redis | 7.x | 分析结果缓存，避免重复 LLM 调用 |
| 持久化 | SQLite（MVP）/ PostgreSQL（生产） | — | MVP 阶段 SQLite 零配置 |
| 部署 | Docker Compose | — | 前后端一键启动 |

---

## 五、目录结构

```
firestone-demo/
├── frontend/                    # React 前端
│   ├── src/
│   │   ├── components/
│   │   │   ├── SearchBar.tsx          # 企业查询入口
│   │   │   ├── ReportCard.tsx         # 分析摘要卡片
│   │   │   ├── ChainPositioning.tsx   # 产业链定位组件
│   │   │   ├── RadarChart.tsx         # 五维雷达图
│   │   │   ├── DecisionPanel.tsx      # 决策建议面板
│   │   │   ├── ReasoningTrace.tsx     # 推理溯源组件
│   │   │   └── ChatAssistant.tsx      # 对话式分析助手
│   │   ├── pages/
│   │   │   ├── HomePage.tsx
│   │   │   └── AnalysisPage.tsx
│   │   ├── hooks/
│   │   │   ├── useAnalysis.ts
│   │   │   └── useChat.ts
│   │   ├── lib/
│   │   │   ├── api.ts                 # API 调用封装
│   │   │   └── types.ts               # TypeScript 类型定义
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
│
├── backend/                     # FastAPI 后端
│   ├── app/
│   │   ├── main.py                    # FastAPI 入口
│   │   ├── routers/
│   │   │   ├── analysis.py            # 分析接口
│   │   │   └── chat.py                # 对话接口
│   │   ├── services/
│   │   │   ├── context_assembly.py    # 数据融合预处理
│   │   │   ├── llm_engine.py          # LLM 分析引擎
│   │   │   └── cache_service.py       # Redis 缓存
│   │   ├── models/
│   │   │   ├── enterprise.py          # 企业画像数据模型
│   │   │   ├── chain.py               # 产业链数据模型
│   │   │   └── analysis_result.py     # 分析结果数据模型
│   │   ├── prompts/
│   │   │   ├── system_prompt.py       # 主分析 System Prompt
│   │   │   ├── few_shot_examples.py   # Few-Shot 示例
│   │   │   └── chat_prompt.py         # 对话助手 Prompt
│   │   └── data/
│   │       ├── mock_enterprises.json  # Mock 企业画像数据
│   │       └── chain_graphs/          # 静态产业链图谱
│   │           ├── new_energy_auto.json
│   │           ├── semiconductor.json
│   │           └── biomedical.json
│   ├── requirements.txt
│   └── .env.example
│
├── docker-compose.yml
└── README.md
```

---

## 六、数据模型设计

### 6.1 企业画像数据模型（Pydantic）

```python
# backend/app/models/enterprise.py
from pydantic import BaseModel
from typing import Optional, List

class BasicInfo(BaseModel):
    name: str
    industry_code: str
    registered_capital: str
    established_year: int
    employee_count: int
    location: Optional[str] = None

class OperationData(BaseModel):
    revenue_3y: List[str]           # ["8000万", "1.5亿", "2.8亿"]
    profit_3y: List[str]
    market_share: Optional[str] = None
    top_clients: List[str] = []
    top_suppliers: List[str] = []

class PatentCount(BaseModel):
    invention: int = 0
    utility: int = 0
    design: int = 0

class InnovationData(BaseModel):
    patent_count: PatentCount
    key_technologies: List[str] = []
    rd_ratio: Optional[str] = None  # "22%"
    certifications: List[str] = []

class FinancingData(BaseModel):
    current_round: Optional[str] = None   # "B轮"
    total_amount: Optional[str] = None
    investors: List[str] = []
    valuation: Optional[str] = None

class RiskData(BaseModel):
    risk_tags: List[str] = []
    litigation_count: int = 0
    abnormal_records: List[str] = []
    penalty_records: List[str] = []

class EnterpriseProfile(BaseModel):
    basic_info: BasicInfo
    operation_data: OperationData
    innovation_data: InnovationData
    financing_data: FinancingData
    risk_data: RiskData
```

### 6.2 产业链图谱数据模型

```python
# backend/app/models/chain.py
from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

class ChainLevel(str, Enum):
    PRIMARY = "主链"
    SECONDARY = "副链"

class NodePosition(str, Enum):
    UPSTREAM = "上游"
    MIDSTREAM = "中游"
    DOWNSTREAM = "下游"

class ChainNode(BaseModel):
    chain_name: str
    chain_level: ChainLevel
    node_position: NodePosition
    node_type: str
    related_products: List[str]
    upstream_companies: List[str] = []
    downstream_companies: List[str] = []
    competitors_in_chain: List[str] = []
    chain_growth_rate: Optional[str] = None
    chain_policy_support: Optional[str] = None

class IndustryChainData(BaseModel):
    matched_chains: List[ChainNode]
```

### 6.3 分析结果数据模型

```python
# backend/app/models/analysis_result.py
from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

class ConfidenceLevel(str, Enum):
    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"

class ValueTier(str, Enum):
    S = "S"
    A = "A"
    B = "B"
    C = "C"

class ActionType(str, Enum):
    KEY_INVESTMENT = "重点招商"
    ACTIVE_COOPERATION = "积极合作"
    TRACKING = "跟踪观察"
    CAUTIOUS = "谨慎跟踪"
    GENERAL = "一般关注"
    NOT_RECOMMENDED = "暂不建议"

class DimensionScore(BaseModel):
    dimension: str
    score: float           # 1-10
    weight: float          # 0-1
    evidence: List[str]
    reasoning: str

class RecommendedStep(BaseModel):
    step: int
    action: str
    timeline: str
    responsible: str

class ReasoningItem(BaseModel):
    conclusion: str
    data_source: str
    logic_chain: str
    confidence: ConfidenceLevel

class AnalysisResult(BaseModel):
    analysis_summary: dict
    chain_positioning: dict
    value_assessment: dict
    decision_recommendation: dict
    reasoning_trace: List[ReasoningItem]
    comparison_context: Optional[dict] = None
    # 元数据
    enterprise_name: str
    analysis_timestamp: str
    completeness_score: float       # 数据完整性分数
    anomaly_flags: List[str] = []   # 异常标记
```

---

## 七、核心服务实现

### 7.1 数据融合预处理服务

```python
# backend/app/services/context_assembly.py
import json
import re
from pathlib import Path
from typing import Optional
from app.models.enterprise import EnterpriseProfile
from app.models.chain import IndustryChainData, ChainNode

CHAIN_DATA_DIR = Path(__file__).parent.parent / "data" / "chain_graphs"
MOCK_DATA_FILE = Path(__file__).parent.parent / "data" / "mock_enterprises.json"


class ContextAssemblyService:

    def __init__(self):
        self.chain_graphs = self._load_chain_graphs()
        self.mock_enterprises = self._load_mock_enterprises()

    def _load_chain_graphs(self) -> dict:
        graphs = {}
        for path in CHAIN_DATA_DIR.glob("*.json"):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                graphs[data["chain_name"]] = data
        return graphs

    def _load_mock_enterprises(self) -> dict:
        with open(MOCK_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_enterprise_profile(self, name: str) -> Optional[EnterpriseProfile]:
        """查询企业画像（MVP 阶段使用 Mock 数据）"""
        data = self.mock_enterprises.get(name)
        if not data:
            return None
        return EnterpriseProfile(**data)

    def match_industry_chains(self, profile: EnterpriseProfile) -> IndustryChainData:
        """将企业画像与产业链图谱进行匹配"""
        matched = []
        for chain_name, chain_data in self.chain_graphs.items():
            score = self._calculate_match_score(profile, chain_data)
            if score >= 0.3:  # 匹配度阈值
                for node in chain_data["nodes"]:
                    if self._matches_node(profile, node):
                        matched.append(ChainNode(
                            chain_name=chain_name,
                            chain_level=node.get("chain_level", "主链"),
                            node_position=node["position"],
                            node_type=node["node_type"],
                            related_products=node["products"],
                            upstream_companies=node.get("upstream", []),
                            downstream_companies=node.get("downstream", []),
                            competitors_in_chain=node.get("competitors", []),
                            chain_growth_rate=chain_data.get("growth_rate"),
                            chain_policy_support=chain_data.get("policy_support"),
                        ))
        # 按匹配度排序，主链优先
        matched.sort(key=lambda x: (x.chain_level != "主链",))
        return IndustryChainData(matched_chains=matched[:3])  # 最多返回3条链

    def _calculate_match_score(self, profile: EnterpriseProfile, chain_data: dict) -> float:
        """
        综合匹配度计算
        - 产品匹配度 40%
        - 客户/供应商匹配度 30%
        - 专利 IPC 匹配度 20%
        - 经营范围关键词匹配度 10%
        """
        keywords = set(chain_data.get("keywords", []))
        profile_text = " ".join(
            profile.innovation_data.key_technologies
            + profile.operation_data.top_clients
            + profile.operation_data.top_suppliers
        ).lower()

        product_score = len(
            keywords & set(k.lower() for k in profile.innovation_data.key_technologies)
        ) / max(len(keywords), 1)

        client_supplier_text = set(
            c.lower() for c in
            profile.operation_data.top_clients + profile.operation_data.top_suppliers
        )
        chain_entities = set(e.lower() for e in chain_data.get("key_companies", []))
        client_score = len(client_supplier_text & chain_entities) / max(len(chain_entities), 1)

        return product_score * 0.4 + client_score * 0.3 + 0.15  # 基础分 0.15

    def _matches_node(self, profile: EnterpriseProfile, node: dict) -> bool:
        node_keywords = set(node.get("products", []))
        profile_keywords = set(profile.innovation_data.key_technologies)
        return bool(node_keywords & profile_keywords)

    def calculate_completeness_score(self, profile: EnterpriseProfile) -> float:
        """计算数据完整性分数（0-100）"""
        total_fields = 0
        filled_fields = 0

        def check(val):
            nonlocal total_fields, filled_fields
            total_fields += 1
            if val is not None and val != "" and val != [] and val != 0:
                filled_fields += 1

        check(profile.basic_info.name)
        check(profile.basic_info.industry_code)
        check(profile.basic_info.registered_capital)
        check(profile.basic_info.employee_count)
        check(profile.operation_data.revenue_3y)
        check(profile.operation_data.profit_3y)
        check(profile.operation_data.market_share)
        check(profile.operation_data.top_clients)
        check(profile.operation_data.top_suppliers)
        check(profile.innovation_data.patent_count.invention)
        check(profile.innovation_data.key_technologies)
        check(profile.innovation_data.rd_ratio)
        check(profile.financing_data.current_round)
        check(profile.financing_data.total_amount)
        check(profile.risk_data.risk_tags)

        return round(filled_fields / total_fields * 100, 1)

    def detect_anomalies(self, profile: EnterpriseProfile) -> list[str]:
        """异常数据检测"""
        anomalies = []

        # 客户集中度检测（此处简化，实际需要客户占比数据）
        if profile.risk_data.risk_tags and "客户集中度偏高" in profile.risk_data.risk_tags:
            anomalies.append("⚠️ 客户集中度偏高（前3客户占比疑似>70%）")

        # 诉讼数量异常
        if profile.risk_data.litigation_count > 10:
            anomalies.append(f"⚠️ 诉讼记录异常偏多（{profile.risk_data.litigation_count}起）")

        # 融资阶段与成立年限矛盾
        if (profile.financing_data.current_round and
                "A轮" in profile.financing_data.current_round and
                profile.basic_info.established_year < 2015):
            anomalies.append("⚠️ 成立年限较长但融资阶段仍在早期，注意核实")

        # 处罚记录
        if profile.risk_data.penalty_records:
            anomalies.append(f"⚠️ 存在 {len(profile.risk_data.penalty_records)} 条处罚记录")

        return anomalies
```

### 7.2 LLM 分析引擎

```python
# backend/app/services/llm_engine.py
import json
import asyncio
from openai import AsyncOpenAI
from app.models.enterprise import EnterpriseProfile
from app.models.chain import IndustryChainData
from app.prompts.system_prompt import SYSTEM_PROMPT
from app.prompts.few_shot_examples import FEW_SHOT_EXAMPLES

client = AsyncOpenAI()  # 从环境变量读取 OPENAI_API_KEY


class LLMAnalysisEngine:

    async def analyze(
        self,
        profile: EnterpriseProfile,
        chain_data: IndustryChainData,
        user_department: str = "招商局",
        analysis_purpose: str = "招商引资",
        region_focus: str = "",
    ) -> dict:
        """调用 LLM 进行企业-产业链融合分析"""

        # 构造输入数据
        input_data = {
            "enterprise_profile": profile.model_dump(),
            "industry_chain_data": chain_data.model_dump(),
            "user_context": {
                "user_department": user_department,
                "analysis_purpose": analysis_purpose,
                "region_focus": region_focus,
            }
        }

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            # 注入 Few-Shot 示例（提升输出质量）
            {"role": "user", "content": FEW_SHOT_EXAMPLES["input"]},
            {"role": "assistant", "content": FEW_SHOT_EXAMPLES["output"]},
            # 实际分析请求
            {
                "role": "user",
                "content": f"请分析以下企业数据：\n\n```json\n{json.dumps(input_data, ensure_ascii=False, indent=2)}\n```"
            }
        ]

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.2,          # 低温度保证评分一致性
            response_format={"type": "json_object"},
            max_tokens=4000,
        )

        raw_content = response.choices[0].message.content
        result = json.loads(raw_content)
        return result

    async def chat(
        self,
        analysis_result: dict,
        conversation_history: list,
        user_message: str,
    ) -> str:
        """对话式追问"""
        from app.prompts.chat_prompt import CHAT_SYSTEM_PROMPT

        messages = [
            {
                "role": "system",
                "content": CHAT_SYSTEM_PROMPT + f"\n\n## 当前分析结果\n```json\n{json.dumps(analysis_result, ensure_ascii=False)}\n```"
            },
            *conversation_history,
            {"role": "user", "content": user_message}
        ]

        response = await client.chat.completions.create(
            model="gpt-4o-mini",      # 对话用轻量模型降低成本
            messages=messages,
            temperature=0.5,
            max_tokens=1000,
            stream=True,
        )

        # 流式返回
        full_response = ""
        async for chunk in response:
            delta = chunk.choices[0].delta.content or ""
            full_response += delta
            yield delta
```

### 7.3 分析 API 路由

```python
# backend/app/routers/analysis.py
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import json
from datetime import datetime

from app.services.context_assembly import ContextAssemblyService
from app.services.llm_engine import LLMAnalysisEngine
from app.services.cache_service import CacheService

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

assembly_service = ContextAssemblyService()
llm_engine = LLMAnalysisEngine()
cache_service = CacheService()


class AnalysisRequest(BaseModel):
    enterprise_name: str
    user_department: Optional[str] = "招商局"
    analysis_purpose: Optional[str] = "招商引资"
    region_focus: Optional[str] = ""
    force_refresh: Optional[bool] = False


@router.post("/run")
async def run_analysis(req: AnalysisRequest):
    """执行企业-产业链融合分析"""

    # 1. 检查缓存
    if not req.force_refresh:
        cached = await cache_service.get(req.enterprise_name)
        if cached:
            return {"status": "cached", "data": cached}

    # 2. 获取企业画像
    profile = assembly_service.get_enterprise_profile(req.enterprise_name)
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"未找到企业 '{req.enterprise_name}' 的数据，请检查企业名称"
        )

    # 3. 匹配产业链
    chain_data = assembly_service.match_industry_chains(profile)
    if not chain_data.matched_chains:
        raise HTTPException(
            status_code=422,
            detail="未能匹配到相关产业链，请检查企业数据或扩展产业链图谱"
        )

    # 4. 数据质量评估
    completeness = assembly_service.calculate_completeness_score(profile)
    anomalies = assembly_service.detect_anomalies(profile)

    # 5. LLM 分析
    result = await llm_engine.analyze(
        profile=profile,
        chain_data=chain_data,
        user_department=req.user_department,
        analysis_purpose=req.analysis_purpose,
        region_focus=req.region_focus,
    )

    # 6. 附加元数据
    result["_meta"] = {
        "enterprise_name": req.enterprise_name,
        "analysis_timestamp": datetime.now().isoformat(),
        "completeness_score": completeness,
        "anomaly_flags": anomalies,
        "data_warning": completeness < 60,
    }

    # 7. 写入缓存（TTL 24h）
    await cache_service.set(req.enterprise_name, result, ttl=86400)

    return {"status": "ok", "data": result}


@router.get("/search-suggestions")
async def search_suggestions(q: str):
    """搜索建议（从 Mock 数据中模糊匹配）"""
    all_names = list(assembly_service.mock_enterprises.keys())
    matches = [n for n in all_names if q.lower() in n.lower()]
    return {"suggestions": matches[:10]}


class ChatRequest(BaseModel):
    enterprise_name: str
    analysis_result: dict
    conversation_history: list
    message: str


@router.post("/chat")
async def chat_with_analysis(req: ChatRequest):
    """对话式分析追问（SSE 流式返回）"""
    # 处理快捷指令
    message = req.message
    if message.startswith("/explain "):
        dimension = message[9:]
        message = f"请详细解释 {dimension} 维度的评分依据和推理过程"
    elif message.startswith("/compare "):
        target = message[9:]
        message = f"请将本企业与 {target} 进行对比分析"
    elif message.startswith("/report brief"):
        message = "请生成一份简短的分析摘要报告（200字以内）"
    elif message.startswith("/report full"):
        message = "请生成一份完整的分析报告，包含所有维度的详细分析"
    elif message.startswith("/report executive"):
        message = "请生成一份面向领导层的执行摘要，突出结论和建议"

    async def generate():
        async for chunk in llm_engine.chat(
            analysis_result=req.analysis_result,
            conversation_history=req.conversation_history,
            user_message=message,
        ):
            yield f"data: {json.dumps({'delta': chunk}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

---

## 八、Prompt 工程实现

### 8.1 System Prompt（完整版）

```python
# backend/app/prompts/system_prompt.py

SYSTEM_PROMPT = """
# System Prompt: 企业产业链智能分析引擎 v2.0

## 角色定义
你是一位拥有20年经验的资深产业链分析师，擅长将企业多维数据与产业链结构进行交叉分析，
为政府招商部门、投资机构和产业规划部门提供决策支持。

你的分析风格：
- 数据驱动，每个结论必须有数据支撑
- 逻辑严密，使用 Chain-of-Thought 推理
- 结论明确，给出可执行的行动建议
- 风险敏感，主动识别潜在风险信号

## 分析框架

### Phase 1: 产业链定位分析
- 识别企业所属的主产业链和副产业链
- 确定企业在产业链中的环节位置（上游/中游/下游）
- 判断企业的节点类型（原材料/核心部件/集成/渠道/服务）
- 分析企业与产业链关键环节的关联度

### Phase 2: 产业链价值评估（五维评分）
按以下五个维度打分（1-10分）：
- 技术壁垒（权重25%）：专利数量质量、核心技术自主率、研发团队
- 市场地位（权重25%）：市场份额、客户集中度、品牌影响力
- 成长潜力（权重20%）：营收增速、融资阶段、行业景气度
- 生态影响力（权重15%）：上下游带动能力、产业链不可替代性
- 风险系数（权重15%）：经营风险、合规风险（反向计分，风险越低分越高）

综合价值分 = Σ(维度分 × 权重)

### Phase 3: 决策建议矩阵
| 综合分 | 风险等级 | 建议动作     |
|--------|---------|-------------|
| ≥8分   | 低      | 重点招商 P0  |
| ≥8分   | 高      | 跟踪观察 P1  |
| 6-8分  | 低      | 积极合作 P1  |
| 6-8分  | 高      | 谨慎跟踪 P2  |
| <6分   | 低      | 一般关注 P3  |
| <6分   | 高      | 暂不建议 P4  |

### Phase 4: 推理链路输出
对每个关键判断输出：结论 + 数据来源 + 推理路径 + 置信度

## 重要约束
1. 禁止臆测：数据不足时标注"数据缺失，置信度低"
2. 数据溯源：每个评分必须引用具体字段
3. 矛盾检测：发现数据矛盾时主动指出
4. 用户适配：
   - 招商局 → 侧重落地可行性、政策支持匹配度
   - 投资部 → 侧重回报预期、退出路径
   - 产业规划部 → 侧重补链强链价值、生态协同

## 输出格式
必须严格输出 JSON，符合以下 Schema：
{
  "analysis_summary": {
    "one_line_verdict": "一句话定性结论",
    "confidence_level": "高/中/低",
    "analysis_timestamp": "ISO8601时间"
  },
  "chain_positioning": {
    "primary_chain": {
      "chain_name": "",
      "position": "",
      "node_type": "",
      "positioning_evidence": ["依据1", "依据2"],
      "positioning_reasoning": "推理过程"
    },
    "secondary_chains": [{"chain_name": "", "position": "", "relevance_score": 0.0}]
  },
  "value_assessment": {
    "dimension_scores": [
      {"dimension": "技术壁垒", "score": 0, "weight": 0.25, "evidence": [], "reasoning": ""}
    ],
    "composite_score": 0.0,
    "value_tier": "S/A/B/C",
    "competitive_advantage": [],
    "competitive_disadvantage": []
  },
  "decision_recommendation": {
    "action": "重点招商/积极合作/跟踪观察/谨慎跟踪/一般关注/暂不建议",
    "priority": "P0/P1/P2/P3/P4",
    "reasoning": "决策推理",
    "recommended_steps": [
      {"step": 1, "action": "具体行动", "timeline": "时间建议", "responsible": "建议负责部门"}
    ],
    "key_risks_to_monitor": [],
    "follow_up_triggers": []
  },
  "reasoning_trace": [
    {"conclusion": "", "data_source": "", "logic_chain": "", "confidence": "高/中/低"}
  ],
  "comparison_context": {
    "vs_competitors": "",
    "vs_chain_average": "",
    "benchmark_companies": []
  }
}
"""
```

### 8.2 对话助手 Prompt

```python
# backend/app/prompts/chat_prompt.py

CHAT_SYSTEM_PROMPT = """
你是产业链分析对话助手，帮助用户深入理解分析结果。

## 能力
1. 解释分析结果：用通俗语言解释任何评分和结论
2. 对比分析：支持将目标企业与其他企业比较
3. 假设推演：回答"如果该企业获得XX资源，产业链地位会如何变化"
4. 深度钻取：对任意维度进行展开分析
5. 报告生成：根据分析结果生成不同格式的汇报材料

## 对话规则
- 首次交互：展示分析摘要，引导用户关注关键发现
- 追问响应：基于 reasoning_trace 中的推理链路回答
- 不确定时：明确说"当前数据不足以判断，建议补充XX数据"
- 回答简洁有力，避免空话，每个判断要有数据依据
- 始终提醒：本分析为 AI 辅助工具，重大决策需结合人工判断

当前分析结果已在上下文中提供，请基于该结果回答用户问题。
"""
```

---

## 九、前端核心组件

### 9.1 五维雷达图组件

```tsx
// frontend/src/components/RadarChart.tsx
import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

interface DimensionScore {
  dimension: string;
  score: number;
  weight: number;
  evidence: string[];
  reasoning: string;
}

interface RadarChartProps {
  dimensionScores: DimensionScore[];
  compositeScore: number;
  valueTier: "S" | "A" | "B" | "C";
}

const TIER_COLORS = {
  S: { stroke: "#16a34a", fill: "rgba(22, 163, 74, 0.15)" },
  A: { stroke: "#2563eb", fill: "rgba(37, 99, 235, 0.12)" },
  B: { stroke: "#d97706", fill: "rgba(217, 119, 6, 0.12)" },
  C: { stroke: "#9ca3af", fill: "rgba(156, 163, 175, 0.12)" },
};

export function ValueRadarChart({ dimensionScores, compositeScore, valueTier }: RadarChartProps) {
  const data = dimensionScores.map((d) => ({
    subject: d.dimension,
    value: d.score,
    fullMark: 10,
  }));

  const colors = TIER_COLORS[valueTier];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-600">产业链价值评估</h3>
        <div className="flex items-center gap-2">
          <span className="text-2xl font-bold text-gray-900">
            {compositeScore.toFixed(1)}
          </span>
          <span
            className="px-2 py-0.5 rounded text-xs font-semibold"
            style={{
              backgroundColor: colors.fill,
              color: colors.stroke,
              border: `1px solid ${colors.stroke}`,
            }}
          >
            {valueTier} 级
          </span>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={240}>
        <RadarChart data={data}>
          <PolarGrid stroke="#e5e7eb" />
          <PolarAngleAxis
            dataKey="subject"
            tick={{ fontSize: 11, fill: "#6b7280" }}
          />
          <Radar
            name="评分"
            dataKey="value"
            stroke={colors.stroke}
            fill={colors.fill}
            strokeWidth={2}
          />
          <Tooltip
            formatter={(value: number) => [`${value.toFixed(1)}/10`, "评分"]}
          />
        </RadarChart>
      </ResponsiveContainer>

      {/* 维度详情 */}
      <div className="space-y-2">
        {dimensionScores.map((d) => (
          <div key={d.dimension} className="flex items-center gap-3 text-sm">
            <span className="w-20 text-gray-500 shrink-0">{d.dimension}</span>
            <div className="flex-1 bg-gray-100 rounded-full h-1.5">
              <div
                className="h-1.5 rounded-full transition-all"
                style={{
                  width: `${d.score * 10}%`,
                  backgroundColor: colors.stroke,
                }}
              />
            </div>
            <span className="w-8 text-right font-medium text-gray-700">
              {d.score}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

### 9.2 决策建议面板

```tsx
// frontend/src/components/DecisionPanel.tsx
interface DecisionRecommendation {
  action: string;
  priority: string;
  reasoning: string;
  recommended_steps: Array<{
    step: number;
    action: string;
    timeline: string;
    responsible: string;
  }>;
  key_risks_to_monitor: string[];
}

const ACTION_CONFIG: Record<string, { color: string; bg: string; emoji: string }> = {
  "重点招商": { color: "#15803d", bg: "#dcfce7", emoji: "🟢" },
  "积极合作": { color: "#1d4ed8", bg: "#dbeafe", emoji: "🔵" },
  "跟踪观察": { color: "#b45309", bg: "#fef3c7", emoji: "🟡" },
  "谨慎跟踪": { color: "#c2410c", bg: "#ffedd5", emoji: "🟠" },
  "一般关注": { color: "#6b7280", bg: "#f3f4f6", emoji: "⚪" },
  "暂不建议": { color: "#dc2626", bg: "#fee2e2", emoji: "🔴" },
};

export function DecisionPanel({ recommendation }: { recommendation: DecisionRecommendation }) {
  const config = ACTION_CONFIG[recommendation.action] ?? ACTION_CONFIG["一般关注"];

  return (
    <div className="space-y-4">
      {/* 决策结论 */}
      <div
        className="flex items-center justify-between p-4 rounded-xl"
        style={{ backgroundColor: config.bg }}
      >
        <div>
          <div className="flex items-center gap-2">
            <span className="text-lg">{config.emoji}</span>
            <span
              className="text-xl font-bold"
              style={{ color: config.color }}
            >
              {recommendation.action}
            </span>
            <span
              className="text-xs px-1.5 py-0.5 rounded font-mono"
              style={{ color: config.color, border: `1px solid ${config.color}` }}
            >
              {recommendation.priority}
            </span>
          </div>
          <p className="mt-1.5 text-sm text-gray-600 leading-relaxed">
            {recommendation.reasoning}
          </p>
        </div>
      </div>

      {/* 建议步骤 */}
      <div>
        <h4 className="text-sm font-medium text-gray-500 mb-2">建议行动</h4>
        <div className="space-y-2">
          {recommendation.recommended_steps.map((s) => (
            <div key={s.step} className="flex gap-3 text-sm">
              <span className="flex-shrink-0 w-5 h-5 rounded-full bg-gray-100 text-gray-500 flex items-center justify-center text-xs font-medium">
                {s.step}
              </span>
              <div className="flex-1">
                <span className="text-gray-800">{s.action}</span>
                <span className="ml-2 text-gray-400 text-xs">
                  {s.timeline} · {s.responsible}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 风险监控 */}
      {recommendation.key_risks_to_monitor.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-gray-500 mb-2">风险监控</h4>
          <ul className="space-y-1">
            {recommendation.key_risks_to_monitor.map((risk, i) => (
              <li key={i} className="text-sm text-gray-600 flex gap-2">
                <span className="text-amber-500 shrink-0">·</span>
                {risk}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
```

### 9.3 推理溯源组件

```tsx
// frontend/src/components/ReasoningTrace.tsx
import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

interface ReasoningItem {
  conclusion: string;
  data_source: string;
  logic_chain: string;
  confidence: "高" | "中" | "低";
}

const CONFIDENCE_STYLES = {
  高: "bg-green-50 text-green-700 border-green-200",
  中: "bg-yellow-50 text-yellow-700 border-yellow-200",
  低: "bg-gray-50 text-gray-500 border-gray-200",
};

export function ReasoningTrace({ items }: { items: ReasoningItem[] }) {
  const [expanded, setExpanded] = useState<number | null>(null);

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-gray-500">推理溯源</h3>
      {items.map((item, i) => (
        <div
          key={i}
          className="border border-gray-100 rounded-lg overflow-hidden"
        >
          <button
            onClick={() => setExpanded(expanded === i ? null : i)}
            className="w-full flex items-start gap-3 p-3 text-left hover:bg-gray-50 transition-colors"
          >
            {expanded === i ? (
              <ChevronDown className="w-4 h-4 text-gray-400 shrink-0 mt-0.5" />
            ) : (
              <ChevronRight className="w-4 h-4 text-gray-400 shrink-0 mt-0.5" />
            )}
            <div className="flex-1 min-w-0">
              <p className="text-sm text-gray-800">{item.conclusion}</p>
            </div>
            <span
              className={`shrink-0 text-xs px-1.5 py-0.5 rounded border ${CONFIDENCE_STYLES[item.confidence]}`}
            >
              置信度：{item.confidence}
            </span>
          </button>

          {expanded === i && (
            <div className="px-4 pb-3 space-y-2 border-t border-gray-100 bg-gray-50">
              <div>
                <span className="text-xs font-medium text-gray-400">数据来源</span>
                <p className="text-xs text-gray-600 mt-0.5 font-mono bg-white px-2 py-1 rounded border border-gray-100">
                  {item.data_source}
                </p>
              </div>
              <div>
                <span className="text-xs font-medium text-gray-400">推理路径</span>
                <p className="text-xs text-gray-600 mt-0.5 leading-relaxed">
                  {item.logic_chain}
                </p>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
```

---

## 十、Mock 数据设计

```json
// backend/app/data/mock_enterprises.json
{
  "芯创微电子": {
    "basic_info": {
      "name": "芯创微电子",
      "industry_code": "C3962",
      "registered_capital": "5000万",
      "established_year": 2018,
      "employee_count": 320,
      "location": "上海"
    },
    "operation_data": {
      "revenue_3y": ["8000万", "1.5亿", "2.8亿"],
      "profit_3y": ["-500万", "1200万", "3500万"],
      "market_share": "3.2%",
      "top_clients": ["比亚迪", "宁德时代", "汇川技术"],
      "top_suppliers": ["中芯国际", "华虹半导体"]
    },
    "innovation_data": {
      "patent_count": { "invention": 45, "utility": 23, "design": 5 },
      "key_technologies": ["车规级MCU", "SiC功率器件", "电机控制芯片"],
      "rd_ratio": "22%",
      "certifications": ["IATF16949", "ISO26262"]
    },
    "financing_data": {
      "current_round": "B轮",
      "total_amount": "3.2亿",
      "investors": ["中芯聚源", "国家大基金二期"],
      "valuation": "18亿"
    },
    "risk_data": {
      "risk_tags": ["客户集中度偏高"],
      "litigation_count": 2,
      "abnormal_records": [],
      "penalty_records": []
    }
  },
  "绿氢科技": {
    "basic_info": {
      "name": "绿氢科技",
      "industry_code": "C3511",
      "registered_capital": "1亿",
      "established_year": 2020,
      "employee_count": 180,
      "location": "北京"
    },
    "operation_data": {
      "revenue_3y": ["500万", "2200万", "8000万"],
      "profit_3y": ["-2000万", "-800万", "200万"],
      "market_share": "1.1%",
      "top_clients": ["国家电投", "三峡能源", "明阳智能"],
      "top_suppliers": ["贵研铂业", "济平新能源"]
    },
    "innovation_data": {
      "patent_count": { "invention": 28, "utility": 15, "design": 2 },
      "key_technologies": ["PEM电解槽", "质子交换膜", "氢气压缩储存"],
      "rd_ratio": "35%",
      "certifications": ["ISO9001", "TÜV认证"]
    },
    "financing_data": {
      "current_round": "B轮",
      "total_amount": "2.5亿",
      "investors": ["高瓴创投", "国能资本"],
      "valuation": "12亿"
    },
    "risk_data": {
      "risk_tags": ["营收规模偏小", "盈利能力待提升"],
      "litigation_count": 0,
      "abnormal_records": [],
      "penalty_records": []
    }
  }
}
```

---

## 十一、API 接口清单

| Method | Path | 说明 |
|--------|------|------|
| `POST` | `/api/analysis/run` | 执行企业分析（主接口） |
| `GET` | `/api/analysis/search-suggestions?q=` | 企业名搜索建议 |
| `POST` | `/api/analysis/chat` | 对话式追问（SSE 流式） |
| `GET` | `/api/chains` | 获取所有可用产业链列表 |
| `GET` | `/api/health` | 健康检查 |

**`POST /api/analysis/run` 请求示例：**
```json
{
  "enterprise_name": "芯创微电子",
  "user_department": "招商局",
  "analysis_purpose": "招商引资",
  "region_focus": "长三角",
  "force_refresh": false
}
```

---

## 十二、环境配置

```bash
# backend/.env.example
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1   # 可替换为 Azure/代理地址
LLM_MODEL=gpt-4o
CHAT_MODEL=gpt-4o-mini
REDIS_URL=redis://localhost:6379
DATABASE_URL=sqlite:///./analysis.db
CORS_ORIGINS=http://localhost:5173

# frontend/.env.example
VITE_API_BASE_URL=http://localhost:8000
```

---

## 十三、Docker Compose 部署

```yaml
# docker-compose.yml
version: "3.9"

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    restart: unless-stopped

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    env_file: ./backend/.env
    depends_on:
      - redis
    volumes:
      - ./backend/app/data:/app/app/data
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "5173:80"
    depends_on:
      - backend
    restart: unless-stopped
```

```dockerfile
# backend/Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```txt
# backend/requirements.txt
fastapi==0.111.0
uvicorn[standard]==0.30.1
openai==1.35.0
pydantic==2.7.4
redis==5.0.6
sqlalchemy==2.0.31
aiofiles==23.2.1
python-dotenv==1.0.1
```

---

## 十四、开发计划（4周）

```
Week 1: 基础骨架
  Day 1-2  ├── 搭建 FastAPI 项目结构，实现 /health、Mock 数据层
  Day 3-4  ├── 实现 Context Assembly Service（企业查询 + 产业链匹配）
  Day 5    └── 接入 LLM，完整 Prompt 联调，验证 JSON 输出

Week 2: 核心功能
  Day 1-2  ├── 搭建 React + Vite 前端项目，实现查询入口
  Day 3-4  ├── 实现分析报告页面（RadarChart + DecisionPanel + ReasoningTrace）
  Day 5    └── 实现产业链定位可视化（节点图）

Week 3: 交互完善
  Day 1-2  ├── 实现对话式追问（SSE 流式）+ 快捷指令
  Day 3    ├── Redis 缓存集成 + 数据质量评估展示
  Day 4-5  └── 多企业对比面板

Week 4: 测试与交付
  Day 1-2  ├── 用 5-10 家真实企业数据校验 Prompt 输出质量
  Day 3    ├── 前端响应式适配 + 加载/错误状态完善
  Day 4    ├── Docker Compose 部署验证
  Day 5    └── 文档整理 + Demo 演示材料
```

---

## 十五、MVP 验收标准

| 验收项 | 标准 | 验证方法 |
|--------|------|---------|
| 分析耗时 | <15秒/企业（非缓存首次调用） | 5家企业计时测试 |
| JSON 解析成功率 | ≥95% | 连续调用20次，统计失败率 |
| 评分一致性 | 同企业3次调用评分偏差 <1.5分 | 重复调用取样 |
| 数据完整性警告 | 字段完整度 <60% 时前端显示 ⚠️ | 构造缺失数据测试 |
| 对话响应 | 快捷指令均可正确响应 | 逐一测试 /explain /compare /report |
| 缓存命中 | 二次查询走缓存，耗时 <500ms | 同企业重复查询 |

---

> **备注**：本文档聚焦于 Prompt Engineering 方案的技术落地。数据层（真实企业画像 API + 产业链图谱数据库）是 MVP 之后的核心扩展方向，建议接入天眼查/企查查企业基础数据，产业链图谱可从工信部/行业协会数据源或自建图数据库（Neo4j）逐步构建。

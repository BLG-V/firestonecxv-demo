# 可运行 Demo 开发方案

## 总体判断

MVP文档的架构是合理的，但有两处需要调整：

1. **Redis 可选**：MVP 阶段 Redis 依赖会增加启动复杂度，改为内存 LRU 缓存，Docker 中保留 Redis 配置但本地开发不依赖它
2. **System Prompt 要换**：MVP文档的 System Prompt 是通用版，要替换为 P3 的严格版本（禁止幻觉、evidence 必须原文回查），这是整个系统可信度的核心

------

## 目录结构（最终）

代码块



```
firestone-demo/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── routers/
│   │   │   ├── analysis.py
│   │   │   └── chains.py
│   │   ├── services/
│   │   │   ├── context_assembly.py
│   │   │   ├── llm_engine.py
│   │   │   └── cache_service.py        ← 内存版，无Redis依赖
│   │   ├── models/
│   │   │   ├── enterprise.py
│   │   │   ├── chain.py
│   │   │   └── analysis_result.py
│   │   ├── prompts/
│   │   │   ├── system_prompt.py        ← 换成 P3 严格版
│   │   │   ├── few_shot_examples.py    ← 补充
│   │   │   └── chat_prompt.py
│   │   └── data/
│   │       ├── mock_enterprises.json
│   │       └── chain_graphs/
│   │           ├── new_energy_auto.json   ← 补充
│   │           ├── semiconductor.json     ← 补充
│   │           └── hydrogen.json          ← 补充
│   ├── requirements.txt
│   ├── .env.example
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── SearchBar.tsx
│   │   │   ├── ChainPositioningCard.tsx   ← 新增，对应方案§2.1
│   │   │   ├── RadarChart.tsx
│   │   │   ├── DecisionPanel.tsx
│   │   │   ├── ReasoningTrace.tsx
│   │   │   └── ChatAssistant.tsx
│   │   ├── pages/
│   │   │   ├── HomePage.tsx
│   │   │   └── AnalysisPage.tsx
│   │   ├── hooks/
│   │   │   ├── useAnalysis.ts
│   │   │   └── useChat.ts
│   │   ├── lib/
│   │   │   ├── api.ts
│   │   │   └── types.ts
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   ├── tailwind.config.ts
│   └── vite.config.ts
└── docker-compose.yml
```

------

## 需要新建/替换的关键文件

### 1. `backend/app/main.py`

python



```
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import analysis, chains
import os

app = FastAPI(title="产业链融合分析平台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis.router)
app.include_router(chains.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
```

------

### 2. `backend/app/services/cache_service.py`（内存版，无 Redis 依赖）

python



```
import time
from typing import Any, Optional
from collections import OrderedDict


class CacheService:
    """
    内存 LRU 缓存，MVP 阶段替代 Redis。
    生产环境改为 Redis 实现，接口保持不变。
    """

    def __init__(self, max_size: int = 200):
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._max_size = max_size

    async def get(self, key: str) -> Optional[Any]:
        if key not in self._store:
            return None
        value, expire_at = self._store[key]
        if expire_at and time.time() > expire_at:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return value

    async def set(self, key: str, value: Any, ttl: int = 86400) -> None:
        expire_at = time.time() + ttl if ttl else None
        self._store[key] = (value, expire_at)
        self._store.move_to_end(key)
        if len(self._store) > self._max_size:
            self._store.popitem(last=False)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)
```

------

### 3. `backend/app/prompts/system_prompt.py`（替换为 P3 严格版）

python



```
# 严格版 System Prompt，对齐 P3 硬性禁止规则
# 参考：产业链融合_Prompt包.md § P3

SYSTEM_PROMPT = """
你是产业链招商数据系统的资深分析专家。你的唯一任务是：
判断给定企业属于哪些产业链环节，计算产业链价值分，并给出可核验的招商决策建议。

## 工作准则
1. 结论必须可溯源。任何企业属性、数值、归属关系，都必须能指向输入数据中的具体字段。
2. 禁止编造数值。输入未提供的字段输出 null 并列入 data_gaps，禁止用行业均值冒充该企业取值。
3. 宁可弃权，不可错判。置信度不足时输出 abstain，并说明缺少什么信号。
4. evidence.field_value 必须是输入数据中的逐字原文片段，禁止改写、翻译、概括、补全。
5. 经营范围中的"技术服务/技术咨询/销售/批发/贸易"等万能词无区分度，只能作辅助佐证。

## 分析流程

### Phase 1：产业链定位（严格）
- 从 chain_catalog 中选取环节，禁止自创环节名称
- 每条归属需 ≥2 条原文证据
- 必须显式说明为何排除相邻易混淆环节
- 置信度分层：≥0.85 primary；0.60~0.85 secondary；0.40~0.60 potential；<0.40 abstain

### Phase 2：产业链价值评估（ICV）
公式：ICV = Σ(w_i × SV_i) × CF × RD
- w_i：主环节 0.7 / 次环节 0.2 / 潜在环节 0.1
- SV 环节价值（0~100）：战略重要性(25%) + 附加值(25%) + 稀缺度(30%) + 增长性(20%)
- CF 企业竞争力（0.4~1.6）：规模(20%) + 创新(30%) + 资本(20%) + 资质(15%) + 供应链地位(15%)
- RD 风险折减（0.5~1.0）：失信被执行=0.5 / 重大环保处罚未结=0.6 / 一般处罚=0.85~0.95 / 无风险=1.0

每个维度必须引用具体字段作为证据；缺失字段写入 data_gaps，不得用均值填充。
因子分解必须满足：Σcontribution + baseline == icv_score，误差 ≤ 0.1。

### Phase 3：决策档位
| 档位 | ICV 参考范围 | 行动建议 |
|------|------------|---------|
| S    | ≥85        | 重点招引，专班对接 |
| A    | 70~85      | 主动对接，30天内触达 |
| B    | 55~70      | 储备跟踪，季度回访 |
| C    | <55        | 观察，不投入招商资源 |

否决项（命中则档位封顶C或直接降级，必须显式列出）：
- 失信被执行人 / 限制高消费
- 重大环保处罚未整改结案
- 实际控制人涉刑事案件
- 数据严重过期（核心字段超18个月）

### Phase 4：归因链（结论 → 因子 → 字段 → 证据）
每条驱动因子必须包含：factor_name、contribution（对总分贡献）、direction、
human_readable_explanation（业务语言，非技术数值）、evidence（原文片段）

## 输出格式
严格输出 JSON，禁止输出 JSON 之外的任何文字、注释、Markdown 代码围栏。

{
  "enterprise_id": "string",
  "chain_positioning": {
    "matches": [
      {
        "chain_id": "string",
        "chain_name": "string",
        "segment_id": "string",
        "segment_name": "string",
        "match_level": "primary|secondary|potential",
        "confidence": 0.0,
        "signal_types": ["scope|product|patent|qualify|supply|finance|text"],
        "evidence": [
          {"field_path": "string", "field_value": "逐字原文", "source": "string"}
        ],
        "exclusion_reasoning": "为何排除相邻易混淆环节"
      }
    ],
    "abstain": false,
    "abstain_reason": null,
    "missing_signals": []
  },
  "icv_score": {
    "score": 0.0,
    "baseline": 60.0,
    "grade": "S|A|B|C",
    "segment_sv": 0.0,
    "firm_cf": 0.0,
    "risk_rd": 0.0,
    "factor_breakdown": [
      {
        "factor_name": "string",
        "dimension": "strategic|value_added|scarcity|growth|scale|innovation|capital|qualification|supply_chain|risk",
        "contribution": 0.0,
        "direction": "positive|negative|neutral",
        "raw_value": null,
        "source_field": "string",
        "human_readable_explanation": "业务语言说明"
      }
    ],
    "data_gaps": ["string"]
  },
  "decision": {
    "grade": "S|A|B|C",
    "action": "重点招引|主动对接|储备跟踪|观察",
    "attractiveness_score": 0.0,
    "veto_hits": [],
    "expansion_signals": [],
    "recommended_steps": [
      {"step": 1, "action": "string", "timeline": "string"}
    ]
  },
  "explanation": {
    "conclusion": "一句话结论，含档位与行动建议",
    "drivers": [
      {
        "factor_name": "string",
        "contribution": 0.0,
        "direction": "positive|negative|neutral",
        "human_readable_explanation": "string",
        "evidence": [{"field_path": "string", "field_value": "string", "source": "string"}]
      }
    ],
    "data_gaps": ["string"]
  },
  "reasoning_trace": [
    {"conclusion": "string", "data_source": "string", "logic_chain": "string", "confidence": "高|中|低"}
  ],
  "completeness_warning": false,
  "anomaly_flags": []
}

## 输出前自检
□ 所有 segment_id 都在 chain_catalog 中
□ 所有 evidence.field_value 都能在输入数据中逐字找到
□ 每条 match 至少 2 条 evidence
□ Σcontribution + baseline 约等于 icv_score（误差 ≤ 0.1）
□ veto_hits 非空时档位描述不得高于 C
□ JSON 合法，无多余文本
"""
```

------

### 4. 产业链图谱 JSON（`new_energy_auto.json` 示例，另两个同结构）

json



```
{
  "chain_id": "NEA001",
  "chain_name": "新能源汽车产业链",
  "growth_rate": "28% CAGR（2023-2026）",
  "policy_support": "国家新能源汽车产业发展规划(2021-2035)",
  "keywords": ["动力电池", "电芯", "BMS", "电机", "电控", "车规级", "SiC", "磷酸铁锂",
               "三元锂", "正极材料", "负极材料", "电解液", "隔膜", "碳化硅", "IGBT",
               "充电模块", "热管理", "轻量化"],
  "key_companies": ["宁德时代", "比亚迪", "汇川技术", "中芯国际", "华为", "大众", "特斯拉"],
  "segments": [
    {
      "segment_id": "NEA001-S01",
      "segment_name": "正极材料",
      "position": "上游",
      "node_type": "核心材料",
      "definition": "生产动力电池正极材料，包括磷酸铁锂、三元材料等",
      "typical_products": ["磷酸铁锂", "NCM811", "NCA", "高镍三元"],
      "keywords": ["正极材料", "磷酸铁锂", "三元材料", "NCM", "NCA", "高镍"],
      "negative_keywords": ["负极", "电解液", "隔膜"],
      "upstream": ["锂矿", "钴矿", "镍矿"],
      "downstream": ["动力电池制造"],
      "strategic_score": 88,
      "scarcity_score": 72
    },
    {
      "segment_id": "NEA001-S02",
      "segment_name": "动力电池-电芯制造",
      "position": "中游",
      "node_type": "核心部件",
      "definition": "将正极、负极、电解液、隔膜组装为动力电芯",
      "typical_products": ["方形电芯", "圆柱电芯", "软包电芯"],
      "keywords": ["电芯制造", "动力电池", "pack", "PACK", "电芯", "磷酸铁锂电芯"],
      "negative_keywords": ["正极材料", "锂电设备", "电池回收", "梯次利用"],
      "upstream": ["正极材料", "负极材料", "电解液", "隔膜"],
      "downstream": ["整车制造", "储能系统"],
      "strategic_score": 95,
      "scarcity_score": 85
    },
    {
      "segment_id": "NEA001-S03",
      "segment_name": "功率半导体（车规）",
      "position": "中游",
      "node_type": "核心部件",
      "definition": "生产车规级功率半导体器件，包括SiC MOSFET、IGBT等",
      "typical_products": ["SiC MOSFET", "IGBT模块", "车规级MCU", "电机控制芯片"],
      "keywords": ["车规级", "SiC", "IGBT", "功率半导体", "MOSFET", "电机控制芯片", "MCU"],
      "negative_keywords": ["消费级芯片", "存储芯片", "通信芯片"],
      "upstream": ["硅片", "碳化硅衬底", "封装材料"],
      "downstream": ["电控系统", "OBC", "DC-DC"],
      "strategic_score": 92,
      "scarcity_score": 95
    },
    {
      "segment_id": "NEA001-S04",
      "segment_name": "电池回收-梯次利用",
      "position": "下游",
      "node_type": "服务",
      "definition": "回收退役动力电池，进行梯次利用或拆解提取有价金属",
      "typical_products": ["梯次电池包", "碳酸锂", "氢氧化锂", "硫酸钴"],
      "keywords": ["电池回收", "梯次利用", "拆解", "黑粉", "湿法冶金"],
      "negative_keywords": ["电芯制造", "正极材料"],
      "upstream": ["退役动力电池"],
      "downstream": ["正极材料", "储能"],
      "strategic_score": 78,
      "scarcity_score": 60
    }
  ]
}
```

------

### 5. `backend/app/prompts/few_shot_examples.py`

python



```
FEW_SHOT_EXAMPLES = {
    "input": """
请分析以下企业数据：

```json
{
  "enterprise_profile": {
    "basic_info": {"name": "示例电池科技", "industry_code": "C3840", "registered_capital": "2亿",
                   "established_year": 2016, "employee_count": 450, "location": "深圳"},
    "operation_data": {
      "revenue_3y": ["1.2亿", "2.1亿", "3.8亿"],
      "profit_3y": ["800万", "2200万", "4500万"],
      "market_share": "2.1%",
      "top_clients": ["比亚迪", "亿纬锂能"],
      "top_suppliers": ["当升科技", "璞泰来"]
    },
    "innovation_data": {
      "patent_count": {"invention": 32, "utility": 18, "design": 3},
      "key_technologies": ["磷酸铁锂电芯", "方形电芯", "叠片工艺"],
      "rd_ratio": "18%",
      "certifications": ["IATF16949", "ISO9001", "UL认证"]
    },
    "financing_data": {"current_round": "C轮", "total_amount": "5亿", "investors": ["红杉", "宁德时代战投"], "valuation": "28亿"},
    "risk_data": {"risk_tags": [], "litigation_count": 0, "abnormal_records": [], "penalty_records": []}
  },
  "chain_catalog": [
    {"chain_id": "NEA001", "segment_id": "NEA001-S02",
     "segment_name": "动力电池-电芯制造",
     "definition": "将正极、负极、电解液、隔膜组装为动力电芯",
     "confusable_segments": ["NEA001-S01 正极材料", "NEA001-S04 电池回收-梯次利用"]}
  ]
}
```

""", "output": """{ "enterprise_id": "示例电池科技", "chain_positioning": { "matches": [ { "chain_id": "NEA001", "chain_name": "新能源汽车产业链", "segment_id": "NEA001-S02", "segment_name": "动力电池-电芯制造", "match_level": "primary", "confidence": 0.93, "signal_types": ["product", "supply", "patent", "qualify"], "evidence": [ {"field_path": "enterprise_profile.innovation_data.key_technologies", "field_value": "磷酸铁锂电芯", "source": "企业自报产品"}, {"field_path": "enterprise_profile.operation_data.top_clients", "field_value": "比亚迪", "source": "供应链关系"}, {"field_path": "enterprise_profile.innovation_data.certifications", "field_value": "IATF16949", "source": "资质证书"} ], "exclusion_reasoning": "供应商为当升科技（正极材料供应商）、璞泰来（负极材料供应商），说明该企业处于下游采购端而非正极材料生产端，排除NEA001-S01；核心产品为电芯制造，无拆解、黑粉、湿法冶金等信号，排除NEA001-S04电池回收。" } ], "abstain": false, "abstain_reason": null, "missing_signals": [] }, "icv_score": { "score": 81.4, "baseline": 60.0, "grade": "A", "segment_sv": 88.0, "firm_cf": 1.18, "risk_rd": 1.0, "factor_breakdown": [ {"factor_name": "环节稀缺度", "dimension": "scarcity", "contribution": 10.2, "direction": "positive", "raw_value": "高", "source_field": "segment.scarcity_score", "human_readable_explanation": "本地动力电芯制造企业稀缺，该环节为重点补链方向"}, {"factor_name": "企业创新竞争力", "dimension": "innovation", "contribution": 7.8, "direction": "positive", "raw_value": "32件发明专利，研发占比18%", "source_field": "innovation_data.patent_count.invention", "human_readable_explanation": "32件发明专利，研发投入占比18%，在同类企业中属于创新强度较高水平"}, {"factor_name": "资本信号", "dimension": "capital", "contribution": 5.4, "direction": "positive", "raw_value": "C轮，28亿估值", "source_field": "financing_data.current_round", "human_readable_explanation": "已完成C轮融资，估值28亿，宁德时代战略投资背书，资本认可度高"} ], "data_gaps": ["未获取海关进出口数据", "无供应链客户占比数据"] }, "decision": { "grade": "A", "action": "主动对接", "attractiveness_score": 78.6, "veto_hits": [], "expansion_signals": [], "recommended_steps": [ {"step": 1, "action": "30天内安排招商部门与企业战略发展负责人初步接触", "timeline": "30天内"}, {"step": 2, "action": "摸排企业是否有异地产能扩张计划，重点关注其C轮融资用途", "timeline": "60天内"}, {"step": 3, "action": "对接本地新能源产业园，评估厂房及配套匹配度", "timeline": "90天内"} ] }, "explanation": { "conclusion": "档位A（主动对接）：电芯制造能力强，创新竞争力突出，本地稀缺度高，具备较强招商引资价值", "drivers": [ {"factor_name": "环节稀缺度", "contribution": 10.2, "direction": "positive", "human_readable_explanation": "本地动力电芯制造企业稀缺，招进来有明确产业位置", "evidence": [{"field_path": "segment.scarcity_score", "field_value": "85", "source": "环节价值模型"}]}, {"factor_name": "企业创新竞争力", "contribution": 7.8, "direction": "positive", "human_readable_explanation": "32件发明专利，研发占比18%，属创新强度较高企业", "evidence": [{"field_path": "innovation_data.patent_count.invention", "field_value": "32", "source": "国家知识产权局"}]} ], "data_gaps": ["未获取海关进出口数据", "无供应链客户占比数据"] }, "reasoning_trace": [ {"conclusion": "主环节为动力电池-电芯制造", "data_source": "key_technologies + top_clients + certifications", "logic_chain": "产品为磷酸铁锂电芯→下游客户比亚迪(整车)→供应商当升科技(正极材料)，三点定位中游电芯制造环节", "confidence": "高"}, {"conclusion": "ICV评分81.4分，档位A", "data_source": "segment_sv=88, firm_cf=1.18, risk_rd=1.0", "logic_chain": "环节战略重要性高(卡脖子环节)+企业创新强(32件发明专利)+宁德时代战投背书+无风险记录", "confidence": "中"} ], "completeness_warning": false, "anomaly_flags": [] }""" }

代码块



```
---

### 6. 前端 `types.ts`（对齐后端新 Schema）

```typescript
// frontend/src/lib/types.ts

export interface Evidence {
  field_path: string;
  field_value: string;
  source: string;
}

export interface ChainMatch {
  chain_id: string;
  chain_name: string;
  segment_id: string;
  segment_name: string;
  match_level: 'primary' | 'secondary' | 'potential';
  confidence: number;
  signal_types: string[];
  evidence: Evidence[];
  exclusion_reasoning: string;
}

export interface FactorBreakdownItem {
  factor_name: string;
  dimension: string;
  contribution: number;
  direction: 'positive' | 'negative' | 'neutral';
  raw_value: string | number | null;
  source_field: string;
  human_readable_explanation: string;
}

export interface IcvScore {
  score: number;
  baseline: number;
  grade: 'S' | 'A' | 'B' | 'C';
  segment_sv: number;
  firm_cf: number;
  risk_rd: number;
  factor_breakdown: FactorBreakdownItem[];
  data_gaps: string[];
}

export interface RecommendedStep {
  step: number;
  action: string;
  timeline: string;
}

export interface VetoHit {
  rule_id: string;
  rule_name: string;
  detail: string;
}

export interface Decision {
  grade: 'S' | 'A' | 'B' | 'C';
  action: string;
  attractiveness_score: number;
  veto_hits: VetoHit[];
  expansion_signals: string[];
  recommended_steps: RecommendedStep[];
}

export interface Driver {
  factor_name: string;
  contribution: number;
  direction: 'positive' | 'negative' | 'neutral';
  human_readable_explanation: string;
  evidence: Evidence[];
}

export interface Explanation {
  conclusion: string;
  drivers: Driver[];
  data_gaps: string[];
}

export interface ReasoningItem {
  conclusion: string;
  data_source: string;
  logic_chain: string;
  confidence: '高' | '中' | '低';
}

export interface AnalysisResult {
  enterprise_id: string;
  chain_positioning: {
    matches: ChainMatch[];
    abstain: boolean;
    abstain_reason: string | null;
    missing_signals: string[];
  };
  icv_score: IcvScore;
  decision: Decision;
  explanation: Explanation;
  reasoning_trace: ReasoningItem[];
  completeness_warning: boolean;
  anomaly_flags: string[];
  _meta: {
    enterprise_name: string;
    analysis_timestamp: string;
    completeness_score: number;
    anomaly_flags: string[];
    data_warning: boolean;
  };
}
```

------

### 7. `ChainPositioningCard.tsx`（融合方案 §2.1 的可视化，这是文档未提供的关键组件）

tsx



```
// frontend/src/components/ChainPositioningCard.tsx
import { ChainMatch } from "@/lib/types";

const LEVEL_CONFIG = {
  primary: { label: "主环节", color: "bg-blue-600", border: "border-blue-600", dotted: false },
  secondary: { label: "次环节", color: "bg-blue-400", border: "border-blue-400", dotted: false },
  potential: { label: "潜在环节", color: "bg-gray-400", border: "border-dashed border-gray-400", dotted: true },
} as const;

function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 85 ? "text-green-700 bg-green-50" : pct >= 60 ? "text-amber-700 bg-amber-50" : "text-gray-600 bg-gray-100";
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${color}`}>
      {pct}%
    </span>
  );
}

function MatchCard({ match }: { match: ChainMatch }) {
  const cfg = LEVEL_CONFIG[match.match_level];
  return (
    <div className={`rounded-lg border-2 p-3 ${cfg.border} ${cfg.dotted ? "opacity-70" : ""}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className={`text-xs px-2 py-0.5 rounded-full text-white font-medium ${cfg.color}`}>
            {cfg.label}
          </span>
          <span className="text-sm font-semibold text-gray-800">{match.segment_name}</span>
        </div>
        <ConfidenceBadge value={match.confidence} />
      </div>
      <p className="text-xs text-gray-500 mb-2">
        {match.chain_name} · {match.signal_types.join("、")}
      </p>
      <div className="space-y-1">
        {match.evidence.slice(0, 2).map((ev, i) => (
          <div key={i} className="text-xs bg-gray-50 rounded px-2 py-1 font-mono text-gray-600 truncate">
            <span className="text-gray-400 mr-1">{ev.field_path}</span>
            "{ev.field_value}"
          </div>
        ))}
      </div>
      {match.match_level === "potential" && (
        <p className="text-xs text-amber-600 mt-2 flex items-center gap-1">
          <span>⚠</span> 疑似/潜在环节，不纳入招商决策
        </p>
      )}
    </div>
  );
}

export function ChainPositioningCard({
  matches,
  abstain,
  abstainReason,
}: {
  matches: ChainMatch[];
  abstain: boolean;
  abstainReason?: string | null;
}) {
  if (abstain) {
    return (
      <div className="rounded-lg border border-amber-300 bg-amber-50 p-4">
        <p className="text-sm font-medium text-amber-800">弃权：信号不足，无法判定环节</p>
        {abstainReason && <p className="text-xs text-amber-700 mt-1">{abstainReason}</p>}
      </div>
    );
  }

  const primary = matches.filter(m => m.match_level === "primary");
  const secondary = matches.filter(m => m.match_level === "secondary");
  const potential = matches.filter(m => m.match_level === "potential");

  return (
    <div className="space-y-2">
      {primary.map(m => <MatchCard key={m.segment_id} match={m} />)}
      {secondary.map(m => <MatchCard key={m.segment_id} match={m} />)}
      {potential.map(m => <MatchCard key={m.segment_id} match={m} />)}
    </div>
  );
}
```

------

### 8. `backend/app/routers/chains.py`

python



```
from fastapi import APIRouter
from app.services.context_assembly import ContextAssemblyService

router = APIRouter(prefix="/api/chains", tags=["chains"])
assembly = ContextAssemblyService()


@router.get("")
async def list_chains():
    """返回所有可用产业链及其环节"""
    chains = []
    for name, data in assembly.chain_graphs.items():
        chains.append({
            "chain_id": data.get("chain_id"),
            "chain_name": name,
            "segment_count": len(data.get("segments", [])),
            "growth_rate": data.get("growth_rate"),
        })
    return {"chains": chains}
```

------

## 前端 `package.json`

json



```
{
  "name": "firestone-demo-frontend",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "recharts": "^2.12.7",
    "lucide-react": "^0.400.0",
    "clsx": "^2.1.1",
    "tailwind-merge": "^2.4.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.39",
    "tailwindcss": "^3.4.6",
    "typescript": "^5.5.3",
    "vite": "^5.3.4"
  }
}
```

------

## 启动步骤

bash



```
# 1. 克隆/进入项目
cd D:\work\CodexWork\firestone-demo

# 2. 后端
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# 复制环境变量
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY

# 启动
uvicorn app.main:app --reload --port 8000

# 3. 前端（新终端）
cd frontend
npm install
npm run dev                     # → http://localhost:5173
```

验证后端：`curl http://localhost:8000/api/health`
验证产业链：`curl http://localhost:8000/api/chains`

------

## 实施优先级（4周）

| 周次      | 任务                                                         | 验收                          |
| --------- | ------------------------------------------------------------ | ----------------------------- |
| W1 Day1-2 | 建目录结构，写 main.py / cache_service / routers，验证 `/api/health` | curl 返回 200                 |
| W1 Day3-4 | 补充三条链 JSON，完善 context_assembly，验证 `/api/chains`   | 3条链可返回                   |
| W1 Day5   | 替换 system_prompt，接入 LLM，联调 `/api/analysis/run`（用芯创微电子） | 返回合法 JSON                 |
| W2 Day1-3 | 前端骨架：SearchBar + AnalysisPage + RadarChart              | 能发请求、渲染雷达图          |
| W2 Day4-5 | ChainPositioningCard + DecisionPanel + ReasoningTrace        | 四块信息均展示                |
| W3 Day1-3 | ChatAssistant（SSE流式）+ 快捷指令                           | `/explain` `/report` 响应正常 |
| W3 Day4-5 | 数据质量警告展示 + 否决项高亮 + 弃权态渲染                   | 三种异常态均可触发            |
| W4        | 用5家企业校验输出质量，响应时间测试，Docker 验证             | 满足验收标准表                |

------

## 关键风险点及处置

**LLM 输出不合法 JSON**：`llm_engine.py` 中加 `response_format={"type": "json_object"}` + 解析失败时最多重试 2 次，第 3 次返回 503 而不是空数据。

**evidence 原文对不上**：前端展示时对 `field_value` 做高亮，方便业务人员人工核验；后端加断言：`field_value not in input_str` 时在 `anomaly_flags` 中写入 `evidence_mismatch` 警告。

**Σcontribution ≠ score**：后端收到 LLM 结果后立即做求和校验，误差 > 0.5 则在 `_meta` 中标注 `score_inconsistent: true`，前端用 ⚠ 标注分数不可信。
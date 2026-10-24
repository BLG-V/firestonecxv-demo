# 企业画像 × 产业链图谱融合 Demo

本仓库提供一条虚构新能源汽车产业链的离线演示数据。页面与接口中的企业、区域、事件、分数和招商建议均为 **模拟数据**，只用于验证定位、评分、决策、解释及图谱反查的产品流程，不用于真实业务决策。

## 一键启动

在仓库根目录运行：

```powershell
docker compose up --build
```

首次启动前，在仓库根目录 `.env` 配置 `DEMO_VERIFICATION_TOKEN` 和 `DEMO_REQUIRE_VERIFICATION_TOKEN=true`；Docker Compose 默认强制该令牌，避免公开部署时匿名修改共享样本。打开 `http://localhost:5173` 使用页面，令牌可在页面右上角录入。首次运行会初始化 SQLite 演示库，核验操作写入 Compose 命名卷 `demo_data`，重启容器仍会保留。清空演示库需显式执行 `docker compose down -v`。LLM 未配置时，其余演示功能仍可离线使用。

启用 Qwen AI 分析时，在仓库根目录 `.env` 配置服务端变量：

```dotenv
OPENAI_API_KEY=你的模型平台密钥
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=qwen3.8-flash
```

模型密钥只传给后端容器。AI 分析公开调用，每个客户端 IP 每分钟最多 10 次，全站每分钟最多 30 次，单次生成最多 800 tokens。人工核验写操作使用独立令牌：配置 `DEMO_VERIFICATION_TOKEN` 和 `DEMO_REQUIRE_VERIFICATION_TOKEN=true`；令牌不会随 AI 请求发送。公网部署必须启用该校验，并在前置网关配置 HTTPS 和数据备份。前端通过同域 `/api` 访问后端，后端端口不直接映射到宿主机。

没有 Docker 时，可分别启动：

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

另开终端：

```powershell
cd frontend
npm ci
npm run dev
```

## 演示路径

1. 在企业列表查看已确认、候选和无法定位的样本；进入企业画像核对环节及证据原文。
2. 查看环节价值、企业竞争力、风险折减和招商结论；缺数据或超期时不展示档位，否决项明确降档。分数、排名及档位只在本模拟样本中有意义。
3. 打开产业链图谱，点击节点反查企业及模拟缺口，再返回企业页。
4. 在候选归属上进行确认、纠正或驳回；刷新后可观察定位与节点清单变化。

匹配分是未经黄金集校准的演示规则分，不是统计意义上的概率。未来可能进入的环节只供展示和人工核验，不参与招商评分。数据日期由固定演示时钟驱动，以便复现实例。
人工核验针对整条环节定位；逐条证据准确率反馈未纳入本 Demo。

## 验证

```powershell
cd backend
python -m pytest -q

cd ../frontend
npm run build
```

原始设计资料见 `docs/`。本 Demo 选择 React + FastAPI + SQLite；企业数据和规则评分为模拟数据。AI 分析只解释当前画像，不计算或改写规则评分、档位与招商决策。真实数据接入、AI 辅助抽取、概率校准、正式身份权限与高可用生产部署均未纳入此版本。

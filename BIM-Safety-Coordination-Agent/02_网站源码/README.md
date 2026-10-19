# 02_网站源码

## 2026-10-19 实模型版

在组内原平台上完善。Windows 本机依赖已安装并构建完成，双击上级目录的 `Start-Demo.cmd`，启动后访问 http://127.0.0.1:8001/ 。当前外层配置为真实 DeepSeek + Qwen 模式。端口冲突时可显式指定其他端口：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1 -Port 8002
```

已使用项目独立环境：Python 3.11.17、FastAPI 0.141.1、Uvicorn 0.52.4、Pydantic Settings 2.15.0、Node 22.23.3、Vue 3.5.18、Vite 7.1.3。Python 环境在 `backend/.venv-win311`，Python/Node 工具在上级 `.tools`；不替换系统 Python 或 Node。Windows 重装依赖可运行 `scripts/setup.ps1`，完整后端版本见 `backend/requirements-lock.txt`，前端版本见 `frontend/package-lock.json`。

新增自然语言任务、受限工具规划、任务相关规范检索、Safety State、候选决策包和同一 Case 的短期上下文。综合、栏杆高度、固定连续性和人员暴露检查使用相应检查项；专项高度检查会省略空间距离调用。超出 L05 数据范围时要求澄清。

复核绑定人工批准的措施版本和验收参数；提高到 1.5 m 后，1.2 m 证据不通过。修改后的其他文字要求列为人工核验项。默认独立确认未勾选，批准、实施与复核均需实际操作。

支持从所选 05 层楼板真实网格生成检查上下文、上传新 PNG/JPG 后调用 Qwen 提取观察候选，再由人工确认。高度、人员点与进度仍为现场测量或明确标注的演示输入，不让图像模型填造米制参数。历史证据选择与重开策略保留原实现。

模型配置优先读取外层 `D:/BIM-Safety_Coordination_Agent/.env`，仅当其不存在时读取 `backend/.env`。设置 `DEMO_MODE=false`、三项 `MODEL_*` 及三项 `VISION_*` 后重启。接口为兼容 Chat Completions 的 `/chat/completions`，BASE_URL 按供应商填写。规划、说明和措施分别通过结构化适配器调用；越界工具、错误引用及未经依据支持的长度值会被拒绝。已实际联调 `deepseek-v4-flash` 和 `qwen3.7-plus`，模型耗时与 token 写入 SQLite；不保存密钥或原始图片请求内容。

验证：在 `backend` 运行 `.\.venv-win311\Scripts\python.exe -m pytest tests -q -p no:cacheprovider`，32 项通过；前端使用项目 Node 22 执行 `npm run build`，类型检查及生产构建通过。测试数据库位于临时目录，不使用用户密钥。真实 API、全网页新证据闭环报告及截图见上级目录的 `可用版说明.md`、`03_测试与验收/实模型版_20261019` 和 `04_演示与截图/实模型版_20261019`。

## Linux / macOS 本地开发

```bash
# 后端（仅本机）
cd backend
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
DATA_ROOT=../../01_资料与依据 .venv/bin/python -m uvicorn app.main:app --reload --port 8000

# 前端（另一个终端）
cd frontend # Node.js 22
npm install --no-audit --no-fund
npm run dev
# http://127.0.0.1:5173，Vite 代理 /api → 8000
```

局域网分享（同一 Wi-Fi）：

```bash
HOST=0.0.0.0 ./scripts/start.sh
# 终端会打印 http://<本机局域网IP>:8000
```

生产构建：

```bash
cd frontend && npm run build
cd ../backend && .venv/bin/python -m uvicorn app.main:app --port 8000
# FastAPI 托管 frontend/dist，统一 http://127.0.0.1:8000
```

## 后端结构

```text
backend/
├─ app/
│  ├─ main.py          FastAPI 路由、静态前端、文件服务
│  ├─ config.py        路径、模式、模型配置
│  ├─ db.py            SQLite schema / 事务 / WAL
│  ├─ seed.py          从 01_资料与依据 导入种子与 FTS5 二元组
│  ├─ tools.py         确定性 BIM / 空间 / 时间 / 证据 / 规则 / 风险 / 复核工具
│  ├─ services.py      案例、状态机、审核、实施、复核、导出
│  ├─ agent.py         LangGraph 10 节点 + trace
│  ├─ live_model.py    OpenAI 兼容调用 + Pydantic + 引用白名单
│  ├─ model_client.py  模型 HTTP 调用与脱敏统计
│  ├─ vision.py        Qwen 候选、人工确认与来源版本
│  ├─ bim_context.py   所选楼板网格边线与检查上下文
│  ├─ acceptance.py    12 项验收执行器
│  ├─ mesh.py          IfcOpenShell 懒加载与网格缓存
│  └─ errors.py        APIError → {error:{code,message,details}}
├─ tests/test_api.py   后端测试
├─ requirements.txt
└─ runtime/            SQLite / 上传 / 导出 / 网格缓存
```

## 重要配置

配置优先级如上。没有外层配置时，可复制 `backend/.env.example` 为 `backend/.env`。Pydantic Settings 读取模型参数；路径、端口等运行参数在 Windows 用 PowerShell 环境变量或启动参数指定（start.sh 仍会加载 .env 的其他运行变量）：

- `DEMO_MODE=true`：默认，无密钥。
- `DEMO_MODE=false` + 三项 `MODEL_*` 齐全：真实模型模式。
- 三项 `VISION_BASE_URL / VISION_API_KEY / VISION_MODEL` 齐全：启用上传图像候选；缺少配置会明确报错，观察可人工填写确认。
- `DEMO_MODE=false` 但配置不完整：分析接口返回 503 `live_model_config_incomplete`，不会静默降级。
- `DATA_ROOT`：资料根目录，默认 `../../01_资料与依据`。
- `RUNTIME_DIR`：运行目录，默认 `backend/runtime`。

## 数据与状态

- 所有时间 ISO8601 带时区；长度米。
- `expected_case_version` 做乐观锁；冲突 409。
- 状态更新与 `case_events` 写入同一事务。
- `analysis_incomplete=1` 表示关键工具失败，不自动判无风险。
- 规则检索只返回 `status=active` 且已在检查时刻生效的条款；retired 只作历史展示。

## 测试

```bash
cd backend
.venv/bin/python -m pytest tests/test_api.py -q
```

浏览器测试脚本见 `03_测试与验收/ui_playwright.py`（需要 `playwright` 与本地 Chrome）。

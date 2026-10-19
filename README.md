# BIM 施工安全协同智能体

面向建筑施工安全检查的项目级智能体平台。系统以 BIM 模型的空间与构件信息为骨架，把现场检查任务、施工活动计划、现场证据和安全规范条文连接成可审核、可实施、可复核、可重新打开的 Safety Case；模型负责理解与文字候选，距离、时段、阈值、状态流转与最终复核由程序执行，批准和复核由人工确认。

## 主要功能

- **整栋与楼层模型浏览**：覆盖 S1 IFC 中 16,372 个有表示构件、19 个模型楼层，首屏加载约 18 MB GLB，支持按楼层、类别、名称筛选与 GUID 定位。
- **检查任务与实时分析**：从首页输入检查任务、上传现场照片，Agent 流式输出分析过程与实际工具轨迹。
- **检查计划与依据**：生成结构化检查计划、事实与规范依据，并做确定性校核；网页可直接查看本次计划、证据与校核结果。
- **定向补证**：资料缺口时列出补证清单并暂停风险文字与措施生成，此状态下不能批准。
- **三维标注与时空冲突**：板边点选、距边线距离测量、人员点拖动标注；施工活动同时间同空间触发冲突校核，审批后活动锁定并保留版本。
- **整改与证据闭环**：整改说明与证据合并提交，同区域一次确认完成复核，默认导出 Word 检查报告，保留 JSON 与 Markdown 导出。
- **持久任务与中断恢复**：SQLite 图检查点、持久任务、租约与心跳，服务重启后可从中断节点继续。
- **可选角色权限**：viewer / inspector / reviewer / rectifier / admin，令牌写入 HttpOnly 会话。

## 技术栈

- 前端：Vue 3.5、TypeScript、Vite 7、Three.js
- 后端：FastAPI 0.141、Pydantic v2、LangGraph 1.0.10、SQLite（WAL / 外键 / FTS5）、IfcOpenShell 0.9
- 模型：兼容 Chat Completions 协议的对话与视觉接口
- 运行环境：Python 3.11、Node.js 22

## 项目结构

```text
BIM-Safety-Coordination-Agent/    交付包主体
├─ 00_执行计划与自检/             执行计划、合规矩阵、资料整合清单
├─ 01_资料与依据/                 原始方案、安全规范、文献、案例与验收模板
│  └─ 03_数据集/                  S1 构件索引、区域几何、模型检查结果
├─ 02_网站源码/
│  ├─ backend/                    FastAPI 接口、LangGraph 编排、规则与状态机
│  ├─ frontend/                   Vue 3 前端与 Three.js 模型视图
│  └─ scripts/                    start.ps1 / setup.ps1
├─ 03_测试与验收/                 测试报告、分阶段验收记录、Word 导出样例
├─ Start-Demo.cmd                 Windows 一键启动
└─ 可用版说明.md                  当前版本能力、演示路线与边界
docs/                            架构设计、方案对照、数据审计与开发建议
scripts/                         数据集与场景验证脚本
```

## 本地运行

前置：Python 3.11、Node.js 22。

后端环境：

```powershell
cd BIM-Safety-Coordination-Agent\02_网站源码\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-lock.txt
Copy-Item .env.example .env
```

前端构建：

```powershell
cd ..\frontend
npm ci
npm run build
```

启动（构建产物由后端统一托管）：

```powershell
cd ..\backend
$env:DATA_ROOT = "..\..\01_资料与依据"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8003
```

访问 [http://127.0.0.1:8003](http://127.0.0.1:8003)，API 文档在 `/api/docs`。

Windows 下也可双击 `Start-Demo.cmd` 一键启动，该脚本使用交付环境自带的 `.venv-win311` 与 `.tools`；迁移到其他机器时先运行 `02_网站源码\scripts\setup.ps1` 准备锁定依赖。

## 配置

复制 `backend/.env.example` 为 `.env` 后按需填写。

- `DEMO_MODE=true`：不调用外部模型，可完成全部验收流程。
- `DEMO_MODE=false`：需补齐 `MODEL_BASE_URL` / `MODEL_API_KEY` / `MODEL_NAME`；视觉候选另需 `VISION_BASE_URL` / `VISION_API_KEY` / `VISION_MODEL`。配置不完整时分析接口返回 503，不静默降级。
- `DATA_ROOT`：资料根目录，默认 `01_资料与依据`。
- `RUNTIME_DIR`：运行目录，默认 `backend/runtime`。
- `ACCESS_MODE`：`local_demo` 仅本机回环访问；`token` 启用角色令牌模式。

## 数据说明

- 原始 S1 IFC 约 376 MB，超过 GitHub 单文件上限，未纳入仓库。按 `01_资料与依据/03_数据集/S1/原始下载入口.csv` 取得后放入同目录即可启用完整模型几何；缺失时仍可用已解析的构件索引与区域预览数据。
- `data/` 原始点云与影像、`runtime` 数据库、上传件、导出件、虚拟环境、`node_modules` 与前后端构建产物均不在仓库内。

## 验证

```powershell
cd BIM-Safety-Coordination-Agent\02_网站源码\backend
.\.venv\Scripts\python.exe -m pytest -q
```

后端 85 项测试通过；前端 `vue-tsc --noEmit` 类型检查与 `vite build` 生产构建通过。分阶段验收记录见 `03_测试与验收/`。

## 文档索引

- 当前能力与演示路线：`BIM-Safety-Coordination-Agent/可用版说明.md`
- 执行计划与合规矩阵：`00_执行计划与自检/`
- 架构设计与开发路线：`docs/Agent架构设计与开发路线.md`
- 2.0 实现说明：`docs/architecture/Agent框架2.0实现说明_20261019.md`
- 平台评估与完善建议：`docs/已有平台评估与完善建议.md`
- S1 数据审计与 Case 开发建议：`docs/S1数据审计与完整Case开发建议.md`
- 方案对照与下一阶段开发建议：`docs/platform_review/方案对照核查_20261019/方案差距与下一阶段开发建议.md`
- 原始需求方案：`01_资料与依据/02_原始附件/BIM-Safety_Coordination_Agent_方案 (1).docx`
- 任务书与接口约定：`01_资料与依据/06_Astra任务书/`
- 验收执行报告：`03_测试与验收/验收执行报告.md`

## 使用边界

本项目用于安全辅助识别、风险提示和过程留痕，不替代法定施工方案审查、作业许可、现场检查、专业人员签字或安全管理人员的最终判断。

人员位置、防护状态、巡检结果与整改实施为演示输入；图像模型只提供观察候选，不从图片推断米制高度或锚固强度；所选楼板与现场照片的对应关系为演示关联。当前安全场景以 05 层板边为中心，全项目拓扑与自动临空面识别尚未完成，现场验证与对照实验仍在计划内。

## 许可与引用

- S1 数据采用 CC BY 4.0，保留原作者与仓库说明，仅用于研究与文献综述展示。
- buildingSMART 测试模型按其仓库许可使用。
- 安全规范 PDF 来自住房和城乡建设部公开页面，保留来源链接。
- 论文按原许可与引用规范使用，缺失全文的条目已在资料清单标明。

# Agent Forge

面向 AI 辅助研发与个人学习的 Skills 与插件集合，覆盖飞书事项背景收集、存量代码调研、服务端技术方案、旅行英语练习，以及从需求到实现、验证和交付的完整开发流程。可以单独使用专业 Skill，也可以通过 `harness-devflow` 组织连续研发任务，保存上下文、产物与真实检查记录。

## 项目一览

| 项目 | 形态 | 主要用途 |
| --- | --- | --- |
| [harness-devflow](harness-devflow/README.md) | 完整研发流程插件 | Codex 三段流程、前期可行性验证、自动化验收与可恢复任务。 |
| [brownfield-recon](brownfield-recon/SKILL.md) | 独立 Skill | 调研已有代码、接口契约和失败路径，形成修改前的行为基线与保留／替换／移除判断。 |
| [server-tech-design](server-tech-design/SKILL.md) | 独立 Skill | 编写、评审和优化服务端技术方案，讲清主流程、关键决策与相关工程约束。 |
| [lark-context-explore](lark-context-explore/SKILL.md) | 独立 Skill | 从飞书文档、消息、会议等来源收集事项背景，形成带出处、时间线和待确认问题的交接包。 |
| [travel-english-coach](travel-english-coach/SKILL.md) | 独立 Skill | 面向英语基础薄弱者，通过旅行场景练习表达、澄清和求助，保存学习进度并安排复习。 |
| [codex-agent-rules](codex-agent-rules/README.md) | 全局 `AGENTS.md` 模板 | 使用 Computer Use 前要求明确授权，并限制大范围读取、重复失败和冗长工具输出。 |

## 开始使用

```bash
git clone https://github.com/LMJian/agent-forge.git
```

根据任务选择一个入口：

- **完整研发任务**：加载或安装克隆目录中的 `harness-devflow/`，在目标代码仓库中调用 `flow`。插件已包含两个专业 Skills 及其资源。
- **聚焦调研或设计**：单独加载 `brownfield-recon/` 或 `server-tech-design/`，也可以让 Agent 阅读对应的 `SKILL.md`。
- **收集飞书事项背景**：加载 `lark-context-explore/`，提供项目名、文档链接或群等线索，整理可追溯的背景包。
- **练习旅行英语**：加载 `travel-english-coach/`，核对固定档案位置后，读取已有进度或开始首个旅行场景。
- **设置个人执行规则**：将 `codex-agent-rules/AGENTS.md` 安装或合并到 `~/.codex/AGENTS.md`，让新会话默认遵循 Computer Use 授权与低消耗执行约定。

在 Codex 安装插件后，可用 `$harness-devflow:flow` 启动。插件仅以 Codex 为支持目标；具体配置见 [插件使用说明](harness-devflow/README.md#使用)。

首次使用完整流程时，需要在目标仓库的 `.harness/project.json` 中配置该项目实际使用的检查命令；代码托管、接口生成和部署工具按交付需要接入。独立 Skills 按各自说明使用，不需要初始化 Harness 项目。

## harness-devflow：Codex 精简研发流程

运行时依赖 **Python 3.10+ 与 Git**，默认 `profile=codex`、`assistance=autonomous`、`target=local`、`isolation=checkout`。
默认保持当前分支开发；新建／切换开发分支或另开 worktree，必须先有用户明确请求或同意。

1. 需求与可行性：一份决策包合并需求、架构、关键风险实验、测试和任务。
2. 连续实现：自动计算计划，Codex 持续实现及修复。
3. 自测交付：验证产品路径和实际输出，记录自动化与必要人工操作的结果。

内部四个状态中，`plan` 从已接受的决策包生成；要求设计确认时仍保留具体审批。
未证明的关键技术假设阻止正式开发；单元测试或编译成功不能冒充产品验收。
`verify-plan` 显示关键路径优先的检查顺序、历史耗时与复用机会；`verify` 执行并在明确确定性前提下复用证据。
验收按用户入口到最终结果逐步映射，文件回放不能冒充运行时行为；`test-progress` 显示剩余用例和人工批次。

旧任务保留原先的 `light`/`standard`/`release`、引导执行和审批要求。
交付终点仍包括 `local`、`pushed`、`pr`、`merged`、`deployed`；对外动作不因流程配置自动获得授权。
不再维护其他宿主的插件入口，保留旧状态读取和已有适配器只为保护已开始的工作。

```text
$harness-devflow:flow 实现导出功能，先证明关键可行性，自动自测后交付本地版本。
$harness-devflow:flow 查看当前任务的剩余测试与阻塞，继续推进。
```

插件包含 14 个流程 Skills 和 2 个专业 Skills，按需读取。
见 [插件 README](harness-devflow/README.md)、[Codex 合同](harness-devflow/references/codex-workflow.md)、
[本次复盘](harness-devflow/docs/codex-retrospective.md)。

## brownfield-recon：存量逻辑调研

沿入口、核心实现、下游调用、配置和数据存储追踪实际行为，结合相关测试与 Git 历史核实结论。重点识别兼容约束、未确认契约，以及哪些旧行为应当保留、替换或移除，区分当前事实、目标设计和已执行的验证。

默认做与当前变更有关的聚焦调研，以简短的 `report.md` 保存代码版本、行为基线和变更判断。只有范围确实需要时，才补充契约矩阵、待确认问题或采集器生成的证据清单。调研就绪度针对下一阶段判断，不把本地调研结论当作已通过集成或发布验证。

调研本身以只读为主，按约定保存产物；如果用户已要求实施变更，调研完成后继续已授权的工作。

加载该 Skill 后的请求示例：

```text
$brownfield-recon 梳理这个仓库的请求路由、配置加载和失败处理，判断本次改造需要保留、替换或移除哪些行为。
```

具体产物规则见 [调研报告契约](brownfield-recon/references/report-contract.md)。

## server-tech-design：服务端技术方案

先明确核心问题、关键决策和完整流程，再按读者需要组织章节。接口、配置、安全、异常、监控和上线作为按需检查的维度，避免机械填充固定模板。

支持新建方案、设计审查和修改已有文档。修改时同步检查定义、示例、图和引用，合并重复内容；区分现状、设计目标、估算和已验证结果。交付目的地遵循用户要求和可用文档工具。

配套的 [章节指南](server-tech-design/references/section-guide.md)、[写作指南](server-tech-design/references/writing-style.md)、[审查清单](server-tech-design/references/review-checklist.md) 和 [可选模板](server-tech-design/references/template.md) 用于按需展开设计。

加载该 Skill 后的请求示例：

```text
$server-tech-design 根据需求和现有代码写一份本地 Markdown 技术方案，先讲清主流程和关键决策，保留必要约束。
```

## lark-context-explore：飞书事项上下文收集

从项目名、文档链接、群名等线索出发，查询相关文档、消息、会议和人员，整理现状、时间线、关键决策、关系与未决问题。每项结论保留出处，并标明查询时间和覆盖边界。

默认生成本地 `background.md` 和会话摘要；飞书文档、HTML 或妙搭发布按用户明确要求执行。依赖 `lark-cli` 及当前用户已有权限，运行时按需读取相关领域 Skill。随包提供断点、预算、证据和产物校验脚本，以及离线测试。

```text
$lark-context-explore 根据这个飞书文档，整理项目背景、关键决策和未决问题，生成本地交接包。
```

完整范围和授权边界见 [Skill 说明](lark-context-explore/SKILL.md)，离线验证方式见 [维护验证](lark-context-explore/references/evaluation.md)。

## travel-english-coach：旅行英语练习

面向英语基础薄弱者，以点餐、问路、机场、酒店等场景逐轮练习，重点训练表达需求、确认关键信息和主动澄清。默认采用可调整的六个月计划；根据实际表现和出行时间安排进度，区分提示后完成与无提示独立完成。文字练习只评估可观察到的文字表现，发音和听力需有相应音频证据。

随包提供本地进度脚本、命令说明、教学决策场景和回归测试。进度脚本支持能力评估按名称合并、损坏档案拒写、版本冲突检查、课次与复习项查询，以及根据真实复习结果计算下次日期。

学习档案默认保存在 `~/.local/share/travel-english-coach/`，与 Skill 目录分开。可通过 `settings.json` 配置其他固定目录；更新已有安装时保留原配置及档案。脚本依赖 Python 3 标准库，支持 macOS/Linux，具体命令见 [档案说明](travel-english-coach/references/progress.md)。

```text
$travel-english-coach 开始今天的练习，先读取我的学习进度。
```

## 如何选择与组合

- 只需要理解或调研现有实现：使用 `brownfield-recon`。
- 已有清楚的需求和背景，只需要方案编写或评审：使用 `server-tech-design`。
- 需要持续推进需求、实现、验证和交付，并保存可恢复状态：使用 `harness-devflow`。
- 需要从飞书多种来源整理事项背景或交接材料：使用 `lark-context-explore`。
- 需要持续练习旅行英语并接续学习进度：使用 `travel-english-coach`。
- 需要为所有 Codex 项目统一 Computer Use 授权和工具输出约束：安装 `codex-agent-rules/AGENTS.md`。

两个独立 Skills 也有明确的产物交接约定，支持在不同会话中先调研、再设计：

1. `brownfield-recon` 优先遵循指定或项目已有的产物目录，默认写入 `.artifacts/brownfield-recon/<branch-key>/<run-id>/report.md`。报告记录仓库、任务范围、实际分支、代码版本、相关未提交状态和下一阶段就绪度，并在结束时给出入口路径。
2. `server-tech-design` 在仓库相关的方案工作中，先读显式提供的材料，再查项目约定位置及 `.artifacts/`，包含被 Git 忽略的文件。它按任务、范围和源码证据选择报告，不只看文件时间；自定义外部目录需要明确提供路径或项目索引。
3. 设计先读入口报告，再按需读取契约、未决问题和证据；检查相关代码的新变化，复用仍适用的结论与场景。设计引用基线并另存文档，保留原调研记录；缺少调研报告时仍可直接做必要的代码检查。

这是由 Agent 执行的 Skill 交接规则。具体格式与读取方式见 [调研输出契约](brownfield-recon/references/report-contract.md) 和 [设计输入发现规则](server-tech-design/references/recon-inputs.md)。

Harness 已在 `harness-devflow/skills/` 内包含两个专业 Skill 及全部资源，无需再安装根目录的独立版本。包内副本和根目录独立版本保持逐文件一致，维护时同步更新，并运行发行校验检查差异。两种入口均支持通过报告交接：独立调研写入 `.artifacts/` 的报告可以作为 Harness 任务的输入，Harness 任务写入 `.harness/runs/<task>/artifacts/` 的报告也可以被后续独立设计会话读取，并按任务范围重新核验。存量调研在 intake 内按需调用；服务端设计与设计审查使用包内 `server-tech-design`，其他领域保留通用设计路径。

## 维护与验证

在仓库根目录运行：

```bash
python3 harness-devflow/scripts/validate_distribution.py
(cd harness-devflow && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v)
(cd lark-context-explore && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v)
(cd travel-english-coach && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v)
```

发行校验检查插件清单、Skill 路由、资源、文档链接、配置示例，以及内置专业 Skills 与根目录副本的一致性。更新这两个专业 Skills 时，同步其内置副本与 `harness-devflow/references/bundled-skill-origins.json` 中的文件哈希。

测试使用临时仓库和合成数据。真实服务访问、发布和教学效果需在对应使用环境中另行验证，具体范围见各组件的验证说明。

## 目录与分享

```text
.
├── README.md
├── codex-agent-rules/      # Codex 全局规则模板与安装说明
├── harness-devflow/        # 完整插件：宿主清单、Skills、运行时、文档和测试
├── brownfield-recon/       # 独立调研 Skill 及配套资源
├── lark-context-explore/   # 飞书事项背景收集、证据记录和离线校验
├── server-tech-design/     # 独立设计 Skill 及配套资源
└── travel-english-coach/   # 旅行英语教练、独立进度档案工具和回归测试
```

克隆本仓库后，按需使用对应目录：

- 完整开发流程：使用 `harness-devflow/`，按 [插件接入说明](harness-devflow/README.md#使用) 加载或安装。
- 独立调研或设计：将 `brownfield-recon/` 或 `server-tech-design/` 完整目录放入所用宿主的 Skills 目录，也可在任务中指定其 `SKILL.md` 路径使用。
- 飞书事项背景收集：将 `lark-context-explore/` 完整目录放入 Skills 目录，并准备已授权的 `lark-cli` 环境。
- 旅行英语练习：将 `travel-english-coach/` 完整目录放入 Skills 目录；首次使用核对 `settings.json`，更新已有安装时保留其固定档案位置。
- 全局执行规则：参考 [codex-agent-rules](codex-agent-rules/README.md) 将模板安装或合并到个人 Codex 主目录。

分享时可以提供本仓库链接或复制所需的完整目录。复制插件时保留 `.codex-plugin/`、`.claude-plugin/` 等隐藏目录；复制 Skill 时保留配套的 `references/`、`scripts/` 等资源。

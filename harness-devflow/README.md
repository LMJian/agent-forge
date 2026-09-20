# Harness Devflow

面向不同 AI 编码宿主和模型的通用研发插件。提供需求、调研、设计、实现、验证与交付流程，支持 **引导执行 / 自主执行**；宿主能力可接入，内置执行能力始终可用。当前版本 **1.0.0**，运行时仅依赖 **Python 3.10+ 与 Git**。

专业方法由 Skills 提供；流程核心校验实际产物、代码版本和检查记录。Codex、Claude Code 或其他能读文件、执行命令的 Agent 使用同一套完成标准。

## 三个独立的选择

| 选择 | 作用 | 默认值 |
| --- | --- | --- |
| 流程深度 `profile` | 决定设计、审查等必要阶段 | `standard` |
| 执行引导 `assistance` | 决定逐任务检查点或自主连续执行 | `guided` |
| 宿主能力 `host` | 决定原生接入或内置实现 | 通用宿主、内置命令、内置工作树、串行执行 |

引导模式适合需要明确步骤、较短上下文或更强过程约束的任务。运行时每次返回一个具体任务、上游资料、验收和检查命令；每个实现任务通过检查点后再继续。自主模式允许连续执行和批量提交，仍要求最终检查、验收覆盖和交付门禁。

模式由项目或用户选择，不依据厂商名称推断模型水平。缺少宿主能力时，内置流程仍可完成研发；能力声明也不构成并行、调度或发布授权。

## 流程阶段

| 配置 | 开发阶段 | 默认终点 |
| --- | --- | --- |
| `light` | 需求 → 计划 → 实现 → 审查与验证 | 本地 |
| `standard` | 需求 → 设计 → 设计审查 → 测试设计 → 计划 → 实现 → 审查与验证 | 本地 |
| `release` | 标准流程，增加设计确认 | 部署 |

完整阶段目录：

```text
intake → design → design_audit → test_design → design_approval
       → interfaces → plan → implement → review → integration
       → push → pr → monitor → release → deploy → knowledge
```

运行时按任务选择实际阶段。接口更新、集成测试、知识沉淀按需启用；集成测试可放到推送后，以验证远端预览环境。

| 交付终点 | 结束条件 |
| --- | --- |
| `local` | 本地实现和验证完成，可以保留未提交修改 |
| `pr` | 推送已验证提交并创建真实 PR/MR |
| `merged` | 观察到 PR/MR 已合并 |
| `deployed` | 具体发布方案获得批准，部署返回成功结果 |

## 16 个 Skills

| Skill | 职责 |
| --- | --- |
| `flow` | 配置任务、选择必要方法、获取下一步、恢复和交接 |
| `intake` | 范围、模块和验收；小任务的简要实现思路与验证方式 |
| `brownfield-recon` | 存量行为与契约调研，形成可复用基线 |
| `design` | 组织通用设计或调用专业设计能力 |
| `server-tech-design` | 服务端方案编写与审查 |
| `design-audit` | 需求覆盖、跨模块一致性和设计审查 |
| `test-design` | 测试场景与验收映射 |
| `interfaces` | 独立契约变更与代码生成 |
| `plan` | 可验证的小任务、验收映射和依赖批次 |
| `implement` | 逐任务或自主实现，验证模块并集成 |
| `review` | 代码审查、真实检查和修复 |
| `integration-test` | 集成或端到端验证 |
| `delivery` | 推送和创建评审请求 |
| `monitor` | 观察评审、CI 和合并状态 |
| `release` | 发布准备、批准和部署结果核验 |
| `knowledge` | 可选的本地知识沉淀 |

Skills 按需加载。两个专业 Skills 及其全部资源随插件分发，与仓库根目录的独立版本逐字节一致，报告契约相同，两种方式生成的调研报告可以互相复用；流程调用时显式传递调研和设计产物，后续阶段读取实际引用的文件。

## 宿主接入与内置后备

| 能力 | 原生接入 | 内置后备 |
| --- | --- | --- |
| 检查命令 | 显式配置的可信命令桥接器 | 标准库子进程执行，记录退出码和日志 |
| 工作树 | 宿主创建，核心核验后接入 | Git worktree 创建、验证与逐批合并 |
| 多 Agent | 已开放且已授权的宿主工具 | 按依赖串行完成模块 |
| 任务恢复 | 宿主会话 + 通用任务包 | 持久状态、`next` 和 `handoff` |
| 持续观察 | 已授权的宿主调度工具 | 当前会话按需检查、下次恢复 |

通过配置声明当前可用能力，不因检测到某个 CLI 或厂商名就自动开启。没有命令桥接器时，包括 Codex 和 Claude Code 在内的宿主都能通过自身终端工具调用内置检查执行器。原生能力执行失败或结果不明时，先核实结果，不自动换一种执行器重做。

后台唤醒需要可用且已授权的调度器。插件不自带模型服务或常驻调度进程。详情见[宿主契约](references/hosts.md)。

## 获取与使用

复制或克隆完整 `harness-devflow/` 目录，保留 `.codex-plugin/`、`.claude-plugin/`、Skills、运行时及资源文件。

Codex 安装后调用 `$harness-devflow:flow`。开发时也可以要求 Agent 阅读本目录 `skills/flow/SKILL.md`。

Claude Code 可从目录加载：

```bash
claude --plugin-dir /absolute/path/harness-devflow
```

然后调用 `/harness-devflow:flow`。其他 Agent 可直接读取相同 Skill 并执行 CLI。

在消费项目中初始化，填写 `.harness/project.json` 的真实检查命令：

```bash
python3 /absolute/path/harness-devflow/scripts/harness.py --repo /path/to/project init --base main
python3 /absolute/path/harness-devflow/scripts/harness.py --repo /path/to/project doctor
python3 /absolute/path/harness-devflow/scripts/harness.py --repo /path/to/project --task export start --goal '实现导出功能' --profile standard --assistance guided --domain backend
python3 /absolute/path/harness-devflow/scripts/harness.py --repo /path/to/project --task export next
```

`next` 返回当前阶段、必要资料、专业方法和具体操作，并启动尚未开始的当前阶段。Agent 完成工作后使用 `submit --result <file>` 提交结果正文；机器报告外壳和可用检查记录由运行时生成。`status` 只读查看，`handoff --output <file>` 写出可在其他宿主读取的任务包。

支持在 detached HEAD 工作区和有未提交修改的工作区启动。本地单模块可直接验证未提交内容；需要隔离并合并的模块仍要求干净起点及模块提交。提交变化会使旧检查失效，远端交付只接受经过验证的明确提交。

配置示例：[Python 引导执行](examples/python-light.json)、[Python 标准流程](examples/python-local.json)、[Node](examples/node-local.json)。用项目真实命令替换示例中的工具和目录。

## 运行时保证与边界

- 模块依赖、任务 ID、验收覆盖和引导检查点由程序校验。
- 命令记录绑定实际代码指纹、命令配置、执行器、日志和结果。
- 宿主工作树必须属于同一个 Git 仓库，并从要求的准确提交开始。
- 失败、阻断、过期或未确认的外部执行不能算作完成。
- 状态使用原子写入和文件锁；重试有界，冲突与中断保留恢复依据。
- 代码审查、真实测试和项目批准分别记录；所有执行方式沿用同一交付门禁。

这些约束帮助减少遗漏和无效重试。语义正确性和测试充分性仍需专业审查及真实任务评估。本地文件和 Git Hook 不提供防篡改的组织级强制边界，CI 与代码托管平台负责对应策略。

本版本仅接受当前配置、任务和报告契约，不转换历史状态，也不提供旧命令别名。

## 验证与文档

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_distribution.py
```

测试使用临时 Git 仓库、真实检查命令及显式宿主测试桥接器。实际宿主安装、第三方平台认证及不同模型的编码效果需要分别验收。

- [架构与职责边界](docs/architecture.md)
- [Skills 职责与交接](docs/skill-guide.md)
- [运行时与结果格式](skills/flow/references/runtime.md)
- [流程与引导配置](skills/flow/references/profiles.md)
- [宿主契约](references/hosts.md)
- [专业能力交接](references/capabilities.md)
- [交付适配器](references/adapters.md)
- [验证记录](docs/validation.md)

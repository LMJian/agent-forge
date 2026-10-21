# Harness Devflow

面向 **Codex** 的研发插件，运行时仅依赖 Python 3.10+ 和 Git。新任务默认使用
`profile=codex`、`assistance=autonomous`、`target=local`、`isolation=checkout`。不再分发其他宿主的插件清单，
不按模型能力拆分流程；已有项目的配置和任务记录继续保留。

## 默认流程：三个工作阶段

| 阶段 | 实际工作 | 交付依据 |
| --- | --- | --- |
| 需求与可行性 | 合并需求、架构、风险、测试设计和任务计划；先跑关键假设的小型实验 | 一份决策包；未证明的关键风险阻止正式开发 |
| 连续实现 | Codex 在当前分支持续实现和修复，另开开发分支／worktree 先获用户同意 | 实际代码、模块检查、验收映射 |
| 自测交付 | 自动化优先，运行产品入口、检查真实输出、审查差异 | 产品级用例台账和真实检查记录 |

内部仍有 `intake → plan → implement → review` 四个状态，其中 `plan` 从已接受的决策包
自动生成，不需要另写计划文档。原来标准流程中的独立设计、设计审查、测试设计不再是默认关卡。
要求设计确认时，启用 `design_approval`，只对具体决策包确认一次。批准范围变化时再确认；
普通实现步骤不需要人逐项放行。`light`、`standard`、`release` 保留供已有任务和明确要求使用。

## 测试自动化与进度

- 先选择命令/API/回放；适合 GUI 的操作由 Codex 在已有授权范围内完成。
- 决策包列出从用户入口到最终结果的 `journey`，每一步都有观察结果和证据边界；场景通过 `steps` 映射，`proof` 区分运行时与文件产物，`oracle` 说明独立预期来源。
- 人工项必须解释为何不能自动执行，并归入操作批次。未获设备操作授权时保持待验证，不能删除那一步后宣称全部通过。
- `verify-plan` 显示检查顺序、覆盖场景、可复用结果和历史耗时估算；`verify` 先执行 `critical`，再执行 `regression` 与 `packaging`，失败即停止。
- `test-progress` / `status` 提供通过、待执行、失败、阻塞、过期、明确取消、剩余人工项和批次数。
- 单元测试和构建成功不能替代产品级验收；未执行/失败/过期项阻止完成。用户取消的用例记为排除，不算通过。
- 显式声明确定性的本地检查可以在同一模块内复用，声明 `across_stages` 后可跨实现、审查和集成复用；输入、环境、日志、时效或最新失败不符时重新执行。
- 同一问题重复两次后，停止重复要求用户操作，保存输入并本地诊断；不能用又一个理想素材的成功宣称修复。

字段与边界详见 [Codex 合同](references/codex-workflow.md) 和 [决策包示例](docs/codex-packet.example.json)。
程序能校验记录、输入一致性和覆盖，不能代替 Codex 判断实验是否有代表性、输出是否正确。
默认在当前分支开发；新建／切换开发分支或另开 worktree 必须先有明确用户请求或同意。
运行时阻止未经记录授权的工作树创建和分支绑定；原始 Git 命令同样遵守
[分支授权规则](references/branch-consent.md)，不能用工具切换绕过。

## 使用

安装完整目录后，在 Codex 中调用 `$harness-devflow:flow`。本地更新后应新开会话以加载新版 Skill。
消费项目先填写真实检查命令，不能把占位命令配置为成功检查：

```bash
python3 /absolute/path/harness-devflow/scripts/harness.py --repo /path/to/project init --base main
python3 /absolute/path/harness-devflow/scripts/harness.py --repo /path/to/project doctor
python3 /absolute/path/harness-devflow/scripts/harness.py --repo /path/to/project --task export start --goal '实现导出功能'
python3 /absolute/path/harness-devflow/scripts/harness.py --repo /path/to/project --task export next
```

提交决策包后，`next` 处理所选审批和计算计划。实现检查可用 `verify --module MODULE`，最终检查用
`verify`，执行前可用 `verify-plan` 查看成本；实际人工/Agent 结果用 `record-case --result FILE` 记录。`--fresh` 强制重新执行检查。
检查复用不伪装成新执行，也不自动批准设计、GUI、对外写入或部署。

| 交付终点 | 结束条件 |
| --- | --- |
| `local` | 本地实现和验收完成，可保留未提交修改 |
| `pushed` | 推送并核验远端 SHA，不创建 PR |
| `pr` | 创建真实评审请求 |
| `merged` | 观察到合并 |
| `deployed` | 发布批准和实际部署结果核验 |

旧任务保持原来的 profile、检查和审批要求。需要真实范围变更时使用 `configure-flow`；不直接改状态文件。
历史状态兼容只为保护已有工作，不再作为多宿主/多模型适配目标。正常 Codex 路径直接使用本地命令和
Git 工作树；原有命令桥和外部适配器按项目需要保留，不在默认流程中要求配置。

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

## 验证与参考

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_distribution.py
```

测试使用临时 Git 仓库、真实命令、工作树和公开 CLI，覆盖失败、输入变化、审批、产品验收、人工排除和旧任务兼容。
测试用例不是其他宿主的产品兼容承诺。实际安装与新的真实项目效果需要分别记录。

- [Codex 工作流设计依据](docs/codex-retrospective.md)
- [运行时与结果格式](skills/flow/references/runtime.md)
- [流程配置](skills/flow/references/profiles.md)
- [专业能力交接](references/capabilities.md)
- [交付适配器](references/adapters.md)
- [已有改动与检查复用](references/focused-tasks.md)
- [跨仓库关联](references/repository-groups.md)
- [流程归属](references/routing.md)

状态采用原子写入、文件锁、代码指纹和证据摘要；拒绝将失败、未知或过期记录用于交付。
这些是本地执行约束，不是防篡改认证服务。用户身份/语义判断仍依赖实际对话与 Codex 的审查。

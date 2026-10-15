# 流程 Skills 职责与协作

插件包含 14 个流程入口和 2 个专业 Skills，共 16 个 Skills。运行时从 16 个阶段中按任务配置选择实际流程；一个 Skill 可以处理多个阶段，专业 Skill 也可以作为阶段内的方法调用。

| 流程 Skill | 职责 | 输入与完成条件 |
| --- | --- | --- |
| [flow](../skills/flow/SKILL.md) | 选择流程、路由、恢复和按需设计确认 | 根据领域和逻辑能力名选择方法，记录来源；通过 next 获取具体任务；支持引导执行、自主执行和跨宿主交接。 |
| [intake](../skills/intake/SKILL.md) | 明确需求、验收与模块边界 | 按需调用 brownfield-recon，引用修改前基线，形成需求与模块依赖报告。 |
| [design](../skills/design/SKILL.md) | 编写技术方案 | backend 使用包内 server-tech-design，其他领域默认通用设计；方案覆盖各模块，也可跨模块共享。 |
| [design-audit](../skills/design-audit/SKILL.md) | 领域审查与跨模块检查 | 独立审查方案的验收覆盖和契约一致性，发现纳入主报告，解决阻断项后推进。 |
| [test-design](../skills/test-design/SKILL.md) | 设计测试场景与验收覆盖 | 复用调研和设计场景并分配稳定 ID，补齐缺口；运行时校验验收覆盖。 |
| [interfaces](../skills/interfaces/SKILL.md) | 更新独立契约和生成产物 | 按需执行接口或生成工具适配器，验证实际结果；普通接口编码纳入 implement。 |
| [plan](../skills/plan/SKILL.md) | 规划任务、验证方法与依赖批次 | 将具体任务映射到验收标准，记录验证方法与模块依赖。 |
| [implement](../skills/implement/SKILL.md) | 实现、隔离、验证和模块合并 | 按计划任务 ID 执行，可使用项目提供的语言或框架 Skill；引导模式逐任务记录检查点；两种模式都提交真实检查记录并验证模块。 |
| [review](../skills/review/SKILL.md) | 代码审查与检查修复 | 支持项目审查能力；发现纳入主报告，检查记录绑定当前代码版本。 |
| [integration-test](../skills/integration-test/SKILL.md) | 执行集成验证并分析失败 | 按上游场景或轻量验收映射执行，区分产品、测试、环境与未知失败。 |
| [delivery](../skills/delivery/SKILL.md) | 推送代码和创建评审请求 | 按交付终点执行 push/PR，记录适配器返回的实际结果。 |
| [monitor](../skills/monitor/SKILL.md) | 跟进远端状态与评审反馈 | merged/deployed 终点等待合并；持续调度使用宿主实际返回的任务句柄。 |
| [release](../skills/release/SKILL.md) | 发布确认与部署验证 | deployed 终点启用；项目发布要求纳入证据，实际部署通过配置的适配器执行。 |
| [knowledge](../skills/knowledge/SKILL.md) | 归档可复用的研发知识 | 引用基线、版本与检查记录，复用已有知识，仅记录新增或纠正的事实；无新增时标记 no_changes。 |

两个专业 Skills 从插件自身目录加载，默认输出本地 Markdown：

- [brownfield-recon](../skills/brownfield-recon/SKILL.md)：提供现有行为、接口契约与变更前基线，供需求分析、设计和测试复用。
- [server-tech-design](../skills/server-tech-design/SKILL.md)：根据需求和调研证据编写或审查服务端方案，向调用阶段返回文档与发现。

专业调用的请求、资源快照、输出目录和报告转换见[能力契约](../references/capabilities.md)。运行时校验报告结构、覆盖关系、实际命令和证据新鲜度；文档质量、调研结论与审查深度由 Agent 和项目验证共同保障。验证范围见[验证说明](validation.md)。

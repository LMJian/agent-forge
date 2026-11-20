# Agent Rules（Codex / DeepSeek Harness）

一份可复用的用户级 `AGENTS.md` 模板，约束操作授权、任务范围、验证结论和工具消耗。同一份文本供 Codex 与 DeepSeek Harness 使用。

它不是 Skill。Skill 只在匹配到相关任务时加载，而用户级 `AGENTS.md` 会作为常驻规则在会话开始时读取，更适合保存必须持续生效的工作约定。

两个宿主读取的位置不同，内容相同：

| 宿主 | 用户级规则位置 |
| --- | --- |
| Codex | `${CODEX_HOME:-~/.codex}/AGENTS.md` |
| DeepSeek Harness | `$DSH_HOME/AGENTS.md`（默认 `~/.dsh/AGENTS.md`），其次 `<agentsHome>/AGENTS.md`（默认 `~/.agents/AGENTS.md`） |

## 包含的规则

- 保留严格的 GUI 首次授权和开发分支／worktree 授权要求；同一范围内复用已获授权。
- 持续遵守本任务的有效约束；区分提交、审批、发布和撤销，停止后续操作不等于取消已有工单。
- 核对写入目标，保留已有工作和优化，只做必要行为变更；具体工程检查交给项目与相关 Skill。
- 窄范围查询、限制输出、诊断重复失败；按变更与证据决定复验，按实际观察结果报告交付状态。

## 安装

如果还没有个人全局规则：

```bash
# Codex
mkdir -p "${CODEX_HOME:-$HOME/.codex}"
cp AGENTS.md "${CODEX_HOME:-$HOME/.codex}/AGENTS.md"

# DeepSeek Harness（preset 已挂载 agent-instructions，读取用户级指令链）
mkdir -p "$HOME/.agents"
cp AGENTS.md "$HOME/.agents/AGENTS.md"
```

如果已有同名文件，请把本目录中 `AGENTS.md` 的章节合并进去，避免覆盖原有约定。两个宿主都在会话开始时读取用户级规则，因此安装或更新后请开始一个新会话验证；本次实测中，会话运行期间新增该文件也会被注入。

仓库根目录的 `scripts/sync-deepseek.sh` 会同时同步这两个位置，并做差异检查和备份。

## 使用边界

这份模板降低无效上下文和工具输出，不能把模型额度消耗固定在某个数值。实际消耗仍受模型、推理档位、任务复杂度和其他共享额度任务影响。

项目目录中的 `AGENTS.md` 可能增加更具体的约定。发布或采用项目级规则时，应保留用户对 GUI 和开发分支的授权边界。

## 维护验证

在仓库根目录运行 `python3 -m unittest discover -s codex-agent-rules/tests -v`，检查两个授权章节的原文保护及反例案例完整性。
[本地反例](evals/cases.json) 用于推演允许的下一步和禁止动作；保留实际回答，再按 criteria 复核。不要真的执行未授权操作来测试规则。
自动检查只证明条款和案例的完整性；本地推演也不代表独立模型评测，规则文本本身不是权限执行器。

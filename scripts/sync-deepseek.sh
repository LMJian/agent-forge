#!/usr/bin/env bash
# 把 agent-forge 的 Skill 与规则同步到本机 DeepSeek Harness / Codex 安装位置。
#
#   scripts/sync-deepseek.sh          备份并覆盖本地副本
#   scripts/sync-deepseek.sh --check  只比较差异，不写文件；有差异时退出码 1
#
# 可用环境变量覆盖位置：
#   DSH_SKILLS_DIR           默认 ~/.agents/skills
#   DSH_AGENTS_DIR           默认 ~/.agents（其 AGENTS.md 是 DSH 用户级指令链）
#   CODEX_HOME               默认 ~/.codex
#   AGENT_FORGE_BACKUP_DIR   默认 ~/.local/share/agent-forge/backups
#
# harness-devflow 的 DSH 插件以本地链接方式安装，仓库即生效源，无需复制；
# 脚本只检查安装状态，并提示需要重启或新开会话才会重新读取 Skill 正文。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_DIR="${DSH_SKILLS_DIR:-$HOME/.agents/skills}"
AGENTS_DIR="${DSH_AGENTS_DIR:-$HOME/.agents}"
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
BACKUP_ROOT="${AGENT_FORGE_BACKUP_DIR:-$HOME/.local/share/agent-forge/backups}"
SKILLS=(brownfield-recon lark-context-explore server-tech-design travel-english-coach)
CHECK=0
[[ "${1:-}" == "--check" ]] && CHECK=1

case "$SKILLS_DIR" in
  /*) ;;
  *) echo "DSH_SKILLS_DIR 必须是绝对路径：${SKILLS_DIR}" >&2; exit 2 ;;
esac
case "$AGENTS_DIR" in
  /*) ;;
  *) echo "DSH_AGENTS_DIR 必须是绝对路径：${AGENTS_DIR}" >&2; exit 2 ;;
esac
case "$CODEX_HOME_DIR" in
  /*) ;;
  *) echo "CODEX_HOME 必须是绝对路径：${CODEX_HOME_DIR}" >&2; exit 2 ;;
esac

STAMP="$(date +%Y%m%d-%H%M%S)"
DRIFT=0
CHANGED=()

# 比较两个目录或文件；不同则返回 1。
same_tree() {
  if [[ -f "$1" && -f "$2" ]]; then
    cmp -s "$1" "$2"
    return
  fi
  diff -rq "$1" "$2" >/dev/null 2>&1
}

# 同步一个目录或文件：先备份现有副本，再整体替换。
sync_entry() {
  local source="$1" target="$2" label="$3"
  if [[ ! -e "$target" ]]; then
    if (( CHECK )); then
      echo "[缺失] ${label} -> ${target}"
      DRIFT=1
      return
    fi
    mkdir -p "$(dirname "$target")"
    cp -R "$source" "$target"
    echo "[新增] ${label} -> ${target}"
    CHANGED+=("$label")
    return
  fi
  if same_tree "$source" "$target"; then
    echo "[一致] ${label}"
    return
  fi
  if (( CHECK )); then
    echo "[差异] ${label} -> ${target}"
    diff -rq "$source" "$target" 2>/dev/null | sed 's/^/    /' | head -20
    DRIFT=1
    return
  fi
  local backup="$BACKUP_ROOT/$STAMP/$label"
  mkdir -p "$(dirname "$backup")"
  cp -R "$target" "$backup"
  rm -rf "$target"
  cp -R "$source" "$target"
  echo "[更新] ${label} -> ${target}（备份：${backup}）"
  CHANGED+=("$label")
}

echo "仓库：${REPO_ROOT}"
echo "Skill 目录：${SKILLS_DIR}"
echo "用户级规则：${AGENTS_DIR}/AGENTS.md（DSH）、${CODEX_HOME_DIR}/AGENTS.md（Codex）"

for name in "${SKILLS[@]}"; do
  sync_entry "$REPO_ROOT/$name" "$SKILLS_DIR/$name" "$name"
done

sync_entry "$REPO_ROOT/codex-agent-rules/AGENTS.md" "$CODEX_HOME_DIR/AGENTS.md" "codex/AGENTS.md"
# DeepSeek Harness 用户级指令链：$DSH_HOME/AGENTS.md 然后 <agentsHome>/AGENTS.md。
sync_entry "$REPO_ROOT/codex-agent-rules/AGENTS.md" "$AGENTS_DIR/AGENTS.md" "dsh/AGENTS.md"

# harness-devflow：检查 DSH 插件是否已以链接方式安装到某个 profile。
PLUGIN_TARGET="$REPO_ROOT/harness-devflow/dsh"
PLUGIN_LINK=""
for candidate in "$HOME"/.dsh/profiles/*/node_modules/@local/harness-devflow-dsh; do
  if [[ -L "$candidate" || -d "$candidate" ]]; then
    PLUGIN_LINK="$candidate"
    break
  fi
done

if [[ -n "$PLUGIN_LINK" ]]; then
  echo "[已安装] harness-devflow DSH 插件：${PLUGIN_LINK}"
  if [[ -L "$PLUGIN_LINK" ]]; then
    echo "          链接目标：$(readlink "$PLUGIN_LINK")（仓库改动需重启 DSH 或新开会话后重新读取 Skill 正文）"
  fi
else
  echo "[未安装] harness-devflow DSH 插件"
  echo "          在 DeepSeek Harness 中执行：plugin_manager install_bundle target=${PLUGIN_TARGET}"
  echo "          或使用 Plugins → Add plugin 选择该目录"
fi

if (( CHECK )); then
  if (( DRIFT )); then
    echo "检查结果：存在差异（运行本脚本不带 --check 即同步）"
    exit 1
  fi
  echo "检查结果：本地副本与仓库一致"
  exit 0
fi

if (( ${#CHANGED[@]} == 0 )); then
  echo "同步完成：无需更新的副本"
else
  echo "同步完成：已更新 ${#CHANGED[@]} 项"
fi

# 本地学习档案

仅依赖 Python 3 标准库，支持 macOS/Linux。脚本通过文件锁、revision 检查和原子替换防止写入冲突；每次读取和保存都完整校验课次、能力与复习项。当前档案损坏或更新无效时拒绝保存，不覆盖当前文件及 `progress.previous.json`。该备份保留上一次成功写入前的版本；恢复前先检查两份文件，不能自行丢弃新记录。

`settings.json` 默认使用 `~/.local/share/travel-english-coach`，脚本将 `~` 展开为当前用户的主目录。也可配置其他绝对路径；档案目录应与 Skill 分开，并在不同会话中保持固定。更新已有安装时保留其配置，不覆盖、重置或迁移档案。学习记录不随 Skill 分发。

## 命令

将下面 `/absolute/path/to/skill` 替换为实际 Skill 路径；不要执行带占位符的命令。

```bash
python3 /absolute/path/to/skill/scripts/progress.py show
python3 /absolute/path/to/skill/scripts/progress.py sessions --status in_progress
python3 /absolute/path/to/skill/scripts/progress.py get session <session-id>
python3 /absolute/path/to/skill/scripts/progress.py reviews --query "repeat"
python3 /absolute/path/to/skill/scripts/progress.py get review <item-id>
python3 /absolute/path/to/skill/scripts/progress.py init
python3 /absolute/path/to/skill/scripts/progress.py save --file /absolute/path/to/patch.json --expected-revision 0
```

- `show` 只读，输出档案位置、revision、个人目标、计划进度、最近三个课次、单独列出的最多三个未完成课次、十个最先到期的复习项及完成次数。需要时用 `show --limit 30` 扩大最近课次和复习窗口（最大50）；旧的未完成课次不会因最近已完成课程增多而隐藏。
- `get session <id>` / `get review <id>` 按精确 ID 读取一个条目；档案已存在但未找到条目时返回非零退出码。档案尚不存在时，所有读取命令返回 `not_initialized` 且不创建文件。不要执行未替换的 ID 占位符。
- `sessions --status in_progress` 列出未完成课次；可选 `all` / `completed`。`reviews --query <关键词>` 搜索 ID、英文、中文释义和问题说明，包括未到期条目；`reviews --due --today YYYY-MM-DD` 只筛选到期项。两种列表默认10条，可用 `--limit 1..50 --offset N` 分页，返回总数和 `next_offset`；只有 `next_offset=null` 才到末页。
- `init` 幂等；已有档案不会覆盖。初始档案：英语基础薄弱、尚未测评、没有已完成课次。
- `save` 从文件读取局部更新，只合并提供的字段；必须给出上次读到的 revision。成功返回新 revision、保存路径及条目数量；失败返回非零退出码。
- `--data-dir /temporary/directory` 是全局参数，放在子命令之前，仅用于隔离测试或用户明确指定的另一个档案。正式学习使用配置中的固定目录，不随任务改路径。
- 更新文件放在当前工作区的临时目录中，不将整段 JSON 拼接进 shell 命令。

## 更新格式

顶层只允许 `profile`、`progress`、`session`、`review_items`、`review_results`，全部可选，但更新不能为空。一份更新可以同时保存课次和本次真实复习结果；任一部分无效时整份拒绝写入。

`profile` 可更新字段：`goal`、`destination`、`departure_date`、`daily_minutes`、`days_per_week`、`plan_months`。目的地或日期不明时保留 `null`，不要猜年份；相对出行时间可在 `progress.notes` 保存原意。基础描述固定为“英语基础薄弱”。

`progress` 可更新字段：`phase`（基础/常见任务/综合应用）、`level_note`、`next_lesson`、`next_assessment_date`（ISO日期或null）、`assessment`（四项能力及依据组成的对象）、`notes`。`assessment` 和课次 `abilities` 都按能力名称合并：省略的名称保持不变，`{}` 不清空；仅在明确要删除错误记录时用 `{"能力名称": null}`。每项值必须完整提供 `{status, evidence}`，不能只更新状态而保留不匹配的旧依据。

首次使用某个课次 ID，必须提供 `date`（ISO日期）、`status`（in_progress/completed）、`topic`、`mode`（text/voice/mixed）。后续同 ID 更新可省略未变字段；`minutes` 为实际已知的非负整数或 null；`summary`、`abilities`、`next_step` 可更新。`abilities` 格式为任务名到 `{status, evidence}` 的映射，status 为独立完成/需要提示/需要重练/未评估。同 ID 不重复累计完成次数。一个课次可包含多个场景；在 summary 和 abilities 中合并已练内容。

`review_items` 用于建立或编辑条目：首次提供 `id`、`phrase`、`meaning`、`next_review`（ISO日期），可选 `issue`；后续同 ID 更新可省略未变字段。新条目的 `attempts=0`、`last_result=未评估` 由脚本设置。初次教学的提示情况写在课次能力或 `issue` 中，不冒充一次复习。已有调度记录的条目若明确调整 `next_review`，脚本重算间隔；日期须晚于上次复习日。

`review_results` 只提交实际发生的复习，每项提供 `id`、`reviewed_on`（学习者当地日期）、`result`（独立完成/需要提示/需要重练）、`evidence` 和 `mode`（text/voice/mixed）。同一更新中同一条目最多一次；不能填“未评估”或早于已记录的上次复习日。示例：

```json
{"review_results": [{"id": "request-repeat", "reviewed_on": "2026-10-16", "result": "独立完成", "evidence": "文字练习：换成酒店场景后，无提示主动请求重复。", "mode": "text"}]}
```

这仍是格式示例，不能写成真实记录。脚本仅在提交真实结果时增加 `attempts`，保存 `last_result`、`last_reviewed_on`、`interval_days`、`last_evidence`、`last_mode` 并计算 `next_review`。默认独立完成逐步采用1/3/7/14天间隔，14天后保持；同日再次独立完成不升级间隔，需要提示或重练统一设为1天。用户明确设置了更长间隔时，后续成功不会自动缩短它。这是可调整的练习安排，不代表学习效果测定。

旧 schema v1 档案保持兼容：旧条目的次数和结果保留，不补造复习日期。没有间隔记录时，下次真实复习从1天间隔开始。读取不迁移或重写档案；原有更新文件若直接编辑 `attempts` / `last_result` 会被拒绝，应改用 `review_results`，不能因此重置档案。

以下仅演示格式，不能作为真实学习记录写入：

```json
{
  "progress": {
    "next_lesson": "复习请求重复，再练酒店入住"
  },
  "session": {
    "id": "example-session-unique-id",
    "date": "2026-10-09",
    "status": "in_progress",
    "topic": "餐厅点餐",
    "mode": "text",
    "minutes": null,
    "summary": "完成点餐场景，仍需要关键词提示。",
    "abilities": {
      "表达点餐需求": {"status": "需要提示", "evidence": "给出句子开头后完成表达。"},
      "听懂服务员问题": {"status": "未评估", "evidence": "本次仅文字交流。"}
    },
    "next_step": "练习确认价格"
  },
  "review_items": [
    {
      "id": "request-repeat",
      "phrase": "Could you say that again, please?",
      "meaning": "请再说一遍好吗？",
      "issue": "遇到不理解的问题时需要提示才会使用",
      "next_review": "2026-10-10"
    }
  ]
}
```

日期使用学习者当地日期；缺少可靠时区时询问或标明采用的时区，不硬编码示例日期。脚本默认按运行设备当地日期筛选到期条目；与学习者时区不一致时传 `show --today YYYY-MM-DD`。

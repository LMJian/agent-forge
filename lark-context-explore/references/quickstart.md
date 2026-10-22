# 轻量记录入口

普通任务只需本页；技术版本核对、恢复和完整审计再读 state.md。light 与 audit 使用相同的原始回执、预算和写入保护；区别是按轮批量登记与按需加载详细规程，不削弱事实检查。所有脚本只操作本地记录，绝不执行 Lark 或授予权限。

## 初始化一次

准备 questions.json，例如：

```json
[{"id":"q1","text":"当前决定及取舍是什么？","status":"unanswered","claim_ids":[],"gaps":["尚未读取"],"requires":[]}]
```

requires 按问题选 document/message/meeting/code/runtime，不预设必须有文档。完整背景包默认 full；用户明确限定单个问题时加 `--coverage-scope targeted`。授权的远端载体用 --document / --html / --publish；--read-only 允许本地 HTML。

```bash
python3 <技能目录>/scripts/check_artifacts.py init <任务目录> --topic "事项名" --read-only --questions-file questions.json --start
```

默认 collection 为 40 次/600 秒、delivery 为 15 次/300 秒，总计 55 次/900 秒。用户上限优先；复杂任务的初始计划、等待用户的 pause/resume 见 state.md。记录所有失败、翻页、重试和实际有效时间。

## 每次请求：预留 → 原生执行 → 封存

request.json 例子（替换为实际参数和环境）：

```json
{"argv":["lark-cli","im","+chat-search","--query","事项名","--as","user"],"execution_context":{"runner":"exec_command/native-shell","sandbox":"use_default","identity":"user"},"question_ids":["q1"]}
```

首次使用接口域加 --probe；文档可用 outline，群/消息/会议直接用相应最小只读查询，表格可用 sheets +info 或 base +base-get。成功的空搜索只证明接口可调用，不证明实体不存在或已读正文。跨域或环境变化后先单次探测；禁止探测写接口、page-all 或整份逐字稿。准确参数以当前 CLI 帮助为准。

```bash
python3 <技能目录>/scripts/run_state.py prepare <任务目录> --file request.json --probe
```

按返回的 call_id、capture_stdout、capture_stderr，在实际原生环境执行完全相同 argv，将 stdout/stderr 重定向到指定文件。保存真实退出码，不用 Python subprocess 改换运行环境或将 JSON 字符串当作 shell 转义。

```bash
python3 <技能目录>/scripts/run_state.py finish <任务目录> --call-id CALL_ID --stdout calls/CALL_ID/stdout.capture --stderr calls/CALL_ID/stderr.capture --exit-code 0 --update-file update.json
```

--update-file 可省略。带上它可同时登记本次来源；sources 中缺省 call_id 自动引用本次调用。响应已封存后，即使可选更新无效，实际调用记录也保留；修复更新后用 update 重试，不能重发网络请求。

## 按轮批量更新

update.json 可以同时包含下列字段；省略未变化的字段，按 ID 增加/更新，sources 不覆盖旧版本。脚本自动继承来源时间、revision 和响应哈希，并验证整个批次。两个 JSON 文件通过本地事务日志恢复，避免手改相互引用。

```json
{
  "sources":[{"id":"s1","call_id":"真实CALL_ID","kind":"message","locator":"真实群/消息ID和时间","scope":"message","provenance":"primary"}],
  "claims":[{"id":"c1","text":"评审决定采用 B","status":"decided","current":true,"support":[{"source_id":"s1","kind":"decision","locator":"消息ID/决策原文"}]}],
  "questions":[{"id":"q1","text":"当前决定及取舍是什么？","status":"answered","claim_ids":["c1"],"gaps":[],"requires":["message"]}],
  "coverage":{"messages":{"status":"examined","reason":"已读实际决策窗口；其余分页未覆盖","call_ids":["真实CALL_ID"]}},
  "round":{"branch":"decision","new_claim_ids":["c1"],"resolved_questions":["q1"],"new_conflicts":[]}
}
```

```bash
python3 <技能目录>/scripts/run_state.py update <任务目录> --file update.json
```

全文读取仍需 full_read_reason；大型响应先用 excerpt/rg 窄读。每轮开始查 status，只给关键事实建 claim，不逐条登记无关实体。

完整背景包覆盖键为 documents/chats/messages/meetings/prehistory/decision_discussion。每行 status 为 examined/skipped/partial/blocked，必须有具体 reason；examined 引用实际成功、同域的 call_ids。跳过说明用户范围或已有证据为何足够；partial/blocked 保留真实缺口，不能标完整。不要求为填表机械查询所有域，也不能把失败接口或标题摘要当作已读证据。

## 登记与交付

```bash
python3 <技能目录>/scripts/run_state.py artifact <任务目录> --id report --file background.md
python3 <技能目录>/scripts/check_artifacts.py check <任务目录>
```

图另外登记/验证；远端创建与发布只在授权后读 delivery.md。完整背景包即使存在缺口也应交付，明确已完成部分、未覆盖内容和实际停止原因，不能修改记录求全绿。

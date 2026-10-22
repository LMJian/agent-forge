# 远端交付记录

仅当已授权创建文档或发布时读取。以下 operation 命令只写本地状态；实际 Lark 请求仍按 prepare → 原生执行 → finish 记录，phase=delivery。结果不确定时先按 state.md 对账。所有示例 ID、字段路径和检查内容均替换为真实回执。

## 绑定输入，再提交

先登记 background.md、background.xml、引用的 .mmd，或 index.html。每种操作 start 绑定本次真实输入的 artifact_ids，首项为直接提交文件，其余是相关正文/图。文件哈希自动计算，不手填。

```json
{"kind":"document","action":"start","artifact_ids":["xml","report","relations"]}
```

```bash
python3 <技能目录>/scripts/run_state.py operation <任务目录> --file operation.json
```

kind 为 document/app/publish。start 保留唯一标签和 inflight；新应用以 HTML 为输入。成功 app_id 的实际可见范围核验后才能 start publish。已授权的首次 create 可沿用同环境成功的只读探测，但必须单次提交；不能把写入当作权限探测。

## 保存回执

```json
{"kind":"document","action":"result","status":"succeeded","call_id":"真实创建调用ID","receipt":{"id":"真实document_id","url":"真实URL"}}
```

ID/URL 必须出现在该次成功调用的原始 JSON 中。创建 app 的 receipt 只需 id；发布成功要 url，受理未完成记 submitted 并保留 release_id。只有 release_id 时先查询，不能声称已发布；后续 release-get 的成功回执更新原尝试。

超时记 unknown，保留旧 ID/输入指纹。对账找到唯一对象后，result 可带 reconciled=true、reason 与 checks，引用实际 token 的 docs +fetch、已定位应用的 access-scope-get 或已知 release 的 release-get 回执，更新原尝试而不重新 create。仍需做后续 verify。明确失败使用实际失败 call_id；只有可靠对账证明未应用、写明 reason 才可 confirmed_not_applied=true 并重试一次。空搜索不证明未写入；同一 inflight 写入不能再次预留。脚本不自动重试、不删除对象、不改变权限。

## 窄回读与可见范围

文档创建成功后，窄读实际 token 对应的关键结论和图结果。operation verify 校验回读对象、成功原始响应、关键文本和 revision：

```json
{"kind":"document","action":"verify","call_id":"真实回读调用ID","checks":["应当出现的关键结论短句","另一个关键原文片段"]}
```

checks 是预先选定的验收锚，不能在失败后换成无关命中串。文本通过不代表画板已渲染，仍检查 warnings、资源块和实际返回的图结果；图失败应在正文和交付中说明。语义一致性与图内容需执行者核对，脚本不宣称自动证明。

应用创建后，用 +access-scope-get 查询该 app_id。以下以响应 data.scope="creator" 为合成示例；实际字段和值以本机 CLI 为准，先核对帮助和真实响应，不猜平台默认值：

```json
{"kind":"app","action":"verify","call_id":"真实权限读取调用ID","checks":["creator"],"visibility_locator":"data.scope"}
```

脚本沿 visibility_locator 从原始 JSON 取值，并与 run.delivery.expected_visibility（默认 creator）比较。若 CLI 使用不同的创建者枚举，先根据已读官方命令说明记录对应的 expected_visibility 和依据；不能把全租户/指定成员值改称创建者范围。扩大受众必须取得独立授权，不执行 +access-scope-set 来消除差异。无法可靠映射时保留未确认，停止发布。

check 的 delivery_missing 分别报告未绑定的历史操作、输入版本变化、缺少成功调用/回读、权限未核验。正文、XML 或图更新后，旧成功回执不会证明当前版本已交付；保留旧操作历史，按用户对更新目标的授权另行处理，不能清空历史重复 create。

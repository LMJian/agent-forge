# 本次任务的事实与断点记录

记录留在任务产物目录，不写入 Skill 或持久记忆。主 agent 合并事实；本地 CLI 用文件锁串行更新 run.json。状态只是证据，不是授权来源。示例路径、token、问题和执行环境必须替换为本次真实值。

## 初始化、计划与时钟

```bash
python3 <技能目录>/scripts/check_artifacts.py init <任务目录> --topic "项目名" --read-only
python3 <技能目录>/scripts/run_state.py questions <任务目录> --file <问题文件>
python3 <技能目录>/scripts/run_state.py clock <任务目录> --clock-action start --phase collection
```

默认只交付本地。按用户已授权载体选择 init 的 --document、--html、--publish（隐含 HTML）或 --read-only。只读可组合本地 HTML，不能组合远端文档/发布。初始化拒绝覆盖已有文件。工具只操作本地记录；不调用 Lark、登录、发布或浏览器。

问题文件是数组，每个问题含 id、text、requires、status、claim_ids、gaps：

```json
[{"id":"q1","text":"核心模块和职责是什么？","requires":["document","code"],"status":"unanswered","claim_ids":[],"gaps":["尚未读方案和对应实现"]}]
```

requires 可为空（普通消息/会议背景），或选择 document/code/runtime。不要给普通背景任务机械添加代码或线上要求。status 为 answered/partial/unanswered，后两者要写具体 gaps；answered 需关联 claims。time_scope 默认 current；历史取舍问题可用 historical，允许引用已被替代的历史事实。即使 requires 为空，完整覆盖仍须至少一条适用于该时间范围、且有可读来源支撑的 claim；question_coverage 中的 supported_claim_ids 列出这些 claim。用 questions 命令更新时保留已被调用引用的问题 ID。

默认 collection 40 次/600 秒，delivery 15 次/300 秒，total 55 次/900 秒。复杂任务可在第一条调用前一次性设定计划；此后增额必须有用户明确指令。预算文件示例：

```json
{"authority":"default","reason":"六个技术问题涉及飞书和多个仓库，预留代码核对与报告时间","limits":{"collection":{"calls":40,"seconds":1500},"delivery":{"calls":5,"seconds":600},"total":{"calls":45,"seconds":2100}}}
```

用 run_state.py budget <任务目录> --file <预算文件> 应用。用户明确上限用 authority=user 和 user_instruction（原话或消息定位），标为 user_hard；不得把自己估算写成用户授权。阶段额度之和不得超过总额，避免消耗交付预留。

切阶段先暂停旧时钟，再启动新阶段；等用户/离线前暂停并写原因，恢复后 resume。有效时间由真实时间段计算，包含分析、CLI 和本地代码阅读；并行只计一次墙钟时间。

```bash
python3 <技能目录>/scripts/run_state.py clock <任务目录> --clock-action pause --reason "等待用户补充仓库范围"
python3 <技能目录>/scripts/run_state.py clock <任务目录> --clock-action resume --phase collection
python3 <技能目录>/scripts/run_state.py status <任务目录>
```

无法事先暂停的异常中断，保留原时间并标明不确定/可能多计，不能事后伪造精确暂停段。collection 用尽转入预留交付阶段；total 用尽只保存状态、汇报缺口，不继续扩展或默默增额。已发出的慢请求可能导致超时，保留真实值并说明；工具只能阻止下一次预留，不能中断外部 CLI 或模型分析。

## 每次调用：预留 → 原生执行 → 封存

先准备 request.json，完整 argv 含所有查询参数、分页和 --as user；不写 token/cookie/密钥。execution_context 如实描述 runner、sandbox、identity，存在多账号/profile 时加非敏感区分字段。改变任一字段即新环境。

```json
{"phase":"collection","argv":["lark-cli","docs","+fetch","--doc","实际TOKEN","--scope","outline","--as","user"],"execution_context":{"runner":"exec_command/native-shell","sandbox":"use_default","identity":"user"},"question_ids":["q1"]}
```

1. run_state.py prepare <任务目录> --file <request.json> --probe 预留唯一一次 outline 探测。普通查询不带 --probe，但必须引用已有 question_ids。全文查询另写 full_read_reason。
2. prepare 返回 call_id、capture_stdout、capture_stderr；它不会执行 argv。在记录的环境里直接执行原生 lark-cli，将两个流重定向到这两个独立文件。实际 argv 必须与记录一致，保存真实退出码。不要用 Python subprocess 包装批量 Lark 请求，也不要把 JSON 字符串当 shell 转义。
3. 返回后立刻运行 run_state.py finish <任务目录> --call-id <ID> --stdout calls/<ID>/stdout.capture --stderr calls/<ID>/stderr.capture --exit-code <真实退出码>。原样封存 .raw 和 SHA-256，只输出身份、revision、长度等摘要；失败正文同样保留。工具响应到 finish 的间隔应尽量短，finished_at 是本地封存时间，不是服务端事件时间。
4. 探测须 exit=0 且响应 ok=true、identity=user。更换 sandbox（含提权）、runner 或 profile 后重新单次探测。Keychain、401/凭证失效、连接拒绝/重置、DNS 或超时等错误使环境失效，先诊断或按会话规则申请所需授权，再成功完成一次新探测后恢复普通查询。对象级 403 单独记缺口。
5. 独立查询逐个 prepare，文件锁内 pending 即占额度；仅执行预留成功的项。每个 finish 只封存一次；重试重新 prepare，原失败文件不可覆盖。中断遗留 pending 保持未确认并占额度，先对账实际命令是否发出，不静默删除。

没有文档 token 时，可先在同一原生环境做一次最小发现查询。用 prepare --probe 记录 docs +search 并写 discovery_reason；只允许单次发现，尚未视为 outline 探测成功。获得 token 后完成标准探测再展开。不要伪造 token 或把搜索伪标成 outline。

只对成功调用登记可读来源：

```bash
python3 <技能目录>/scripts/run_state.py source <任务目录> --call-id <ID> --id s1 --kind document --locator "真实URL#章节" --scope outline --provenance primary
python3 <技能目录>/scripts/run_state.py excerpt <任务目录> --file calls/<ID>/stdout.raw --keyword "架构" --keyword "决策" --max-chars 6000
```

source 自动沿用调用 finished_at 为 fetched_at/observed_at，独立记录 recorded_at、revision 和缓存哈希。outline 只能证明目录内容；具体方案需章节正文。excerpt 默认最多 8 个命中、6000 字符，最大 12000；truncated=true 表示仍有未覆盖片段，不要 cat 整份大型响应。

## 事实、覆盖与文件

evidence.json 含 schema_version=2、sources、claims。关键事实示例：

```json
{"id":"c1","text":"评审决定采用 B","status":"decided","current":true,"support":[{"source_id":"s1","kind":"decision","locator":"评审结论段"}],"supersedes":[],"conflicts_with":[]}
```

- status 为 proposed/decided/implemented/operating/unknown；分别需要 proposal/decision/implementation/runtime 级依据。unknown 仍需 context 等证据定位尚未确认的问题。
- 来源 provenance 为 primary/secondary/direct。AI 摘要和转述不能冒充拍板记录或运行凭据。代码来源和版本字段见 [技术调查模式](code-investigation.md)。operating 需 direct runtime 来源及 environment、deployment_revision、trace_locator；元数据完整不自动证明线上事实。
- 不可读来源 access 为 forbidden/missing_scope/not_found/unsupported，记录失败 call_id、缓存、检查时间与范围，不支撑已知事实。readable 必须对应成功回执。
- 新决定明确替代旧决定时旧 claim current=false，新 claim supersedes 指向旧 ID。冲突用双向 conflicts_with；更新时间较新不等于替代。推断用 inference=true。
- rounds 记 branch/new_claim_ids/resolved_questions/new_conflicts；pending_leads 不能绕过预算。coverage 记域、分页与时间范围的跳过原因。
- 编辑事实/问题时先写同目录临时 JSON、解析通过再原子替换，不与记账操作并行写 run.json。只存相关原始响应，不混入无关个人信息或凭据。

实际生成后登记文件：

```bash
python3 <技能目录>/scripts/run_state.py artifact <任务目录> --id report --file background.md
python3 <技能目录>/scripts/run_state.py artifact <任务目录> --id architecture --file architecture.mmd
python3 <技能目录>/scripts/run_state.py mermaid <任务目录> --id architecture --mermaid-module <已安装的mermaid.esm.mjs>
python3 <技能目录>/scripts/check_artifacts.py check <任务目录>
```

Mermaid 命令只用现成 Node 解析器，不安装依赖、不启动浏览器。没有解析器时省略 --mermaid-module，记录 not_checked；失败与未验证要保留。语法通过不等于已渲染或关系真实。正文与 .mmd 内容一致可复用语法回执，文件变化后重登记并重验。

校验分层：record_valid（记录/引用/证据级别）、artifacts_valid（存在性/哈希/代码路径行号/本地 Markdown 链接）、budget_status（能否继续）、budget_compliant（有无超限）、question_coverage、diagrams。call_counts 区分 reserved/sealed/pending；预留占额度，不等于已实际执行。delivery_complete 还要求 Markdown 和用户指定载体均已交付、问题完整、无 pending 调用/不确定写入且图语法通过；退出码 0 或 delivery_complete 不等于事实准确率，也不掩盖预算超限。仍有缺口的报告也应交付，如实说明未完成项，不篡改状态求全绿。

旧 schema v1 可读取和审计，不自动升级；输出时间/环境/覆盖缺失警告。不要补写虚构的历史时间、参数或原始响应。后续刷新新建 v2 任务目录并链接旧报告。

## 写入断点与对账

每种操作最多两次明确提交。一次尝试格式：

```json
{"status": "inflight", "request_tag": "本次唯一标签", "content_sha256": "本地待提交正文或HTML的SHA256", "receipt": {}, "confirmed_not_applied": false}
```

状态：inflight（已准备发出/可能已发出）、unknown（结果不明）、submitted（发布已受理未结束）、succeeded、failed。成功 receipt：document 含 id/url，app 含 app_id 对应的 id，publish 含发布态 url；提交中的发布保存 release_id。request_tag 仅用于本地关联，不能假装是服务端幂等键。

1. 调用前落盘 inflight、输入哈希、请求标签与时间；返回后立刻保存服务端 ID、URL、revision/release_id。任何已有成功 ID 都先复用，不能重新 create。
2. 超时、断网、进程中断留下 inflight/unknown 时先对账。已知文档 token 就窄读核验；没有 token 时按本次唯一标题/创建时间/归属搜索候选，再比对内容。创建时可在标题附短任务标识，避免同名误匹配。
3. 已知 app_id 就查询该应用和发布记录；未知 app_id 时按本次名称、创建时间和创建者定位候选。已知 release_id 查询其状态。候选多于一个时不能擅自选，更不能用新建“解决”。
4. 查不到对象或索引暂未返回都不能证明写入没发生。只有明确失败且有可靠响应/对账证明未应用，才记录 failed + `confirmed_not_applied: true` 并考虑第二次提交。unknown/inflight/submitted/succeeded 后禁止直接追加新尝试。
5. 对账能确定成功时，更新原尝试为 succeeded 并补 receipt；发布已受理则更新原尝试为 submitted。不能确认时保留 unknown 和本地产物，报告需要确认的对象；不盲重试、不删除。

恢复前核对文件哈希与服务端 revision。文件改动属于新版本，不能把上次成功发布当作本次成功；用户授权更新既有产物后另记新版本操作，不清空旧操作来绕过不确定状态。阶段二失败只影响页面；已创建文档及本地背景包照常交付。

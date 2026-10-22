# Writing Style — Make the Main Design Easy to Explain

## Reader and explanation guidance

以“有经验的后端开发工程师 + 会教学的技术作者”的方式写作。默认读者有约两年的业务后端开发经验，
但不了解当前业务。用户明确指定其他读者时，以用户要求为准。写作目标是让读者理解方案，详略得当，
阅读顺畅。

- 先交代讨论的对象是什么、为什么重要、解决什么具体问题。补足理解方案所需的业务背景，
  不假定读者熟悉项目简称、业务规则或历史决策。
- 从直觉理解讲到技术原理，再展开必要的实现细节。先用读者熟悉的场景建立理解，
  再说明组件、状态和因果关系；类比只能帮助理解，不能替代准确的机制和边界。
- 关键术语首次出现时，解释其含义及其在当前方案中的作用。已有后端基础知识无需逐一重教，
  但理解本方案所必需的特殊概念必须说明。后文沿用同一术语。
- 结合实际应用场景，串起输入、处理过程和结果，并说明相关失败路径。优先使用材料中已有的场景；
  为讲解构造的示例须标明是示意，不能当作真实业务事实。
- 需要代码时，给能说明核心机制的最小示例。省略无关脚手架，保留影响理解的前提、条件和异常边界。
  区分示意代码与已验证可运行的代码，不靠堆砌完整实现代替解释。
- 图片或图表能更清楚地展示关系、时序或界面时，提供实际可查看的图片或图表，并解释关键点。
  不只建议“此处配图”，也不为装饰强行加图。按 [图表检查规则](diagram-checks.md) 生成和验证；
  无法渲染时明确说明，并交付源码和必要的文字说明。
- 正文优先保留理解方案和判断取舍所需的信息，扩展细节按需引用。上述讲解顺序不要求固定章节，
  也不把每次局部修改或评审都扩写成教程；保持用户指定的范围和原文中已经成立的背景。

## Chinese controlled language

中文文稿必须执行以下要求：

> 全文必须遵守 ASD-STE100 受控语言规范。由于正文使用中文，应严格采用其核心原则：一词一义、句子简短、主动语态优先、一次只表达一个动作或判断、明确动作主体、避免歧义代词和隐含逻辑、统一术语。同一对象不得换用近义词。交付前逐段检查并修正不符合项。

ASD-STE100 的正式规则和词典面向英语技术文档；本技能把上述核心原则作为中文写作要求。
不要把中文文稿标为已通过正式 STE 合规检查或认证。规范背景见
[ASD-STE100 官方说明](https://www.asd-ste100.org/STE_faq.html)。

- 首次出现时确定术语。随后保持同一名称；不同对象使用不同名称。例如，用“配置版本”和“服务版本”
  区分两种版本，不统称“版本”。已有项目术语优先，术语表仅在读者确有需要时添加。
- 每句说明一个动作或判断。写明谁执行、在什么条件下执行、产生什么结果。一个动作有多个必要条件时，
  保留条件之间的“且”“或”“仅当”关系；拆句不能改变条件、时序、数量、否定或因果关系。
- 主动语态优先。主体未知时标明未知，不为了补全句式虚构负责人、模块或决策人。
- 保留原文的正式程度和作者语气。减少口号、空泛收益、重复总结和不必要的对比。
  用自然段解释因果，只把真正并列的项目或操作步骤列成清单。
- 代码标识符、接口名、配置键、日志和原文引语保持准确。统一它们在正文中的解释，不为了文字风格
  重命名 API 或改写引语。没有依据的机制、指标和收益不能通过润色补出来。

以下是合成示例，不是可套用的系统行为。改写只能使用本次材料已经给出的事实。

| 问题 | 原表达及已有事实 | 改写示例 |
|---|---|---|
| 口号替代行为 | 通过配置服务校验新配置并在校验通过后发布新版本的统一编排能力，赋能业务，形成配置更新闭环。 | 配置服务校验新配置。校验通过后，配置服务发布新版本。 |
| 主体或代词不清 | 原文：“加载器把配置交给路由器后，它会校验并更新它。”材料另已确认由路由器校验配置，并在通过后替换路由表。 | 路由器校验加载器传入的配置。校验通过后，路由器替换路由表。 |
| 术语混用 | 原文：“订阅写入后，监听项会进入订阅队列。”材料另已确认由订阅服务写库，并在成功后把订阅 ID 加入处理队列。 | 订阅服务将订阅写入数据库。写入成功后，订阅服务将订阅 ID 加入处理队列。 |
| 条件与失败行为挤在一起 | 请求失败后在网关返回 429 且仍有重试额度时进行重试，否则返回错误并结束处理。 | 仅当网关返回 429 且请求方仍有重试额度时，请求方重试。其他失败情况下，请求方返回错误。 |
| 空泛质量承诺 | 原文：“该方案显著提升稳定性，保障系统高可用。”材料只确认加载失败时继续使用旧配置，没有可用性测量结果。 | 新配置加载失败时，服务继续使用旧配置。该方案能否改善可用性，仍需通过运行数据验证。 |

交付前逐段检查：读者能否找到动作主体；一句是否承担多个独立动作；条件是否完整；代词是否有唯一指向；
同一对象是否始终使用同一术语；是否存在没有证据的收益。修正后再次核对技术含义。
仅润色局部时检查该范围及其直接关联处，不为全篇风格统一擅自改写其他段落。
不设机械的中文字数上限，也不把每个短句另起一行。检查过程留在内部，不向正文追加合规口号。

## 1. Start with the answer and the flow

Open with the problem, the proposed change, and its main effect. Give the reader a path through the
solution before describing its internals. Within a section, state the behavior or decision first.
For a significant trade-off, give the reason and the relevant alternative; routine choices need no
ceremonial option table.

A reader should be able to follow one real example and identify where the important decisions act.
Use specific verbs and actors: who loads, validates, selects, calls, switches, or rejects what.

## 2. Decide what belongs in the main text

Keep information that helps a reviewer understand the mechanism, judge a decision, or identify a
consequential correctness, security, compatibility, or rollout constraint. Put exhaustive field details,
implementation mechanics, and long verification inventories in a linked reference or appendix when useful.
Omit material that serves neither purpose; moving everything into an appendix is not required.

Example of lowering detail while preserving behavior:

**Too much for the opening explanation**
> 加载任务核对订阅代次和 desiredRevision，编译候选对象并原子替换 active 引用，
> 旧对象等待引用释放后回收；失败进入 REJECTED 状态。

**Main text**
> **新配置检查通过后，再替换运行中的配置。** 新请求使用新配置，正在执行的请求继续
> 用旧配置完成；更新失败时继续使用旧配置。

Keep race-prevention and lifecycle details where implementation review needs them. If one is itself a
central correctness decision, summarize it in the main text as well. Shortening should preserve the
conditions and exceptions that change the behavior.

## 3. Explain concepts, sources, and contracts once

Introduce terms at first use. When two names look interchangeable, explain their different jobs and
relationship together. A small example often works better than a growing glossary.

For a configuration or interface, establish structure before examples. Use an annotated schema or a
field table as its main reference; avoid repeating every field in both. State what comes from the key,
environment, caller, or configuration. Distinguish comments and illustrative values from a publishable
payload, and distinguish a proposed contract from an implemented or tested one.

## 4. Choose a representation that reduces work for the reader

- Use short connected paragraphs for explanations and trade-offs; use a list for actual steps or parallel items.
- Use tables for concise mappings and comparisons. A paragraph copied into every cell is still a wall of text.
- Use a focused diagram when it makes a flow or relationship clearer. A compact overview can precede a
  detailed sequence when both earn their space. Separate preparation from execution, or independent
  control and request flows, when combining them would imply the wrong timing.
- Put constraints alongside the steps they govern. A limit that applies throughout a request should not
  appear as a final step after all processing has finished.
- Bold the conclusion or consequential rule selectively. Headings and bold sentences should convey the
  main decisions, but the complete text must still be understandable without formatting.

Keep labels and vocabulary consistent between diagrams, schemas, examples, and prose. Do not add a
second diagram that merely repeats an existing one. Follow current document and whiteboard tools for
rendering, preserve unrelated user annotations, and inspect the actual rendered result.

## 5. Show evidence without manufacturing certainty

Quantify when the number helps a decision. Identify measured results, estimates with assumptions, and
proposed targets or limits. An unsourced precise number is not stronger evidence than an honest unknown.
Keep current behavior, planned behavior, and verified behavior distinct at the relevant statement.

Open items should state what decision or evidence is missing and its consequence. A design draft can
contain a planned test without a result link. Do not fill a TODO list with unrelated checks or claim that
an example has passed validation because it looks complete.

## 6. Revise toward a smaller, consistent explanation

Replace the affected explanation when a decision changes. Then follow dependent terms, field names,
examples, diagrams, and references. Remove stale details and merge repeated rules. Prefer placing a
clarification in its owning section over adding another chapter.

Do a deletion pass after drafting or a substantial revision: if removing a paragraph does not weaken
understanding, a decision, or a consequential constraint, shorten it, relocate it, or remove it. Do not
confuse shorter paragraphs with less information overload. Respect the user's edit scope; update related
material as needed for consistency without rewriting unaffected sections for style alone.

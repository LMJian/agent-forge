# Review findings and scope

Use this in review mode. Read the requested design and relevant evidence, then return findings without
editing source documents unless the user also requested corrections. Evaluate the scope the user asked
about. A draft self-check does not replace a separate Harness audit invocation.

Start with the consequential findings, ordered by impact. Each finding should explain:

- **Location:** the design section and the affected interface/module. Give a verified file/symbol/configuration
  or document anchor when the evidence comes from another source.
- **Trigger:** the specific input, state or deployment order that exposes the problem.
- **Impact:** the observable wrong result, acceptance failure or engineering decision left unsupported.
- **Evidence:** what was inspected, what it shows and which part remains an inference or gap.
- **Correction:** the smallest useful design change or check. State an unresolved product decision when
  choosing a fix would change requirements; do not ask the user to approve routine wording corrections.

These are content requirements, not five mandatory headings for every finding. A short connected
paragraph can carry all five. Do not invent a failure scenario solely to fill the format.

| Severity | Use when | Do not use for |
|---|---|---|
| `blocker` | The proposed design cannot meet an acceptance criterion, or a concrete trigger causes an unacceptable failure. An unresolved essential contract can also block the dependent decision. | A preferred writing style, a hypothetical unrelated risk, or a test planned for a later stage. |
| `warning` | A material limitation or missing check affects a stated claim, but supported design work can continue within an explicit boundary. | A generic demand to add more monitoring, tests or infrastructure. |
| `suggestion` | A focused change improves clarity or maintainability without changing correctness or acceptance. | A confirmed data-loss or compatibility failure. |

Example with synthetic evidence:

> **blocker — 成功响应可能早于持久化。** 方案“响应时机”一节允许服务在写库前返回成功。
> 需求要求成功响应代表任务已持久化。如果服务在响应后、写库前退出，客户端会收到成功，但任务会丢失。
> 建议在持久化成功后返回成功；写库失败时返回明确错误。

Do not replace an issue with “improve error handling.” Name the failed step and caller-visible result.
Merge findings that share the same cause. Separate confirmed contradictions from unverified risks.
Keep evidence limits visible: a local code review does not establish deployment health or test success.

If there are no actionable findings, say so and name the reviewed scope and material checks not performed.
Do not manufacture suggestions to make the review look substantial. No findings does not mean release
approval, production validation or user sign-off.

For standalone work, concise Markdown is sufficient. For Harness, return the findings to the wrapper
using its existing `blocker` / `warning` / `suggestion` contract. Preserve `severity` and `message` when
converting findings; put anchors and details in the message or the caller-supported fields. Include an
explicit empty findings array for a clean review. Unresolved blockers cannot be reported as `pass`.
Do not change workflow state, invent report-envelope fields or mark the user's approval on their behalf.

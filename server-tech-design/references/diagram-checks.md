# Diagram checks and delivery limits

Use this when the requested output contains a diagram. Choose a diagram only when it clarifies a flow,
boundary or relationship. Verify its meaning against the text and evidence before checking its syntax.
Check important actors, arrow direction, synchronous/asynchronous completion, failure paths and labels.
Label proposed components and uncertain relationships; rendering cannot prove they exist.

Keep the following states separate for each diagram that matters to the deliverable:

| Check | Evidence for completion | When unavailable or failed |
|---|---|---|
| Source generated | The actual Mermaid/other source exists in the output file or document | Finish the source or state what is missing. An empty resource block is not a diagram. |
| Syntax checked | A compatible parser or renderer accepted that exact source; record the tool and result | Mark syntax as not checked if the tool is unavailable. Fix confirmed syntax errors and recheck the affected diagram. |
| Render inspected | The generated image/document was actually inspected for clipped labels, overlapping edges and readable layout | Mark visual inspection as not performed. Successful parsing or an image file on disk is insufficient. |

Use existing supported CLI/API tools first. Read the relevant destination's format guidance before export.
Do not auto-install a renderer, launch a browser, create a remote diagram or change sharing permissions
to satisfy this check. Those actions require authorization under the current task's rules. Previously
authorized tools may be used within their scope; do not ask again merely because this reference exists.

If no parser or renderer is available, deliver the requested local source and concise prose describing
the flow. State exactly which check remains undone. If the user explicitly requires a rendered artifact,
complete all independent work and report that remaining requirement; do not claim full completion.
Do not add a prose duplicate when the readable diagram already explains the same information.

After a diagram changes, repeat the checks affected by that change. A receipt for an old version does
not validate the new source. Ensure an embedded diagram and a separately delivered source agree.
For a remote destination, use the authorized narrow readback to check warnings and the actual resource.
If remote rendering fails, retain the local source and report the failure without re-creating the whole document.

The final report needs only the material result or gap, such as “架构图源码已生成；当前环境没有解析器，
尚未校验语法和渲染效果。” Do not append a large verification ledger to an otherwise small design.

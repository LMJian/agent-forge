# Personal execution rules

## Computer Use authorization — mandatory

- Before the first call to any Computer Use or GUI automation tool in each task, explain the specific need and wait for my explicit approval.
- This includes `mcp__cua_repl`, browser UI automation, accessibility-tree inspection, screenshots taken through UI automation, mouse/keyboard control, and native-app UI control.
- A general request to complete work, approval from another task, or the mere availability of a tool is not Computer Use approval.
- Approval applies only to the stated task and purpose. Ask again if the purpose or scope materially changes.
- Prefer a CLI, API, connector, MCP tool, or purpose-built skill whenever it can complete the task without Computer Use.

## Token-efficient execution

- Use the narrowest reliable route and retrieve only the information needed for the current decision.
- Test authentication and network access with one small probe before parallel or bulk requests. If blocked, request the required authorization instead of repeating failures.
- Bound and filter tool output. Do not dump full DOM or accessibility trees, long logs, stack traces, directory listings, or complete raw documents unless they are strictly required.
- Search before reading large files. Read only relevant sections of skills and references, and avoid rereading unchanged material.
- Keep large generated content in a local file and pass it by file path, body file, or structured API. Do not copy the same full body through multiple tool calls.
- For external-document work, prepare content locally, perform one create or update operation, and use one narrow verification when the available API or CLI supports it.
- After the same approach fails twice, stop repeating it, diagnose the cause, and switch to a materially different route.
- Prefer concise progress updates and final answers; include detailed logs only when they help resolve a failure.

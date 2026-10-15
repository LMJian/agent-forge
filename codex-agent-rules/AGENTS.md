# Personal execution rules

## Computer Use authorization — mandatory

- Before the first Computer Use or GUI automation call in each task, explain the specific purpose and scope, then wait for my explicit approval. Read-only GUI inspection also requires approval.
- This covers browser UI automation, accessibility-tree inspection, screenshots captured through UI automation, mouse/keyboard control, and native-app control, including GUI operations driven indirectly through a CLI or script.
- Reuse explicit approval within the same task, purpose, and scope without asking for every step. Ask again if the purpose or scope materially changes. A general task request, approval from another task, or tool availability is not Computer Use approval.
- Direct CLI/API/connector requests, web search, and reading local files or supplied images do not by themselves require Computer Use approval; their own access permissions and action boundaries still apply.
- Prefer a CLI, API, connector, MCP tool, or purpose-built skill when it can complete the task without GUI interaction.

## Token-efficient execution

- Start with the narrowest reliable query or read. Expand scope only when the available evidence is insufficient to complete the task correctly.
- Before parallel or bulk external requests, use one small relevant request to check authentication and connectivity. Reuse that result within the same task and access scope; recheck when the scope changes or evidence suggests access has changed. If authorization is missing, request it instead of repeating failures.
- Search before reading large files. Read only relevant sections of skills and references. Reuse unchanged instructions, retrieved evidence, and local artifacts; refresh them when they may be stale or the task requires current state.
- Filter and summarize results before returning tool output to the conversation. Bound both the number of items and each item's length; line limits alone do not control a large single-line JSON response. Retrieve full content only when necessary for the task.
- Keep large raw results and generated content in local files when needed, and pass them by file path, body file, or structured API. Avoid copying the same full body through multiple tool calls.
- For external-document work, prepare content locally, apply a cohesive create or update, and verify the changed parts with a narrow readback where supported. Avoid repeated full-document transfers.
- Distinguish empty results, timeouts, authentication failures, and permission denials. A failed or incomplete query is not evidence that data does not exist; qualify conclusions by the actual query scope and coverage.
- Follow applicable permissions and tool/skill retry requirements; these rules do not grant automatic retry permission. After the same approach fails twice, stop repeating it, diagnose the cause, and change the approach within the authorized scope or report the blocker. Do not blindly retry writes whose outcome is unknown.
- Separate confirmed facts, inferences, and unresolved questions. Give the evidence needed to support the conclusion without dumping unrelated logs or documents.
- Once the requested outcome is achieved and required checks pass, deliver the result instead of extending unrelated investigation. Efficiency must not replace necessary verification or leave authorized work incomplete.
- Keep progress updates and final answers concise, centered on findings, consequential uncertainty, and next actions. Include detailed logs only when needed to explain a failure.

# Review Checklist — Comprehension Before Inventory

Use this internally before handing off a draft or substantial revision. Apply relevant checks only.
A concern can be satisfied inside the main flow; it needs no standalone heading. Do not paste this
checklist or a sequence of “not applicable” explanations into the document unless requested or required.

## Can the reader explain the solution?

- [ ] The opening explains the current problem, intended change, outcome, and scope.
- [ ] A reader can restate the core solution and the important decisions without tracing implementation details.
- [ ] One concrete example goes from input to result; relevant lifecycle transitions and failure outcomes are clear.
- [ ] Input sources, state ownership, identity or version selection, and their effects are established where relevant.
- [ ] Similar concepts are distinguished before use; diagrams and prose agree on responsibility and timing.
- [ ] Each section answers a distinct question, and its position follows the design's reasoning or execution flow.

## Is the relevant design complete and evidenced?

- [ ] Applicable existing recon was discovered from supplied/project artifact locations, including hidden or ignored `.artifacts`; reused claims match this repository, task and relevant current code, and the baseline is cited without being overwritten.
- [ ] The proposed choice and meaningful trade-offs are explained; no alternative was invented just to fill a table.
- [ ] Changed contracts, state and configuration behavior, compatibility, and consequential failure paths are specified.
- [ ] Relevant authorization, isolation, sensitive-data, outbound-access, and resource boundaries remain visible.
- [ ] New traffic, dependencies, storage, or latency costs are assessed when material, with assumptions or evidence.
- [ ] Numbers distinguish measurements, estimates, and targets; organizational requirements have a source and scope.
- [ ] Existing behavior, proposed changes, implemented work, and verified results are not conflated.
- [ ] Consequential claims point to the relevant symbol/configuration read site or document section and version; local snapshots and runtime observations keep their evidence limits.
- [ ] Open items affect a real decision or readiness claim and identify the missing information or next step.

## Can the design be observed, verified, and released?

- [ ] Monitoring names the operations and measurements, reused or proposed sources, useful dimensions, and alert conditions.
- [ ] Success and availability have a clear meaning; transport and business results, retries, and timeouts are distinguished when needed.
- [ ] Relevant acceptance cases cover the core flow and major failure or compatibility boundaries; executed results are linked only if available.
- [ ] Where rollout is needed, enablement order, observation, abort conditions, and rollback behavior are explicit.
- [ ] Required project controls are addressed without assuming every change needs a new FG, region plan, or approval process.

## Is the draft focused and consistent?

- [ ] Essential behavior is in the main text; long implementation inventories do not obscure it.
- [ ] Every paragraph helps explain the solution, justify a decision, or assess a consequential constraint; remaining repetition is removed.
- [ ] Tables and diagrams simplify rather than duplicate text, and important labels remain readable in the actual output.
- [ ] Each definition or field reference has one primary home; annotated schemas and examples do not duplicate a second full reference.
- [ ] After changes, affected examples, diagrams, cross-references, headings, and obsolete explanations have been reconciled.
- [ ] The final affected content has been read back; user annotations and unrelated content are preserved.
- [ ] Chinese paragraphs follow the controlled-language rules: explicit actors, one action or judgment per sentence, complete conditions and consistent terms; simplification has not changed the contract.
- [ ] Diagram generation, syntax checking and visual inspection have separate, accurate states; unavailable checks are reported rather than treated as passed.
- [ ] Review findings identify location, trigger, impact, evidence and correction; stylistic suggestions are not promoted to blockers, and a clean review reports its actual scope and limits.

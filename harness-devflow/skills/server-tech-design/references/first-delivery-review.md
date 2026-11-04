# Review the draft before first delivery

Use this for a new design or substantial revision. This is an internal content review, not a user approval
step, fixed document outline, separate report, or mandatory JSON artifact. For a narrow edit, apply only
the affected questions. Keep one primary explanation for each concept.

## Read what a new reader receives

Read the draft without relying on the conversation or the recon author's unstated knowledge. For each
question below, find the passage that answers it. A remembered answer without a document passage is a
missing explanation. Revise it before publication, then follow the affected terms, examples and diagram
labels. Do not wait for the user to request these checks separately.

| Reader question | Evidence the draft needs |
| --- | --- |
| Why does this change exist? | The business trigger and desired user result, what already works, and the specific gap. An opening that only says “add module X” does not explain the background. |
| What work belongs to this change? | Affected responsibilities and boundaries: new code, changed contracts, reused behavior, configuration/version dependencies, and retained or removed behavior where relevant. A component list alone is insufficient. Explain why the proposed module owns the gap when that choice matters. |
| How does one scenario reach its result? | Inputs, responsible actors, intermediate state and observable result. Explain domain terms and distinguish easily confused objects before details depend on them. Follow the material failure branch as well as the successful path. |
| What is still unknown? | Real unresolved decisions, evidence gaps or tunable proposals, with the consequence, next action and point when an answer is needed. Keep accepted requirements settled. If no relevant gap exists, do not manufacture a pending section. |

Scale detail to the task. A business capability can be in scope while part of its contract remains
unresolved; identify both without relying on unstated domain knowledge. When a dependency
already has relevant work in progress, separate reuse and integration from implementing it again.

## Apply the writing rules to the whole requested scope

Use [writing-style.md](writing-style.md). Read prose, tables, examples and diagram labels together.
Check actual understanding barriers rather than counting characters or requiring a glossary:

- Resolve domain-only abbreviations, conversation question numbers, unclear aliases and vague actors.
  Introduce a term where it is needed; later references should keep the same name.
- Give each sentence one action or judgment. Preserve the original conjunctions, ordering, quantities,
  negation and transaction boundary when splitting a sentence. Do not fragment one judgment's necessary
  conditions or replace a coherent paragraph with one sentence per line.
- Distinguish accepted, persisted, notified, applied and completed states when the flow uses them.
  A bounded retry policy does not guarantee eventual delivery. Do not strengthen evidence or guarantees
  through more confident wording.
- Consolidate unresolved business contracts, technical integration checks and proposed operating values
  at an appropriate place. Consequential constraints still belong beside the flow they govern; reference
  the primary explanation rather than repeating a full field list or policy.

Do not put this checklist or a language-compliance slogan into the design. Do not claim formal STE
certification. Follow [delivery.md](delivery.md) after content review; publication/readback and semantic
review establish different things.

## Rechecks and stopping

For “check and fix” requests, review all requested dimensions in the current revision and repair each
observed issue in one cohesive pass. Do not limit a whole-document review to last time's sample sentences.
Then check affected connections and the delivered content. If a later recheck has unchanged content,
reuse the prior substantive review after verifying applicability. Report no new findings when justified;
do not create another version merely to show activity. A later business decision may still require an
update without making the current, explicitly bounded draft defective.

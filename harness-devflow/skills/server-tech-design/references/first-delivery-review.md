# Review the draft before first delivery

Use this for a new design or substantial revision. This is an internal content review, not a user approval
step, fixed document outline, separate report, or mandatory JSON artifact. For a narrow edit, apply only
the affected questions. Keep one primary explanation for each concept.

## Read the opening on its own

Read only the background, overview, and change scope. For a cross-component design with meaningful
dependencies and call order, inspect both diagrams or their documented source fallback. Find where
the reader can answer each applicable question. Put missing answers in the opening before reviewing
the detailed design.

| Reader question | Evidence to find in the opening |
| --- | --- |
| Why does this change exist? | The user scenario, existing capability, specific gap, and intended result. |
| How are the modules connected? | The entry point, responsibilities, state owner, and direction and purpose of the dependencies. |
| How does the main scenario reach its result? | The call order, origins of consequential inputs, important state changes, and what the caller or user observes at each completion point. |
| What will change and why? | Check each code change in its Spec row or paragraph. It names the component, the changed behavior, and the reason together. The Spec separates code work, contract updates, configuration, and reuse or integration. |
| How will the work be completed? | The Plan names the owner, prerequisite, and expected observable result for each relevant phase. |

Compare the diagrams, Spec, and Plan. Check that the same component owns each key action or state
change, the call order follows the dependencies, and the Plan covers the Spec's work. Repair any
mismatch where the reader first encounters it. Use the smallest representation that answers the
questions for the current scope.

In the detailed design, trace the same scenario through its consequential failure paths. Identify
unresolved decisions and evidence gaps with their consequence, next action, and required milestone.
Keep accepted decisions settled and distinguish candidate work from deployed capability.

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

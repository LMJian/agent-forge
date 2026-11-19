# Section Guide — Select Concerns, Then Organize the Design

Use this as an internal coverage guide when choosing or reviewing sections. A concern may be handled
inside a flow, contract, or rollout explanation; it does not automatically deserve a chapter.
Follow an explicitly required user or project template. Otherwise omit inapplicable concerns without
filling the document with “N/A” or explanations of deleted headings.

## Build the reading path

Start with the problem and the intended result. For a cross-component design, use one representative
scenario to draft the following views before expanding the implementation. Confirm each important
dependency, input source, and state owner against the available evidence.

- **Module dependency diagram.** Show the entry point, the components that own decisions or state,
  and the dependencies that affect the design. Give each component its name and role. Use directional
  arrows with short labels that say what crosses each boundary. Identify added, changed, and reused
  components with text labels or a legend. Group internal details under their owner. This is a module
  graph, not a sequence diagram; include clients or agents when they participate in the main scenario.
- **Core interaction sequence.** Start with a concrete trigger and follow it to an observable result.
  Show who calls whom, where consequential inputs come from, and where state is written or read.
  Mark what each important response means and where work continues asynchronously. Choose branches
  that explain a material route, state, or outcome. Summarize repeated calls in a loop or a short note.
  Put longer variants in the detailed design.
- **Change scope (Spec and Plan).** In the Spec, name the affected service or module and its repository
  where relevant. Put the concrete change and the gap it addresses together. Separate code changes,
  contract or dependency updates, configuration, and reuse or integration work. In the Plan, give each
  phase an owner, prerequisite, and result that allows the next phase to start. For example, verify
  that an existing client reads data produced by the new writer before enabling writes. Link open
  decisions from the Spec or Plan when they affect scope or work order.

Use the same names and responsibilities across the views. Keep each diagram focused on its own
question. Add a short walkthrough in sequence order when a reader needs it to connect the steps.
For a small change, a short paragraph or table can cover the relevant answers. Place detailed
contracts and failure rules beside the behavior they govern, then link to them where needed.

## Engineering coverage — apply where relevant

| Concern | Questions to resolve | When to expand |
|---|---|---|
| Background and scope | What is the user's goal, what already works, which gap remains, and what result changes? Who owns new work, reuse and integration? | Explain unfamiliar context and consequential module placement; omit history that does not explain a decision. |
| Core decisions | What is chosen, why, and what important trade-off is accepted? | Compare real alternatives when their cost, correctness, or compatibility differs materially. |
| Interfaces and contracts | Who calls what, with which inputs and outputs? What validates, authenticates, authorizes, or deduplicates the request? | New or changed contracts, consumer changes, sensitive data, or non-obvious limits. |
| Data, configuration, and cache | Where does each value come from, who owns it, and how is it discovered, identified, stored, updated, or removed? | New state, persistence or consistency behavior, dynamic discovery, or migration. |
| Failures and resource bounds | What fails, what does the caller observe, and what continues serving? What bounds time, size, retries, and concurrency? | Consequential failure paths and dependency behavior; refer back to shared rules. |
| Security and privacy | What changes in trust, authorization, tenant isolation, data exposure, or outbound access? | A changed security boundary or an applicable organizational requirement. |
| Compatibility | Which old callers, data, configurations, or versions must keep working? How do they coexist or migrate? | Behavior or contract changes; explain transitions instead of saying “compatible.” |
| Capacity and performance | What new traffic, storage, I/O, fan-out, or resource pressure does the change create? | Material cost or latency changes; show assumptions and the bottleneck. |
| Multiple regions and deployment variants | Are routing, locality, cross-region failures, private deployments, or older deployments relevant? | The actual dependency path crosses these boundaries. |
| Monitoring | What proves the system is available, correct enough for its intended use, and operating within budget? | Use the metric guidance below; expand only the important diagnostic dimensions. |
| Verification and rollout | How will the critical behavior be checked, enabled, monitored, stopped, and restored? | New behavior or deployment risk; state dependency order and rollback prerequisites. |

## Sources of truth and contracts

Explain related concepts together when they can be confused: configuration identity versus publication
revision, desired state versus usable state, or loading a capability versus selecting it for traffic.
Show what each controls and how they relate, using a small example if helpful.

For a field, identify whether it is supplied by the caller, inherited from environment or connection
context, derived from a key, or explicitly configured. Repeated representations of the same fact need
an owner and a consistency rule; add a redundant field only when its validation or operational purpose
justifies the extra state.

For implementation-aligned updates, verify the changed branch against the requested base (for example,
master), then explain the resulting design directly. Readers should not need the previous document or
chat history. Keep current, proposed, deployed and verified behavior distinct; do not infer deployment
from a code diff. Reconcile the overview, diagrams, contracts, Spec and Plan after responsibilities change.

Choose the contract representation by the reader's question:

- **Nested persisted values and messages:** prefer the actual project's struct/type or schema, with
  field explanations in comments. Preserve nesting, map/list element types, optionality, units and
  serialization names. Use Go structs for a Go project, not as a universal language requirement.
  Label excerpts and omit only irrelevant fields; do not invent fields or defaults to fill a template.
  Flat field tables alone do not show the shape of a nested value. Use tables for mappings/comparisons.
- **Storage:** show the key pattern separately from the value type. Explain ownership, encoding,
  retention/expiry and deletion/update behavior. Include logical growth, root/index size and update
  costs when material; splitting a value into pages does not establish a bounded aggregate or hot key.
- **MQ:** show the message type and the actual topic, producer, consumer and consumer-group mapping.
  Distinguish configured group names, resolved physical groups and worker instances when they differ;
  derive counts from the actual consumer configuration rather than counting screenshot rows or replicas.
- **Push/RPC/HTTP:** distinguish the declared model, envelope and actual wire encoding at each layer.
  A PB declaration alone does not prove PB binary, protobuf JSON or application JSON transport. Follow
  the serializer and receiver; show who calls/parses/applies the data, at what time, and what the actual
  failure/gap response is. Do not introduce a new fallback or broaden a success guarantee while explaining.
- **Configuration and access:** give the applicable namespace/path/key, annotated value shape, field
  sources/defaults and consumer. For changed endpoints/dependencies, record the domain/path/method,
  caller/callee, login/authentication/authorization and required service permission/security review.
  Distinguish existing, new, submitted and effective items from evidence. Do not invent ACLs or approvals.

Explain each field in one primary place. A small payload example can clarify encoding or behavior;
comments and illustrative values are not a copy-paste production JSON payload. These concerns belong
in their owning sections and do not require separate chapters, repeated tables or a second checklist.

## Monitoring: define metrics and their meaning

Start with the operations whose failure matters. Use counters for requests, completions, and failures,
histograms for latency, and gauges for meaningful current state. Rates and percentiles should be derived
from those measurements. Distinguish attempted, completed, and retried work when they have different counts.

| Monitoring object | Measurements or reused metrics | Interpretation and dimensions | Alert condition |
|---|---|---|---|
| An operation or interface | Volume, failures, duration | Define success, failure classes, and the bounded dimensions needed to locate the problem. | Select the actionable availability, error, or latency condition. |
| A relevant background process or state | Attempts, failures, duration, or readiness | Explain whether failure affects current service or only a pending update. | Persistent failure or loss of required usable state. |

Adapt these rows; not every design has a background loader. Platform metrics can be reused when they
cover the required signal. Avoid duplicate instrumentation, but still identify the interface availability,
latency, and throughput that the design relies on. Give metric names or their definition; identify
proposed additions and existing sources without claiming planned instrumentation is already deployed.

For layered protocols, distinguish transport success from operation success. For example, a protocol
error can occur inside HTTP 200. Define the denominator, timeout and cancellation treatment, and caller
versus service failures when they affect the success or availability measure. Do not sum the same request
across layers. State how probes or ingress metrics cover no-traffic periods or failures invisible to the
application when availability requires that coverage.

Use bounded labels; keep request IDs, raw errors, credentials, and user content out of metric labels.
Use logs and traces for correlation and detailed diagnostic metadata without recording sensitive payloads.
Keep test plans and release TODOs outside the monitoring explanation. Set thresholds from a stated target
or observed baseline rather than inventing a production limit.

## Verification, rollout, and organizational requirements

At design time, identify acceptance scenarios for the core flow and the significant failure, security,
and compatibility boundaries. Link executed results only when available; distinguish a planned test,
a local or mocked check, and a production validation.

For changes that need staged release, explain enablement, observation, abort conditions, and rollback.
Use the applicable control mechanism, such as an existing feature gate, route, or configuration revision;
name an FG specifically when the verified project policy or design requires it. Show what the control
actually stops or restores, including existing requests or connections and irreversible data changes.

Apply organizational requirements using their current source and scope. Region-hop budgets, capacity
sign-off thresholds, link-level rules, mandatory FG controls, security conclusions, and review procedures
are not universal constants. Confirm relevant policy and cite it; mark an unresolved requirement only
when it materially affects this design. Keep measured numbers, estimates, and proposed limits distinct.

Add owner, reviewers, milestones, test links, and review records when known or required for this delivery.
Do not imply review approval, test completion, capacity sign-off, or rollout readiness through a filled template.

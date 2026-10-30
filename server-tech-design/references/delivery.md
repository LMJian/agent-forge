# Delivery — Lark first, Markdown fallback

Use this for creating a design document, converting an accepted draft, or delivering a requested
document report. A review-only request still returns findings; an in-place edit preserves its target.

## Choose the destination

| Situation | Deliverable |
|---|---|
| New document, no explicit format, authorized Lark/Feishu tools available | Lark document and its URL |
| Explicit Markdown/path, local-only instruction, or required Harness `local_markdown` contract | Local Markdown at the required location |
| Existing document to edit | Update that document; do not create a duplicate to apply the default |
| Review without a requested document report | Findings in the conversation or the caller's review contract |
| Lark cannot be used for this task | A saved local `.md` with the actual delivery limitation |

Do not ask the user to choose a format merely because none was specified. For a new design-document
request, use the configured Lark default within the task's authorized content, identity and destination.
This does not authorize broader sharing, uploading every referenced file, changing credentials or
installing integrations. Reuse prior authorization when it covers the same action and scope.

Distinguish a missing integration, missing authentication, denied permissions and a platform failure.
An authorization error is not proof that the platform does not support documents. For the default
destination, these limitations may trigger the Markdown fallback without delaying the useful draft.
If the user explicitly required Lark, deliver the fallback but state that the Lark requirement remains
unmet and identify the minimal missing access or recovery step. Do not present the fallback as a Lark success.

## Prepare and publish

Use an available document connector, API or CLI. Load its relevant document/media skills and current,
version-matched command guidance. Do not copy stale flags from an old example or use GUI automation
when the supported API can perform the operation.

For a long or repository-backed document, keep a local source and resolve its figures and references
before submission. A caller-required local artifact remains part of the handoff even when another
authorized destination is also used. Use the project's existing document/artifact conventions.

Transfer the requested design and its intended figures/examples. A link to a recon report, raw log,
archive or review receipt does not by itself authorize uploading that source. Check the actual scope
and intended audience; ask only when necessary authorization is missing. Preserve the useful document
while an additional resource is blocked, and disclose the unavailable reference instead of silently
dropping it or substituting an unrelated source.

Adapt local code references to stable repository/version links when available. Turn authorized example
file references into accessible attachments or document sections. Preserve the original labels and
technical meaning. Avoid broken local filesystem links in a remote document; identify any reference
that cannot be made accessible. Do not broaden permissions to make a link work.

Keep the intended title, heading hierarchy, tables, code blocks and figure positions. Avoid duplicating
the document title. Use the provider's supported long-document and media insertion workflow; keep
receipts and document IDs so a partial operation can resume without creating another document.

## Verify the delivered content

Read back the resulting document. For a new document or a full conversion, compare the whole content
with the accepted source. For a narrow edit, compare the affected content and preserve unrelated blocks.
Use the actual document revision and resource tokens, not only the local submission or a create response.

Compare paragraphs, heading order, table cell values, list items, code and reference destinations.
Counts help locate omissions but do not prove equality. For transferred files and images, read back
the relevant resource when supported and compare content or hashes. Check that figures occupy the
intended location; a media token alone does not establish a readable or correct figure.

Normalize serialization differences only: XML entities, code-block line-break tags and adjacent style
fragments may represent identical content. Several bold XML nodes can represent one continuous bold
span around inline code. Preserve field names, numbers, units, conditions and code whitespace that
affects meaning. Do not weaken comparison just to obtain a pass. Check rendered figures separately
using [diagram-checks.md](diagram-checks.md); byte equality is not a new visual inspection.

If a mismatch is found, repair the smallest affected block and read it back. Use a revision
precondition when supported; otherwise refresh the affected blocks before writing. If the content has
changed since the compared revision, reconcile those edits before repair instead of restoring a stale
source. Preserve comments, annotations and unrelated media. Do not overwrite a nonempty document solely
to fix an import defect.
When asked to verify a document again, refresh its current revision/content and relevant resources;
an old readback or cached attachment does not establish the current remote state.

## Handle incomplete delivery

- If no usable Lark delivery path exists, save the full design as `.md` with available figures/examples.
  Return clickable local paths and the specific limitation. Do not install tools or change security settings.
- If creation timed out with an unknown outcome, reconcile the operation/document ID before any new
  creation. Preserve the draft; do not create duplicate documents or label the outcome as unsupported.
- If creation succeeded but readback failed, retain the URL and source. State that consistency remains
  unverified. Repair or recover that document when possible; do not report verification as passed.

Follow the provider's retry and approval rules. A fallback preserves work; it does not erase an
unknown remote outcome or satisfy an explicitly required verification step.

Report the document URL or fallback path, the verification actually performed, and material gaps.
Keep detailed receipts and comparisons in local artifacts unless the user requests them.

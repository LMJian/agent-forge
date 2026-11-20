# Harness Devflow for DeepSeek Harness

This directory is the DeepSeek Harness bundle for [Harness Devflow](../README.md). It is not a
second copy of the workflow: the Host module registers the skills that live in `../skills`, and
the runtime stays in `../scripts` and `../harness`, so a repository sync updates both hosts at once.

The bundle registers sixteen workflow skills plus one entry skill:

- `harness-devflow` — entry point; routes to `flow` and the host mapping.
- `flow`, `intake`, `plan`, `implement`, `design`, `design-audit`, `test-design`, `interfaces`,
  `integration-test`, `review`, `delivery`, `monitor`, `release`, `knowledge`,
  `brownfield-recon`, `server-tech-design` — the workflow stages, read on demand.

Host-specific steps are mapped in [the DeepSeek Harness host mapping](../references/dsh-host.md).
The runtime needs Python 3.10+ and Git in the target checkout; the plugin itself makes no network
calls and starts no subprocess until a workflow command runs.

## Install

From DeepSeek Harness, install this directory as a local bundle (Plugins → Add plugin, or the
plugin manager with this folder as the target). A local directory install links this checkout, so
later edits under `../skills` or `../references` apply after the plugin reloads. Restart or start a
new session when the skill catalog must list the updated bodies.

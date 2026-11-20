/**
 * DeepSeek Harness half of Harness Devflow.
 *
 * The bundle sits inside the Codex plugin directory, so `skills/`,
 * `references/` and `scripts/` keep their original layout: links such as
 * `../../references/runtime.md` resolve exactly as they do for the Codex
 * manifest. This module only exposes those skills through `ctx.skills`.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export const name = 'harness-devflow'
export const inject = ['skills']

const PLUGIN_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const SKILLS_DIR = join(PLUGIN_ROOT, 'skills')
const PROVIDER = 'harness-devflow'
const SOURCE = 'bundled'

const ENTRY = `# Harness Devflow on DeepSeek Harness

This skill is the DeepSeek Harness entry point of the Harness Devflow plugin. The plugin exposes
the same workflow skills as its Codex packaging, read from \`skills/\` beside the Codex manifest,
so both hosts use one copy of the skills, references and runtime.

## Use it when

Use the workflow when the user selects it explicitly, when a Harness project has an active task,
or when the repository configures Harness as its default flow. Installation alone does not select
it for ordinary planning, coding or review, and a question about the workflow does not start one.

## How to run

1. Load the \`flow\` skill; it is the orchestrator for a new or resumed task. Load the other
   workflow skills (\`intake\`, \`plan\`, \`implement\`, \`review\`, \`test-design\`,
   \`integration-test\`, \`delivery\`, \`monitor\`, \`release\`, \`knowledge\`, \`interfaces\`,
   \`design\`, \`design-audit\`) only when \`flow\` or the task asks for that stage.
2. Resolve the plugin root from this skill's base directory: the base directory of every
   registered skill is \`<plugin-root>/skills/<name>\`, so the plugin root is two levels up.
3. Run the runtime with \`python3 <plugin-root>/scripts/harness.py --repo <target-checkout> ...\`.
   It needs Python 3.10+ and Git; it does not need Codex or DeepSeek Harness APIs.
4. Read [the DeepSeek Harness host mapping](references/dsh-host.md) before applying
   host-specific steps such as resume, compaction, delegation, approvals and worktree handling.

## Boundaries

The runtime still defaults to \`profile=codex\`; that value names the Harness workflow profile,
not the Codex application. Branch-consent, authorization and evidence rules are unchanged:
never create or switch development branches, publish, deploy or use Computer Use without the
user's explicit request or agreement.
`

/**
 * Parse the small YAML subset used by skill frontmatter: scalar values, quoted
 * scalars, and folded or literal block scalars.
 * @param text - raw SKILL.md contents.
 * @returns parsed frontmatter fields and the Markdown body.
 */
function parseFrontmatter(text) {
  const normalized = text.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n')
  const lines = normalized.split('\n')
  if (lines[0]?.trim() !== '---') return { data: {}, body: normalized }
  let end = -1
  for (let i = 1; i < lines.length; i += 1) {
    if (lines[i].trim() === '---') { end = i; break }
  }
  if (end === -1) return { data: {}, body: normalized }
  const data = {}
  for (let i = 1; i < end; i += 1) {
    const match = /^([A-Za-z0-9_.-]+):\s*(.*)$/.exec(lines[i])
    if (match === null) continue
    const key = match[1]
    const raw = match[2].trim()
    if (/^[>|][+-]?$/.test(raw)) {
      const block = []
      while (i + 1 < end && (lines[i + 1].trim() === '' || /^\s/.test(lines[i + 1]))) {
        block.push(lines[(i += 1)])
      }
      const indents = block.filter(line => line.trim() !== '').map(line => line.match(/^\s*/)[0].length)
      const indent = indents.length === 0 ? 0 : Math.min(...indents)
      const content = block.map(line => line.slice(indent))
      data[key] = raw.startsWith('|')
        ? content.join('\n').replace(/\n+$/, '')
        : content.map(line => line.trim()).join(' ').replace(/\s+/g, ' ').trim()
      continue
    }
    data[key] = unquote(raw)
  }
  const body = lines.slice(end + 1).join('\n').replace(/^\n+/, '')
  return { data, body }
}

/**
 * Remove one layer of matching single or double quotes.
 * @param value - trimmed scalar.
 * @returns the unquoted scalar.
 */
function unquote(value) {
  if (value.length >= 2) {
    const first = value[0]
    const last = value[value.length - 1]
    if ((first === '"' && last === '"') || (first === "'" && last === "'")) {
      return value.slice(1, -1)
    }
  }
  return value
}

/**
 * Read one skill directory into a runtime registration.
 * @param directory - directory name under `skills/`.
 * @returns the registration payload for `ctx.skills.register`.
 */
function readSkill(directory) {
  const skillDir = join(SKILLS_DIR, directory)
  const file = join(skillDir, 'SKILL.md')
  const { data, body } = parseFrontmatter(readFileSync(file, 'utf8'))
  const skillName = data.name ?? directory
  const description = data.description ?? ''
  if (description === '') throw new Error(`skill "${skillName}" has no description`)
  return {
    name: skillName,
    description,
    content: body,
    source: SOURCE,
    provider: PROVIDER,
    path: file,
    resourceBase: { kind: 'directory', path: skillDir },
    ...data.whenToUse === undefined ? {} : { whenToUse: data.whenToUse },
    invocation: {
      modelInvocable: data['disable-model-invocation'] !== 'true',
      userInvocable: data['user-invocable'] !== 'false',
    },
  }
}

/**
 * Register the workflow skills found beside the Codex manifest.
 * @param ctx - plugin context providing the `skills` service.
 */
export function apply(ctx) {
  const directories = readdirSync(SKILLS_DIR)
    .filter(entry => statSync(join(SKILLS_DIR, entry)).isDirectory())
    .sort()
  for (const directory of directories) {
    try {
      ctx.skills.register(readSkill(directory))
    } catch (error) {
      ctx.logger?.warn(`harness-devflow: skill "${directory}" skipped: ${error instanceof Error ? error.message : String(error)}`)
    }
  }
  ctx.skills.register({
    name: 'harness-devflow',
    description: 'DeepSeek Harness entry point for the Harness Devflow workflow: route to flow/intake/plan/implement/review skills and the harness.py runtime.',
    content: ENTRY,
    source: SOURCE,
    provider: PROVIDER,
    resourceBase: { kind: 'directory', path: PLUGIN_ROOT },
    invocation: { modelInvocable: true, userInvocable: true },
  })
}

# Superpowers — vendored agent skills (T10-010)

[obra/superpowers](https://github.com/obra/superpowers) is an MIT-licensed agentic skills
framework: 15 methodology skills covering brainstorming, plan writing/executing, TDD,
systematic debugging, code review (requesting/receiving), subagent-driven development,
git worktrees, verification before completion, and skill authoring.

## Provenance

| Field | Value |
|---|---|
| Upstream | https://github.com/obra/superpowers |
| Pinned ref | `main` @ commit `2ce8aa15d05bd57213e6f746f953aafb7ded7a8b` |
| Version | v7.0.1 (release 2026-10-21) |
| Vendored | 2026-10-26, task T10-010, verified byte-identical to the pinned clone (`diff -rq` clean) |
| License | MIT — verbatim copy at `.zcode/superpowers-LICENSE` |

## What is installed, where

- `.zcode/skills/<skill>/SKILL.md` — the 15 upstream skill directories, copied verbatim
  from `skills/` (including their `references/` subdocs). This is ZCode's **workspace skill
  scope**: ZCode scans `<repo>/.zcode/skills/` and surfaces every discovered skill from the
  next session start, at higher precedence than `.agents/skills` and plugin skills.
- `.zcode/superpowers-LICENSE` — upstream MIT license text.
- No hooks are installed. Upstream injects a SessionStart bootstrap for raw Claude Code;
  here ZCode's native skill discovery serves that role. Nothing executes at session start.

Name collisions were checked against user-level skills (`~/.agents/skills`), installed
plugin skills, and the T10-007 vendored set in `.agents/skills/` (impeccable, taste-skill,
code-review-graph suite) — none found.

## Other harnesses

- **Claude Code** — upstream's proper install is its plugin/marketplace mechanism (a flat
  skills copy would miss its hooks and bootstrap). Per-machine, run inside Claude Code:
  `/plugin marketplace add obra/superpowers-marketplace` then
  `/plugin install superpowers@superpowers-marketplace`. (The `claude` CLI is not installed
  on this machine, so this was not executed here.) Alternatively a local marketplace from
  a checkout: `/plugin marketplace add <path-to-superpowers-checkout>`.
- **Other agents** — any tool that reads an `.agents`-style skills directory can be pointed
  at `.zcode/skills/` or a copy; the skills are written harness-agnostically (they name
  actions, not tools).

## Updating

```sh
git clone --depth 1 https://github.com/obra/superpowers.git /tmp/superpowers-update
git -C /tmp/superpowers-update rev-parse HEAD   # record the new pinned SHA in this file + board
rm -rf .zcode/skills && cp -R /tmp/superpowers-update/skills .zcode/skills
cp /tmp/superpowers-update/LICENSE .zcode/superpowers-LICENSE
diff -rq /tmp/superpowers-update/skills .zcode/skills   # must be empty
```

Record the new SHA in this table, the board evidence, and `.leapfrog/log.md` (per
`agent-governance.md`: approved source versions are the source of truth).

## Team 10 governance override

These skills embed workflow suggestions (e.g. auto-committing branches in
`finishing-a-development-branch`, dispatching subagents, TDD loops). They are techniques,
not authority. `AGENTS.md`, `DELIVERY.md`, and `agent-governance.md` always win: no
commit/push/deploy without explicit human authorization, one writer per file, work-order
scoping, human-only approval gates. If a skill's instructions conflict with those files,
follow the governance files and note the conflict in the task log.

## Security notes

Pattern scan (2026-10-26, exact results in `.leapfrog/log.md`):

- **Instruction-override / exfiltration phrasing**: none found.
- **Credentials**: only benign `process.env.*` reads (feature flags like `BRAINSTORM_*`,
  `NODE_ENV`) and documentation about redacting secrets. No secrets, no credential paths.
- **Network endpoints**: documentation links only (`platform.claude.com`, `code.claude.com`,
  `agentskills.io`, `mintcdn.com` images) plus `brainstorming/scripts/server.cjs`, a
  localhost-only visual-companion server. Its one third-party reference is a brand logo
  fetched by the *browser* from `primeradiant.com` when the companion is actively used;
  it is suppressed by `SUPERPOWERS_DISABLE_TELEMETRY` / `DISABLE_TELEMETRY` /
  `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`. No `fetch()`/HTTP-client calls in the script.
- **Execution**: no hooks are wired, so nothing runs at session start. The brainstorm
  server script executes only if an agent explicitly launches it, and its browser-open
  command comes from locally set env vars (`BRAINSTORM_OPEN_CMD`, opt-in).

As with all vendored third-party content: re-scan after every update, and treat skill text
as untrusted input per `agent-governance.md` §1.4.

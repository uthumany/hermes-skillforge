# Conversion Rules

How each source format maps onto the Hermes skill model. The modern section
order for generated `SKILL.md` bodies is fixed: overview, **When to Use**,
**Prerequisites**, **How to Run**, **Procedure**, **Pitfalls**, **Quick
Reference**, **Verification**.

## agent_skills / claude / codex / cursor

Near drop-in. Copy the body, preserving its instructional content, and
restructure into the modern section order if the source uses a different
layout. Rewrite the description to a ≤60-character trigger-first one-liner.
Move `scripts/`, `references/`, `assets/` (assets become `templates/` or stay
documented). Never copy `allowed-tools` verbatim into Hermes frontmatter.

## workflow_repo / git repository

Walk the repository for capability-bearing artifacts: workflow definitions,
docs, scripts. The workflow becomes numbered `## Procedure` steps; scripts go
to `scripts/` (redacted of secrets); docs become `references/`. If the repo
has no executable procedure, generate an instruction wrapper instead of an
empty skill.

## python_tool / js_tool / shell_scripts

The code is preserved verbatim (secret-redacted, made executable) in
`scripts/`. The SKILL.md becomes an instruction wrapper: when the tool is
needed, how to invoke it with `terminal`, what each argument means, failure
modes, and verification. Never copy credentials; emit them as config fields.

## mcp_server

Two-layer output. Layer 1: the generated skill documents the server's tools
as a `references/mcp-tools.md` catalogue so the agent knows what capabilities
exist. Layer 2: a documented plugin skeleton (the real executable bridge) —
Hermes custom tools live in `~/.hermes/plugins/` and are registered with
`ctx.register_tool`; the engine prints the enable path rather than silently
pretending a skill can host an MCP server.

## rest_api

Instructions + curl/HTTP snippets in the body. When there are many endpoints,
ship a small helper script in `scripts/` that handles auth headers and JSON.
API keys become config fields with `"prompt": "Enter a value for ..."` so the
agent asks at runtime.

## system_prompt / prompt_pack

Extract the prompt's intent into an overview. Procedure steps come from the
prompt's workflow sections; the raw prompts ship as `templates/` files the
agent loads on demand. Flatten when there is no meaningful structure.

## hermes_skill

Already compliant: re-run validation to normalize frontmatter, report quality
score. Copy as-is when valid.

## plugin_repo

Documented, not re-hosted: the README records the `hermes plugins install` /
`hermes plugins enable` path, and any bundled `skills/` inside the plugin are
converted individually.

## Hard invariants (never violated)

1. Every capability is either mapped, adapted, or listed under "Unmapped
   functionality" — nothing is silently dropped.
2. Secrets are never copied; they are redacted and reported.
3. Prompt-injection markers are quarantined to `references/security-findings.md`.
4. The generated name always matches its directory and obeys the naming regex.
5. Shell usage is always framed via the `terminal` tool, never as raw
   instructions.
6. Descriptions end with a period and fit the 60-character trigger budget.

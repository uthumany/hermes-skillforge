# MCP Conversion Guide

MCP (Model Context Protocol) servers cannot be *hosted* inside a skill. A
skill is instructions plus scripts; an MCP server is a long-lived process
exposing tools. SkillForge therefore produces a two-layer conversion.

## Layer 1 — the skill (knowledge)

The generated SKILL.md teaches the agent: what the server's tools are, when
they are relevant, and what data they return. The full tool catalogue ships as
`references/mcp-tools.md`. This is enough for many workflows: the agent can
follow the documented procedures without a live server (e.g., when the same
data is reachable via a REST endpoint).

## Layer 2 — the plugin (execution)

For live tool invocation, the user enables a Hermes plugin. The engine prints
the exact enable path. The minimal pattern, mirroring the Hermes plugin API:

```python
# ~/.hermes/plugins/my_mcp_bridge/__init__.py
from hermes_sdk import PluginV1  # conceptual; see hermes-agent plugin docs

def register(ctx):
    @ctx.register_tool("mcp_tool_name")
    def tool_fn(args):
        # call the MCP server (stdio or SSE transport) and return the result
        return call_mcp("tool_name", args)
```

Then: `hermes plugins install ~/.hermes/plugins/my_mcp_bridge` and
`hermes plugins enable my_mcp_bridge`. A `/reset` or new session picks it up.

## Transport notes

- **stdio servers**: the plugin spawns the server process; keep invocation
  args in a config field, never hardcoded secrets
- **SSE/HTTP servers**: call the endpoint directly from the tool function;
  document required network access in the README so validation passes
- **Tool lists**: extract every `@mcp.tool` / registered tool name from the
  source and list it in `references/mcp-tools.md` with a one-line purpose

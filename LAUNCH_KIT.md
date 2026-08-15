# Launch Kit — Show HN Announcement + X/Twitter Thread

Ready-to-post copy for promoting **Hermes SkillForge**. Everything is copy-paste ready; only the posting mechanics are noted below each block.

---

## 1. Hacker News "Show HN"

### Title (paste into the title field — HN requires the "Show HN:" prefix for launches)

```
Show HN: Hermes SkillForge – convert any agent skill, repo, or MCP server into an install-ready skill (Python 3.10+, stdlib-only)
```

**Alternative titles (A/B):**

```
Show HN: SkillForge – I built a converter that turns Claude/Codex/Cursor skills and MCP servers into Hermes Agent skills
```

```
Show HN: A zero-dependency tool that validates and repackages 20+ agent-skill formats into one standard
```

> HN rules: post the link in the title of the Show HN submission (use "Show HN: Title" and set the URL to https://github.com/uthumany/hermes-skillforge), or post without a link and put the repo URL in the first comment. The second approach often performs better for repos — recommended here.

### Body / First comment (paste as the first comment)

```
Hi HN! I built Hermes SkillForge, a universal converter that takes 20+ source formats — Agent Skills (agentskills.io), Claude/Codex/Cursor skills, GitHub repos with agent workflows, MCP server manifests, plugins, prompt packs, rules files — and turns them into valid, install-ready skills for the Hermes Agent, following official SKILL.md authoring standards.

Why: the agent ecosystem is fragmenting. Every agent framework (Claude, Codex, Cursor, OpenClaw, AgentSkills, MCP) invented its own skill/config format, and the same automation has to be hand-rewritten for each. I wanted one portable, validated standard with a real test suite attached.

How it works (10 CLI commands):

  skillforge analyze <source>      # detect format + confidence + evidence
  skillforge convert <source>      # generate SKILL.md, scripts, references, tests
  skillforge validate              # Hermes validator: frontmatter, 60-char description budget, secret scan, dangerous-command scan, prompt-injection scan
  skillforge test                  # run the per-skill pytest suite the converter generated
  skillforge repair                # auto-fixes validation failures until clean
  skillforge install | rollback    # conflict-safe install into ~/.hermes/skills/
  skillforge batch <dir>           # convert every source under a directory

Some details I found interesting while building it:

- Zero dependencies: the whole engine is ~2,150 lines of Python-3.10 stdlib. No pip install needed.
- Safety by default: it redacts secrets (API keys, AWS keys, private keys) from generated files and refuses to execute host-dependent placeholder scripts — it statically validates them instead.
- Every converted skill ships its own generated pytest suite. The engine's own suite passes 10/10; the three demo conversions (agentskills.io skill, workflow repo, MCP server) validate at 18/18, 19/19, and 18/18.
- Quality scoring 0–100, unmapped-functionality tracking (it tells you what the source did that couldn't be converted), and rollback snapshots.

Available on npm: npm install -g hermes-skillforge
Repo: https://github.com/uthumany/hermes-skillforge
CI: green across Python 3.10–3.13; examples in examples/.

Happy to answer questions about the format-detection heuristics or the validator rules. Also very open to feedback on what skill formats to add next — GitLab, ComfyUI, and n8n workflows are on the roadmap.
```

### Posting tips

Post on a weekday 11:00–14:00 ET. Reply quickly to every early comment (response time matters for ranking). Do not vote on your own post and don't ask friends to upvote — HN downranks that. A follow-up "Ask HN" about which agent-skill format people want converted next is a good second wave 1–2 weeks later.

---

## 2. X/Twitter Thread

> Post the first tweet when ready, then reply to your own tweet with each subsequent post (this keeps the thread together and concentrates engagement). Replace handle mentions with real accounts if you use them.

### Tweet 1 (hook)

```
I built a tool that converts 20+ AI-agent formats into one universal standard.

Claude skills, Codex skills, Cursor rules, MCP servers, prompt packs, GitHub repos — all into validated, install-ready Hermes Agent skills.

A thread 🧵
```

### Tweet 2 (problem)

```
The agent ecosystem is fragmenting fast.

Every framework invented its own format:
• agentskills.io SKILL.md
• .claude / SKILL.md
• codex skills
• .cursor/rules
• MCP server configs
• plugins, prompt packs...

Same automation, hand-rewritten N times. No tests. No validation.
```

### Tweet 3 (solution)

```
Enter Hermes SkillForge 🛠️

A zero-dependency Python CLI (~2,150 lines, stdlib-only) that:

1. Auto-detects the source format with confidence scoring
2. Converts it into an official SKILL.md
3. Generates a pytest suite for the converted skill
4. Validates, scores (0–100), and redacts secrets
```

### Tweet 4 (workflow)

```
The workflow is dead simple:

$ skillforge analyze ~/my-cursor-rules
→ format: cursor_rules (confidence: high)

$ skillforge convert ~/my-cursor-rules
$ skillforge validate && skillforge test
$ skillforge install

Every skill ships rollback snapshots. Nothing silently breaks your setup.
```

### Tweet 5 (safety story)

```
The part I'm proudest of: safety.

• API keys, AWS keys, private keys → auto-redacted in output
• Dangerous commands flagged before install
• Placeholder scripts that need npm/rsync/servers are NEVER executed — statically validated instead
• Prompt-injection patterns scanned and rejected

Your converted skills are safe to hand to an agent.
```

### Tweet 6 (proof)

```
Does it actually work? The repo runs it on itself:

✅ Engine test suite: 10/10 passing
✅ CI matrix: Python 3.10, 3.11, 3.12, 3.13
✅ Demo conversions: agentskills.io skill 18/18, workflow repo 19/19, MCP server 18/18

Open source, MIT, CI badge green, contributions welcome.
```

### Tweet 7 (CTA)

```
Install it now:

$ npm install -g hermes-skillforge
$ npx hermes-skillforge convert <source>

Works with npm, yarn, pnpm, bun, deno, npx, Rush, Lerna, Volta.

Star the repo if you find it useful — it genuinely helps with discovery.

👉 github.com/uthumany/hermes-skillforge

#AI #LLM #agents #MCP #devtools #opensource
```

### Posting tips

Post between 9:00–11:00 ET on a weekday. Use the thread (reply-chain) format rather than a single long tweet — threads get 2–3x more reach. Engage with every reply in the first hour (the algorithm weighs early velocity heavily). Quote-tweet any early positive reply with a short demo GIF (record the CLI output with a tool like terminalizer). Tag related communities sparingly — at most 2–3 handles.

---

## 3. Bonus: One-liners for other channels

**Reddit (r/LocalLLaMA, r/ClaudeAI, r/ArtificialIntelligence) title:**

```
I built an open-source converter that turns Claude/Codex/Cursor skills and MCP servers into validated, test-covered Hermes Agent skills — 20+ formats, zero dependencies
```

**LinkedIn post opening line:**

```
Agent skills are the new libraries — but every platform invented its own format. I open-sourced a converter that unifies 20+ of them into one validated standard. MIT license.
```

**Discord/community pitch (short):**

```
Just shipped Hermes SkillForge (MIT): convert any agent skill / MCP server / prompt pack into an install-ready, validated Hermes skill with auto-generated tests. `npx hermes-skillforge convert <source>`. Repo: github.com/uthumany/hermes-skillforge
```

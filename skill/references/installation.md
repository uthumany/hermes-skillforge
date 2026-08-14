# Installation and Lifecycle

## Paths

| Item | Location |
|---|---|
| User skills (global) | `~/.hermes/skills/<category>/<skill>/` |
| Global skill index | `~/.hermes/skills/index.json` (managed by Hermes) |
| Converted source tree | `~/.hermes/skillforge/last_conversion/` |
| Rollback snapshots | `~/.hermes/skillforge/rollbacks/` |
| HERMES_HOME override | `$HERMES_HOME` env var |

## Installing

1. `python3 scripts/skillforge.py install` — copies the last validated
   conversion into `~/.hermes/skills/software-development/` (category is
   taken from `metadata.hermes.category`; override by placing the skill in
   the desired category directory and rebuilding the index).
2. Hermes discovers skills at session start; new skills are usable in a new
   session, or run `/reset` / `hermes skills reset` for the current one.

## Upgrading

`python3 scripts/skillforge.py update <source>` re-runs the pipeline against
the same source and bumps the `version` field of the installed copy
(patch-level increment). The prior version is snapshotted to `rollbacks/`.

## Conflicts

If a skill with the same (or hyphen-equivalent) name exists, the old copy is
backed up before overwrite and the report lists both paths.

## Uninstalling / rollback

`hermes skills uninstall <name>` removes the skill. The engine's
`python3 scripts/skillforge.py rollback` restores the most recent snapshot;
installed files are always snapshotted *before* modification, so removal is
always reversible within the recorded snapshots.

## Verification after install

```
hermes skills list | grep <name>      # local listing
hermes skills search <name>           # also searches online registry
```

The skill's slash command appears in a new session as `/skill-<name>`.

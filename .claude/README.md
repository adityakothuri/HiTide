# .claude/

Claude Code config for this repo. It comes from [ECC](https://github.com/affaan-m/ECC) and loads automatically when you run `claude` here.

| Folder | What it is |
|---|---|
| `agents/` | Specialist helpers Claude can hand work to (reviewers, build fixers, planners) |
| `commands/` | Slash commands like `/plan`, `/build-fix`, `/code-review` |
| `skills/` | Playbooks Claude follows for specific jobs (`ui-demo`, `orch-build-mvp`, ...) |
| `rules/ecc/` | Coding standards Claude always follows |
| `hooks/`, `scripts/` | Automatic checks that run while Claude works (format, typecheck, console.log warnings) |
| `settings.json` | Wires up the hooks and turns off the ones that slow us down |

You shouldn't need to edit anything here. See `HOW_TO_USE.md` in this folder for how to use it.

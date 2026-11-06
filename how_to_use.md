# How to use Claude Code on this repo

## Setup

Nothing to install. The ECC add-on (agents, skills, commands, rules) lives in this repo's `.claude/` folder.

1. Make sure you have **Node.js** installed (`node -v`).
2. Pull the repo, `cd` into it, and run `claude`.
3. If it asks whether to trust this folder, say yes.

## How to talk to it

Just talk normally. Say what you want and what "done" looks like.

- "Add a login page with email and password."
- "The build is broken, fix it."
- "This page looks generic. Make it look polished."
- "Review what I just changed before I push."

Claude picks the right tools on its own most of the time.

## Things to run by name

Type the ones starting with `/` directly. For the others, say "use the ___ skill".

| When | Run | What it does |
|---|---|---|
| Writing the idea down | `/prp-prd` | Asks questions, writes a short product spec |
| Starting the project | `orch-build-mvp` skill | Scaffolds a working MVP from the idea or spec |
| Starting a feature | `/plan` | Writes a step-by-step plan and waits for your OK |
| Building a feature | `/feature-dev` | Guided build of one feature |
| Build or type errors | `/build-fix` | Fixes errors with small, safe changes |
| Before pushing | `/code-review` | Catches bugs in your changes |
| UI looks bland | `frontend-design-direction` skill | Gives the UI a clear visual style |
| UI polish | `make-interfaces-feel-better` skill | Spacing, motion, small details |
| Testing the app | `browser-qa` skill | Clicks through the app and checks for errors |
| Deploying | `deployment-patterns` skill | Deploy setup and health checks |
| Demo video | `ui-demo` skill | Records a polished walkthrough video |
| Pitch slides | `frontend-slides` skill | Builds a slide deck as a web page |
| Taking a break | `/save-session`, later `/resume-session` | Picks up where you left off |
| "What can ECC do?" | `/ecc-guide` | Answers questions about ECC |

## Tips

- One task per message works best.
- If Claude heads the wrong way, press Esc and redirect it.
- Pull often and commit small, so it's easy to undo.

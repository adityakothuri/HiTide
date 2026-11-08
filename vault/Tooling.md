---
tags: [floodwatch, tooling, ecc]
status: in-progress
updated: 2026-11-07
---

# Tooling

Claude Code setup for this repo: the ECC add-on (agents, skills, commands, hooks, rules) plus the project's own config. ECC is installed project-locally in `.claude/`.

## Install layout

- `.claude/agents/`, `.claude/skills/`, `.claude/commands/`, `.claude/hooks/`, `.claude/scripts/`, `.claude/settings.json`: ECC assets, checked in.
- `.claude/rules/ecc/common/` plus language folders (`python/`, `typescript/`, `react/`, `web/`, and others): rules. The `python/` rules were copied from a clone of `affaan-m/everything-claude-code`.
- `CLAUDE.md` at the repo root: project rules Claude reads on every session. See [[00 Home]] for the phase tracker.
- `.claude/settings.local.json` and `.claude/ecc/` are gitignored (personal state).

## Counts

| Asset | Count | Location |
|---|---|---|
| Agents | 71 | `.claude/agents/` |
| Commands | 98 | `.claude/commands/` |
| Skills | 314 | `.claude/skills/` |

> [!abstract]- All agents
> a11y-architect, agent-evaluator, architect, bengali-reviewer, build-error-resolver,
> chief-of-staff, code-architect, code-explorer, code-reviewer, code-simplifier,
> comment-analyzer, commit-reviewer, conversation-analyzer, cpp-build-resolver, cpp-reviewer,
> csharp-reviewer, dart-build-resolver, database-reviewer, django-build-resolver,
> django-reviewer, doc-updater, docs-lookup, e2e-runner, fastapi-reviewer, flutter-reviewer,
> fsharp-reviewer, gan-evaluator, gan-generator, gan-planner, go-build-resolver, go-reviewer,
> harmonyos-app-resolver, harness-optimizer, healthcare-reviewer, homelab-architect,
> java-build-resolver, java-reviewer, kotlin-build-resolver, kotlin-reviewer, loop-operator,
> marketing-agent, mle-reviewer, network-architect, network-config-reviewer,
> network-troubleshooter, opensource-forker, opensource-packager, opensource-sanitizer,
> performance-optimizer, php-reviewer, planner, pr-test-analyzer, python-reviewer,
> pytorch-build-resolver, rag-pipeline-reviewer, react-build-resolver, react-reviewer,
> refactor-cleaner, ruby-reviewer, rust-build-resolver, rust-reviewer, security-reviewer,
> seo-specialist, silent-failure-hunter, spec-miner, swift-build-resolver, swift-reviewer,
> tdd-guide, type-design-analyzer, typescript-reviewer, vue-reviewer

> [!abstract]- All commands
> aside, astra-review, auto-update, build-fix, checkpoint, code-review, cost-report, cpp-build,
> cpp-review, cpp-test, ecc-guide, epic-claim, epic-decompose, epic-publish, epic-review,
> epic-sync, epic-unblock, epic-validate, evolve, fastapi-review, feature-dev, flutter-build,
> flutter-review, flutter-test, gan-build, gan-design, go-build, go-review, go-test,
> gradle-build, harness-audit, hookify, hookify-configure, hookify-help, hookify-list,
> instinct-export, instinct-import, instinct-status, issue-review, jira, kotlin-build,
> kotlin-review, kotlin-test, learn, learn-eval, loop-start, loop-status, marketing-campaign,
> model-route, multi-backend, multi-execute, multi-frontend, multi-plan, multi-workflow,
> orch-add-feature, orch-build-mvp, orch-change-feature, orch-fix-defect, orch-refine-code,
> orch-review, plan, plan-canvas, plan-prd, pm2, pr, project-init, projects, promote, prp-commit,
> prp-implement, prp-plan, prp-pr, prp-prd, prune, python-review, quality-gate, react-build,
> react-review, react-test, refactor-clean, resume-session, review-pr, rust-build, rust-review,
> rust-test, santa-loop, save-session, security-scan, sessions, setup-pm, skill-create,
> skill-health, skill-host-compat, test-coverage, token-card, update-codemaps, update-docs,
> vue-review

> [!abstract]- All skills
> accessibility, agent-architecture-audit, agent-eval, agent-harness-construction,
> agent-introspection-debugging, agent-payment-x402, agent-runtime-gateway-smoke-test,
> agent-security-hardening, agent-self-evaluation, agent-sort, agentic-engineering, agentic-os,
> ai-first-engineering, ai-regression-testing, android-clean-architecture, angular-developer,
> api-connector-builder, api-design, architecture-decision-records, article-writing,
> automation-audit-ops, autonomous-agent-harness, autonomous-loops, backend-patterns, benchmark,
> benchmark-methodology, benchmark-optimization-loop, bengali-nlp,
> blender-motion-state-inspection, blueprint, brand-discovery, brand-voice,
> brownfield-retrospective, browser-qa, bun-runtime, canary-watch,
> carrier-relationship-management, change-impact, cisco-ios-patterns, ck, claude-devfleet,
> click-path-audit, clickhouse-io, code-tour, codebase-onboarding, codehealth-mcp,
> coding-standards, competitive-platform-analysis, competitive-report-structure,
> compose-multiplatform-patterns, config-gc, configure-ecc, connections-optimizer,
> content-engine, content-hash-cache-pattern, context-and-decisions, context-budget,
> continuous-agent-loop, continuous-learning, continuous-learning-v2, contract-first,
> conventional-commit-review, cost-aware-llm-pipeline, cost-tracking, council,
> council-multi-model, counterparty-channel-discipline, cpp-coding-standards, cpp-testing,
> crosspost, csharp-testing, customer-billing-ops, customs-trade-compliance,
> dart-flutter-patterns, dashboard-builder, data-scraper-agent, data-throughput-accelerator,
> database-migrations, deep-research, deepseek-harness-setup, defi-amm-security, delivery-gate,
> deployment-patterns, design-system, dev-team, django-celery, django-patterns, django-security,
> django-tdd, django-verification, dmux-workflows, docker-patterns, docs-governance,
> documentation-lookup, dotnet-patterns, dynamic-workflow-mode, e2e-testing, ecc-guide,
> ecc-recipes, ecc-tools-cost-audit, email-ops, energy-procurement, enterprise-agent-ops,
> error-handling, esign-field-placement, eval-harness, evm-token-decimals, exa-search,
> fal-ai-media, fastapi-patterns, finance-billing-ops, flox-environments,
> flutter-dart-code-review, foundation-models-on-device, frontend-a11y,
> frontend-design-direction, frontend-patterns, frontend-slides, fsharp-testing,
> gan-style-harness, gateguard, generating-python-installer, git-workflow, github-ops,
> golang-patterns, golang-testing, google-workspace-ops, growth-log, healthcare-cdss-patterns,
> healthcare-emr-patterns, healthcare-eval-harness, healthcare-phi-compliance, hermes-imports,
> hexagonal-architecture, hipaa-compliance, homelab-network-readiness, homelab-network-setup,
> homelab-pihole-dns, homelab-vlan-segmentation, homelab-wireguard-vpn, hookify-rules, i18n-sync,
> inherit-legacy-style, intent-driven-development, inventory-demand-planning, investor-materials,
> investor-outreach, ios-icon-gen, issue-review, iterative-retrieval, ito-baskets, ito-compute,
> ito-inference, ito-training, java-coding-standards, jira-integration, jpa-patterns,
> knowledge-ops, kotlin-coroutines-flows, kotlin-exposed-patterns, kotlin-ktor-patterns,
> kotlin-patterns, kotlin-testing, kubernetes-patterns, laravel-patterns,
> laravel-plugin-discovery, laravel-security, laravel-tdd, laravel-verification,
> latency-critical-systems, lead-intelligence, liquid-glass-design, living-docs-governance,
> llm-trading-agent-security, logistics-exception-management, loop-design-check,
> mailtrap-email-integration, make-interfaces-feel-better, manim-video, market-research,
> marketing-campaign, master-agreement-generator, mcp-dependency-review, mcp-server-patterns,
> messages-ops, ml-adoption-playbook, mle-workflow, module-governance, module-regression,
> motion-advanced, motion-foundations, motion-patterns, mybatis-patterns, mysql-patterns,
> nanoclaw-repl, nasiko-control-plane, nestjs-patterns, netmiko-ssh-automation,
> network-bgp-diagnostics, network-config-validation, network-interface-health, nextjs-turbopack,
> nodejs-keccak256, nutrient-document-processing, nuxt4-patterns, openclaw-persona-forge,
> opensource-pipeline, operator-approval-loop, orch-add-feature, orch-build-mvp,
> orch-change-feature, orch-fix-defect, orch-pipeline, orch-refine-code, osint-investigation,
> parallel-execution-optimizer, perl-patterns, perl-security, perl-testing, plan-canvas,
> plan-orchestrate, plankton-code-quality, postgres-patterns, prediction-market-oracle-research,
> prediction-market-risk-review, prisma-patterns, product-capability, product-lens,
> production-audit, production-scheduling, project-flow-ops, prompt-caching-strategy,
> prompt-optimizer, python-patterns, python-testing, pytorch-patterns, quality-nonconformance,
> quarkus-patterns, quarkus-security, quarkus-tdd, quarkus-verification, rails-patterns,
> ralphinho-rfc-pipeline, react-native-patterns, react-patterns, react-performance,
> react-testing, recsys-pipeline-architect, recursive-decision-ledger, redis-patterns,
> regex-vs-llm-structured-text, remotion-video-creation, repo-scan, research-ops,
> returns-reverse-logistics, rules-distill, rust-patterns, rust-testing, safety-guard,
> santa-method, scientific-db-pubmed-database, scientific-db-uspto-database, scientific-pkg-gget,
> scientific-thinking-literature-review, scientific-thinking-scholar-evaluation, search-first,
> security-bounty-hunter, security-review, security-scan, seo, skill-comply, skill-host-compat,
> skill-scout, skill-stocktake, social-graph-ranker, social-publisher, springboot-patterns,
> springboot-security, springboot-tdd, springboot-verification, story-lifecycle,
> strategic-compact, swift-actor-persistence, swift-concurrency-6-2, swift-protocol-di-testing,
> swiftui-patterns, taste, taste-application, taste-distillation, tasteforge-video, tdd-workflow,
> team-agent-orchestration, team-builder, terminal-opener, terminal-ops, test-collaboration,
> tinystruct-patterns, token-budget-advisor, token-card, typescript-patterns, ui-demo, ui-to-vue,
> uncloud, unified-memory, unified-notifications-ops, verification-loop, video-editing, videodb,
> visa-doc-translate, vite-patterns, vue-patterns, windows-desktop-e2e, workspace-surface-audit,
> x-api

## Used on this project

| Asset | When | Why | Status |
|---|---|---|---|
| `planner` agent | Start of each phase | Break the phase into tasks before coding. Phase 1 breakdown done here. | Done for Phase 1 and Phases 2-3 (2026-11-07). The Phases 2-3 plan set the demo clock rule: fast-forward the flood, then run at 1x. |
| `tdd-workflow` skill | Core logic (risk, road status, stop detection, escalation, route check) | Tests first. Road status went RED, then GREEN with 19 tests. See [[Risk Scoring]]. | Done: road status, flood model, risk scoring, route check and lookahead, outreach guard, stop detection and escalation, reply parser. 185 tests. RED and GREEN commits are on `feat/backend-sim`. |
| `doc-updater` agent | After each phase | Keeps this vault and the module notes in step with the code. | Used for this vault (2026-11-07) |
| `python-reviewer`, `fastapi-reviewer`, `code-reviewer` agents | Before each phase is marked done | Catch Python, FastAPI, and general issues before the phase closes. | `python-reviewer` ran for Phase 1: 0 critical, 2 high, 6 medium. Both high and 5 medium fixed in commit `fix: address python-reviewer findings`. Skipped: demo-key auth. `code-reviewer` ran for Phases 2-3: 0 critical, 2 high (a blocking send, timers acting after a reply), 6 medium. All fixed. `python-reviewer` ran on vision and Photon: 1 high ("not safe" parsed as safe), 6 medium. All fixed, with a new TDD parser (20 tests). `code-reviewer` ran on Photon 2.0 and voice: 0 critical, 1 high (an LLM-collected "safe" could override a spoken "help"), fixed with TDD. Of 6 mediums, 5 fixed: cancel on reset, guarded call task, scrubbed summaries, accurate timeline note, WS shutdown. Stale poll votes are noted as a known gap. |
| `security-scan` skill + `security-reviewer` agent | Before submission | Check secrets, input validation, and the WS and webhook surface. Results go in [[Privacy and Consent]]. | Done 2026-11-07. Results and fixes are in [[Privacy and Consent]]. |
| `Explore` agent (built-in) | Reading unfamiliar code or docs | Fast read-only search across the repo. Built into Claude Code, not in `.claude/agents/`. | Used as needed |

## Teammates: optional ECC plugin

ECC already works from `.claude/`. To get the plugin's commands and agents in your own session, run these inside Claude Code:

```
/plugin marketplace add affaan-m/everything-claude-code
/plugin install everything-claude-code@everything-claude-code
```

## Related

- [[Decisions]]
- [[Architecture]]
- [[Privacy and Consent]]

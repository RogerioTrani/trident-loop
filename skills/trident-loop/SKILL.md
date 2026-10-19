---
name: trident-loop
description: "Harden a plan with independent cross-provider review (Claude, Codex, Kimi, DeepSeek, Qwen), then optionally build and cross-inspect it. Start in any supported host CLI: the host plans and another provider reviews. Use for trident this plan, trident-loop, or trident this feature; not for trivial edits."
---

# Trident Loop

The current conversation owns requirements, planning and coordination. The other provider reviews the plan. Either provider can build; the provider that did not build inspects the final code in a fresh session.

## Resolve roles once

Identify the actual host from your runtime, not PATH, installed skills, model-name guesses, or the repository. Several CLIs may be installed. Any registered provider can be the host: use `host=claude` in Claude Code, `host=codex` in Codex, `host=kimi` in Kimi Code, and the matching runtime identity for any further provider. If the runtime identity is unavailable, ask which host the user is using once.

**Provider registry and pipeline order.** The default pipeline order is the explicit list `claude, codex, kimi, deepseek, qwen`. A provider joins the end of the list once its runner boundary is implemented, and the order can be changed per run with `providers=` / `PROVIDER_ORDER`. Resolve every default role from this order:

- Default plan reviewer: the first provider in the pipeline order that is not the host.
- Default builder: the host. The host remains coordinator even when another provider builds.
- Default final inspector: the first provider in the pipeline order that is not the builder, in a fresh session.

Honor explicit `reviewer=`, `builder=` and `inspector=` with any registered provider. To swap the planner, start the conversation in the other host; do not pretend a CLI reviewer is the user's planning conversation.

**Recommendation, not prohibition.** Following the pipeline order and default roles is the recommended path: it keeps the reviewer independent of host and builder by construction and keeps the loop bounded. The user may deviate at any point — a different reviewer, a reordered pipeline, extra rounds — provided every deviation and its reason is recorded in `LOG_FILE`. A deviation applies to the current decision only, unless the user says it is standing; deviations never silently become the new default.

**Interactive role dialogue.** At each role decision — reviewer before round 1, any reviewer change between rounds, builder, inspector — state the pipeline default as a recommendation and ask the user, unless the user has already given a standing instruction that covers it (for example: "tax-calculation reviews go to provider X", "always follow the pipeline", or an explicit `reviewer=` for this run). Record standing instructions in `LOG_FILE` and apply them without re-asking. When two standing instructions conflict, surface the conflict and ask. Silence after a recommendation approves only the recommended role — nothing else.

**Kimi roles.** Kimi (`kimi`, Kimi Code CLI) has no per-call flags for effort, permission mode or output schema, and its review tool surface is set by an agent-file allowlist. Read [the Kimi notes](references/runtime.md#kimi) before choosing it. Model aliases must already exist in the Kimi `config.toml`. The runner never edits that config. Use the alias, not the display name: `kimi-code/kimi-for-coding` is the model shown as "K2.8 Preview", and `kimi-code/k3-256k` is "K3-256k". Kimi has no per-call effort: the levels are low, high and max, and the runner applies the `[thinking] effort` of the config (currently `high`). Kimi has no "medium" level, and the runner refuses any `--effort` that differs from the config instead of running at another level. Omit `--effort` for Kimi. The record shows the applied level. Whether medium should map to high is the owner's decision, and the runner does not make that mapping on its own.

Model selection is independent of provider roles. Preserve the host's selected model. Review/build CLI calls inherit their own configuration unless `reviewer_model`, `builder_model`, or `inspector_model` is supplied; map these to the runner's `--model` for that invocation. Apply an explicit `*_effort` similarly. Fable 5.1, GPT-6 Astra and Kimi K3 (`kimi-code/k3-256k`) are suitable explicit choices, not mandatory pins. A model in the host UI does not prove which model a separate CLI will use. Report requested and observed model information separately; report an unresolved CLI default honestly. For Kimi, the stream exposes no observed model, so the record keeps the requested alias and marks the observed model unknown. Never silently fall back to another model/provider on a failure.

Read [the runtime reference](references/runtime.md) before launching a CLI. Resolve its runner relative to this installed SKILL.md, never relative to the project being reviewed. Use absolute paths when launching it.

If the user supplies `codex_cli` or `claude_cli`, map the selected provider's executable path to `--cli`. A host app can have a newer working binary than the CLI on PATH; verify the path and version without silently changing global installation or configuration.

## Tunables

| Argument | Default | Meaning |
|---|---|---|
| `PLAN_FILE` / `plan` | `PLAN.md` | Plan path used throughout, including the build handoff |
| `LOG_FILE` / `log` | `PLAN-REVIEW-LOG.md` | Append-only transcript |
| `rounds` / `MAX_ROUNDS` | `5` | Default plan-review round budget; user extension is honored and recorded |
| `reviewer` | pipeline default | Chosen per round; may change between rounds on user request or standing instruction |
| `providers` / `PROVIDER_ORDER` | `claude,codex,kimi` | Pipeline order used to resolve default roles; extendable as providers are implemented |
| `builder` | host | Provider implementing the plan |
| `research` | proportionate to task | `none`, `web`, or explicit opt-in `deep` |
| `mode` | `full` | `full` includes recon/interview; `review` starts from an existing plan |
| `inspect` | `on` | `off` only when the user explicitly opts out; record it |
| `MAX_FIX_ROUNDS` | `2` | Bounded build-fix attempts before reporting or taking over |
| `MAX_INSPECTION_ROUNDS` | `2` | Initial inspection plus one after fixes |

Echo roles, paths, round limits, requested models and inspection opt-out before starting. Preserve existing authorization: a request to plan does not authorize building; a request to plan and implement does. Do authorized preparation before seeking any remaining sign-off.

## Phase 0 — Recon

For existing projects, inspect relevant code, dependencies, callers and writers of shared state. Read existing `CONTEXT.md` / `CONTEXT-MAP.md` and relevant ADRs. For greenfield work, research prior art, a reasonable stack and concrete failure modes when useful. Respect an explicit research depth. Deep multi-agent research requires explicit opt-in and an available tool; otherwise use supported targeted research, and report the limitation. Do not require a proprietary Workflow tool or hard-code a research-agent model.

Discover relevant skills through the host's available catalog and the other provider's documented skill locations when accessible. Record only relevant proposed dependencies. Do not assume host MCP, browser, credentials or skills transfer to the other CLI. Verify required build capabilities before relying on them.

Present one assumptions ledger with source paths or research links. Ask for corrections to material uncertainties as a batch. Resolve routine reversible choices yourself when the user has authorized the work; silence is not approval of an action requiring approval.

## Phase 1 — Settle requirements

Maintain a short visible decision map. Ask only about unresolved decisions that change the outcome. For each consequential question, give the recommendation, why it matters, and the cost of guessing wrong. Batch independent questions; ask dependent ones sequentially. If the code can answer, inspect it instead. Offer “accept all remaining recommendations” when a long decision list would slow the user down.

Respect existing glossary definitions; resolve ambiguous domain language. Maintain glossary-only context lazily using [CONTEXT-FORMAT.md](CONTEXT-FORMAT.md). Record an ADR only for expensive-to-reverse, non-obvious trade-offs using [ADR-FORMAT.md](ADR-FORMAT.md).

Write the resolved `PLAN_FILE` with:
- Goal and observable acceptance criteria.
- Concrete approach, key decisions, trade-offs and non-goals.
- Confirmed assumptions with sources and remaining risks.
- Relevant toolchain requirements per provider, if any.
- Verification: exact proof command(s), expected results, and manual/visual checks when needed.

Derive proof commands from the repository when possible. Ask only when what counts as success remains unclear. Start the append-only `LOG_FILE` with roles, model requests, scope, authorization and round limits. Keep run diagnostics outside the checkout.

With `mode=review`, load the supplied plan, fill only material gaps with the user as needed, and proceed directly to review; do not restart a requirements interview.

## Phase 2 — Independent plan review

Use the shared runner in `review` mode with the actual `--host`, resolved `--plan` and optional model/effort. Record each round in `LOG_FILE` with its reviewer provider, requested and observed model, verdict and session continuity. The reviewer of round 1 is chosen as recommended above. A further round with the **same** reviewer uses `--resume <previous-successful-result.json>` with the same provider/model/effort and a host-authored `--feedback` file containing dispositions, when that provider supports resume. A round with a **new** reviewer — a user-requested swap at any round boundary, a standing instruction, or a provider without resume — starts a fresh session that receives the full prior context: the current plan body plus every previous round's findings and the host's dispositions. Mark the continuity accordingly: `resumed`, `fresh-session-with-prior-review` (forced for Kimi, whose CLI refuses `--session` together with its agent-file), or `fresh-reviewer` (provider change). A reviewer swap never resets the round count, and the approval at the end binds to the final reviewer's verdict on the final plan hash. Never use a guessed session id, `--last`, or a build session as a reviewer.

Each successful response contains a verdict, evidence-backed findings, actual coverage and limitations. Preserve the entire response and runner result path in `LOG_FILE`.

- **APPROVED:** no unresolved material defects. Approval is bound to the exact plan path and SHA256. Present remaining low-priority advice and limitations; zero findings is valid and is not proof of exhaustive correctness.
- **REVISE:** the host arbitrates each finding. Implement warranted plan changes; reject unsupported suggestions with reasons. Record dispositions and send the revised plan to the round's reviewer (the same one by default; a swap follows the interactive role dialogue above). Avoid relitigating resolved points without new evidence.
- **BLOCKED / failed process / malformed result:** never count this as approval. Explain the actual missing evidence or operational failure. Do not burn remaining rounds on blind retries or switch providers silently; a provider change is a recorded user decision, not an automatic retry mechanism.

Stop at `MAX_ROUNDS`. The cap is a default against manufactured convergence, not a prohibition: when the user explicitly extends the budget — common in high-stakes domains such as financial, tax or compliance work — continue, recording the extension, the new cap and the reason. Present unresolved findings and the host's position instead of manufacturing convergence. A changed plan requires another review. Before building, run the approval check on the final plan. If the user explicitly chooses to proceed without independent approval, record that override and use the standalone unreviewed-spec path; never label it approved.

## Phase 3 — Build and inspect

Present the reviewed plan, improvements and remaining limits. If implementation is not already authorized, ask for that final decision. Use the selected builder, defaulting to the host. Kimi as builder also needs `--accept-kimi-config-permission` unless the Kimi config's `default_permission_mode` is `manual`; see [the build reference](references/build.md).

The host can implement directly with its normal tools. For a different builder, use the shared runner's `build` mode. Either path must capture the pre-build commit, preserve unrelated user work, and carry the same resolved plan and verification contract.

Run the agreed proof checks, inspect all changed files and review the result through the other provider in a **fresh** `inspect` session. Supply the pre-build commit and builder identity. Reinspection after accepted fixes also uses a fresh session. Log findings and dispositions; rerun affected proof checks after fixes.

If the coordinator takes over coding, it has become a builder. Require a fresh other-provider inspection of its changes; never describe the earlier inspection as covering later edits. If a provider acted as reviewer in earlier rounds and later becomes builder, record the role change in `LOG_FILE`; its own earlier findings never count as independent inspection of its build. If both providers contributed code, record authorship and have each inspect the other's changes; do not claim any model independently reviewed code it authored. If the inspection budget is exhausted, report remaining findings and unreviewed edits explicitly for the user's decision.

Present the final diff, proof results, inspection coverage, unresolved findings, deviations and rounds used. Honor existing commit/push authorization; otherwise leave the concrete diff ready for sign-off. External publication is never implied merely by running the loop.

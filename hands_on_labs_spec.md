# Hands-On Labs to Build — Multi-Model, Vendor-Agnostic AI-Native Coding

**Source outline:** Multi-Model, Vendor-Agnostic AI-Native Coding Approaches (2-Day / 16-Hour Workshop)
**Design principle applied:** every lab produces a *visible, demonstrable end state* for the participant (a running app, a populated dashboard, a diff, or a report) — not just "steps completed."

---

## Lab 1 — API Familiarization & Baseline Testing
**Maps to:** Module 1, The Multi-Model Imperative
**Duration:** ~90 min

**What needs to be built:**
- A pre-configured OpenCode environment wired to AWS Bedrock with at least 3 model tiers enabled (e.g., Claude Sonnet, Claude Opus, GPT-5.6 Sol, GPT-5.6 Terra).
- A fixed set of 4–5 standardized enterprise coding prompts (e.g., "write a rate limiter," "refactor this function for readability," "design a caching layer") that every participant runs against every model.
- A benchmark capture template (spreadsheet or simple web form) that logs latency, token cost, and a 1–5 quality rating per model per prompt.

**Visible end result for the participant:**
A completed **model comparison scorecard** (table or dashboard) showing side-by-side latency, cost, and quality across all tested models for identical prompts — something they can screenshot and take back to their team as evidence for model-selection decisions.

---

## Lab 2 — Multi-Model Task Orchestration in OpenCode
**Maps to:** Module 2, Model Selection & Prompt Orchestration Workflows
**Duration:** ~2 hrs

**What needs to be built:**
- A small, intentionally incomplete feature/codebase (e.g., a REST API missing an endpoint, or a React component missing state logic) that requires both architecture-level design and routine implementation work.
- An OpenCode orchestration template/config that lets participants route the "design" sub-task to a higher-tier model (Opus/Sol) and the "implementation/refactor" sub-tasks to a lower-tier model (Sonnet/Codex).
- A test suite or acceptance checklist to validate the finished feature.

**Visible end result for the participant:**
A **working feature they can run and test live** — e.g., hit the new API endpoint in Postman/browser and see correct output, or render the UI component and interact with it — built through model handoff rather than a single model doing everything.

---

## Lab 3 — Plan-and-Execute Workflows in OpenCode
**Maps to:** Module 3, Multi-Agent Orchestration & Auto-Tuning
**Duration:** ~2 hrs

**What needs to be built:**
- A moderately complex development task (e.g., "add authentication middleware," "implement a data-export module") sized to need a genuine plan (multiple files/steps) rather than a one-shot prompt.
- A structured "Plan Mode" prompt template for the high-reasoning model (Opus) to produce a step-by-step implementation plan/spec.
- A follow-on execution template that feeds that plan into the fast completion model (Sonnet) module-by-module, with a verification checkpoint after each step.

**Visible end result for the participant:**
A **fully built and runnable module** (e.g., login flow working end-to-end, or exported file correctly generated) plus the **artifact plan document** Opus produced — so they can see both the blueprint and the finished, working software it produced.

---

## Lab 4 — Cost-Aware Workflow Optimization
**Maps to:** Module 4, Enterprise Cost, Governance, and Best Practices
**Duration:** ~90 min

**What needs to be built:**
- A multi-step coding pipeline (e.g., a chain of 4–6 OpenCode tasks: generate → test → refactor → document) that currently uses a high-tier model at every step, deliberately over-provisioned.
- A cost/performance tracking template (tokens used, $ cost, wall-clock time, pass/fail on tests) captured "before" the refactor.
- Guidance for participants to selectively downgrade steps to lower-tier models or cross-vendor fallback models without breaking test pass rates.

**Visible end result for the participant:**
A **before/after optimization report** showing the same pipeline output/tests still passing, alongside a measurable cost and/or latency reduction (e.g., "42% lower token spend, same test pass rate") — a concrete, presentable governance artifact.

---

---

## Additional Labs (pulled from outline bullets not yet covered by a lab)

### Lab 1B — Vendor Lock-In & Failover Simulation
**Maps to:** Module 1, "Mitigating vendor lock-in and managing API latency"
**Duration:** ~45 min

**What needs to be built:**
- A simple coding task pre-wired to run against a "primary" vendor model.
- A simulated outage/timeout/rate-limit injected mid-task (mock error response).
- A pre-built fallback routing config that reroutes to a secondary, cross-vendor model.

**Visible end result:** The task **completes successfully despite the simulated outage** — participants see the failover log/trace showing the automatic handoff from Vendor A to Vendor B with the final output still delivered.

---

### Lab 2B — Context Continuity Across Model Switches
**Maps to:** Module 2, "Managing context window efficiency and state continuity across model switches"
**Duration:** ~60 min

**What needs to be built:**
- A multi-turn coding task too large for a single context window, split across 2+ model handoffs (e.g., Opus designs, Sonnet implements, a third pass reviews).
- A context-passing template (summary/state file) participants populate between hops.
- A "broken" version of the same task with no context hand-off, for comparison.

**Visible end result:** A **working end-to-end solution assembled from context handed cleanly between models**, next to a visibly broken/inconsistent output from the no-context-passing version — a direct before/after contrast participants can see on screen.

---

### Lab 3B — Cross-Model Verification System
**Maps to:** Module 3, "Designing collaborative AI systems with cross-model verification"
**Duration:** ~75 min

**What needs to be built:**
- A code-generation task where one model produces a solution and a second, different-vendor model is tasked purely with reviewing/critiquing/testing it.
- A structured verification loop (generate → critique → revise → re-verify) implemented in OpenCode.
- A deliberately flawed starter solution to guarantee the verifier catches at least one real bug.

**Visible end result:** A **verification report showing the bug the second model caught**, plus the corrected, passing code — tangible proof the cross-model check added value the single model missed.

---

### Lab 3C — Auto-Tuning Prompts for Lower-Tier Models
**Maps to:** Module 3, "Auto-Tuning: using high-tier models to systematically optimize prompts and extraction schemas for lower-tier models"
**Duration:** ~60 min

**What needs to be built:**
- A task where a lower-tier model initially performs poorly against a fixed test/eval set using a naive prompt.
- A workflow where a high-tier model analyzes the failures and rewrites/optimizes the prompt or extraction schema.
- The same eval set to re-run the lower-tier model against the tuned prompt.

**Visible end result:** A **before/after accuracy score** (e.g., "prompt v1: 4/10 tests passing → auto-tuned prompt v2: 9/10 tests passing") using the same cheap model both times — proof that tuning, not a bigger model, closed the gap.

---

### Lab 4B — Enterprise Governance & Compliance Configuration
**Maps to:** Module 4, "Leveraging centralized enterprise governance... Navigating data privacy, BAAs, and compliance"
**Duration:** ~45 min

**What needs to be built:**
- A sandboxed AWS Bedrock account/console view with model-access policies to configure (allow-listing models, guardrails, logging).
- A scenario requiring participants to restrict a specific data classification (e.g., "PII-tagged code") to only in-region/BAA-covered models.
- A test request that should be blocked, and one that should be allowed, once policy is correctly configured.

**Visible end result:** A **live policy test showing the disallowed request rejected and the compliant request succeeding** — a screenshot-able proof of correctly configured governance controls.

---

## Summary Table (Updated)

| Lab | Module | Core Deliverable Participant Walks Away With |
|---|---|---|
| 1. API Familiarization & Baseline Testing | 1 | Model comparison scorecard (latency/cost/quality) |
| 1B. Vendor Lock-In & Failover Simulation | 1 | Task completes despite simulated outage, via failover trace |
| 2. Multi-Model Task Orchestration | 2 | Working, testable feature built via model handoff |
| 2B. Context Continuity Across Model Switches | 2 | Working solution vs. broken no-context version, side by side |
| 3. Plan-and-Execute Workflows | 3 | Running module + the Opus-generated plan behind it |
| 3B. Cross-Model Verification System | 3 | Verification report catching a real bug + corrected code |
| 3C. Auto-Tuning Prompts for Lower-Tier Models | 3 | Before/after accuracy score on same cheap model |
| 4. Cost-Aware Workflow Optimization | 4 | Before/after cost & performance report |
| 4B. Enterprise Governance & Compliance Config | 4 | Live policy test: blocked vs. allowed request |

## Build Checklist (for content developers)
- [ ] Provision AWS Bedrock access + OpenCode environment with all required model tiers enabled for each lab
- [ ] Author starter codebases/repos for Labs 2–4 (intentionally incomplete, with test suites)
- [ ] Write the standardized prompt sets for Lab 1
- [ ] Build the benchmark/scorecard template (Lab 1) and cost-tracking template (Lab 4)
- [ ] Draft Plan Mode prompt template + verification checkpoints for Lab 3
- [ ] Define pass/fail acceptance criteria for each lab's "visible end result"
- [ ] Time-box and dry-run each lab to confirm it fits its allotted slot

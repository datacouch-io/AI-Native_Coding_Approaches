# OpenCode + Bedrock Labs — Shared Setup

Status: **tested** — every step below was run for real on 2026-09-04 (macOS, Darwin 25.5.0).

This is the "no proxy — use OpenCode directly against AWS Bedrock" end-user course, built to `hands_on_labs_spec.md`. Do this setup once before Lab 1.

## 1. Prerequisites

- Node.js + npm (tested with Node v26.4.0 / npm 11.17.0)
- AWS CLI v2 (tested with 2.35.11) with credentials that have Bedrock access
- macOS with Terminal.app and Safari, for the screenshot mechanism below

## 2. Install OpenCode

```bash
npm install -g opencode-ai
opencode --version
```

**Verified 2026-09-04:** installed `opencode-ai@1.18.27`, `opencode --version` → `1.18.27`.

> **Tested gotcha:** `npm install -g opencode-ai` prints a warning that its `postinstall` script was blocked by npm's `allow-scripts` guard. In this environment the CLI worked anyway (the postinstall step wasn't required for basic operation) — but if `opencode` isn't found or misbehaves after install, re-run with `npm install -g --allow-scripts=opencode-ai opencode-ai`.

## 3. Configure the Bedrock provider

`opencode.json` in the project root:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "amazon-bedrock": {
      "options": { "region": "us-east-1" }
    }
  }
}
```

```bash
export AWS_REGION=us-east-1
export AWS_PROFILE=default
opencode models | grep amazon-bedrock | head -5
```

**Verified 2026-09-04:** full Bedrock catalog listed, including all four models this course uses:
- `amazon-bedrock/us.anthropic.claude-sonnet-5`
- `amazon-bedrock/us.anthropic.claude-opus-5`
- `amazon-bedrock/global.openai.gpt-5.6-sol`
- `amazon-bedrock/global.openai.gpt-5.6-terra`

> **Tested gotcha:** OpenCode does **not** fall back to the AWS CLI's default-profile behavior. Running `opencode run` with no `AWS_PROFILE` set fails with `Error: AWS SigV4 authentication requires AWS credentials... AWS access key ID setting is missing` — even though `aws sts get-caller-identity` and raw `aws bedrock-runtime converse` calls work fine with the same shell's implicit default profile. You must export `AWS_PROFILE` (or `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, or `AWS_BEARER_TOKEN_BEDROCK`) explicitly before running `opencode`.

> **Tested gotcha:** the GPT-5.6 models (`openai.gpt-5.6-sol`, `openai.gpt-5.6-terra`) only appear under the `global.` prefix in OpenCode's model list, not `us.` — even though AWS's own `aws bedrock list-inference-profiles` shows both `us.openai.gpt-5.6-terra` and `global.openai.gpt-5.6-terra` as ACTIVE. Use `global.openai.gpt-5.6-sol` / `global.openai.gpt-5.6-terra` with OpenCode.

> **Root-credentials caveat:** this account's AWS credentials are the **root user**, not a scoped IAM/SSO identity. That's fine for the labs in `hands_on_labs_spec.md` (none of them require blocking a specific model via IAM policy), but if a later lab needs to test an actual access-denied scenario, root cannot be restricted by an IAM policy attached to itself — that needs a real scoped IAM user/role (or an Organizations SCP), which is a separate, real AWS change to make deliberately, not assume.

## 4. Cost/latency/token capture

`opencode run --format json` emits newline-delimited JSON events. The one that matters for benchmarking is `step_finish`:

```json
{"type":"step_finish", "part": {"tokens": {"total":13111,"input":1,"output":1985,"cache":{"write":640,"read":10485}}, "cost": 0.023549}}
```

`cost` is computed by OpenCode itself from the real per-token pricing of whichever model answered — no need to hand-roll a pricing table.

> **Tested gotcha:** the *first* `opencode run` call against a given model pays a large **cache-write** cost for its own system prompt/tool definitions (~10-11K tokens on Claude models via Bedrock, ~6.3K on the GPT-5.6 models). This makes a bare `opencode run` call cost noticeably more than the same prompt sent as a raw Messages/Chat-Completions API call would (compare: a raw Claude Sonnet 5 API call for a small refactor cost ~$0.003 in this course's other lab; the same prompt through OpenCode cost ~$0.006-0.04 depending on response length). **Correction after further testing:** this is not strictly "once per session" — it's a provider-side prompt cache keyed by (model, system-prompt content) with its own TTL, so a *fresh* session can still hit a warm cache if the same model was called recently by anything (confirmed: a "first" call in one quick test showed `cache.read` already populated from a prior call minutes earlier). `opencode run --continue` deliberately reuses the same session and reliably shows the cache-write drop to near-zero on the second call — real, measured ~30% cost reduction on a short follow-up prompt. This is the course's own "context bloat" / prompt-cache teaching point, observed directly rather than asserted — see Lab 1's practice exercise 3 for a hands-on version of this measurement.

## 4b. Python environment for verification steps

The labs verify AI-generated code by *executing* it, which needs a Python environment of its own:

```bash
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip pytest flask
```

**Tested gotcha:** system Python has no `pytest`, so `python3 -m pytest` fails with
`No module named pytest`. Use `./.venv/bin/python -m pytest`.

**Tested gotcha:** `flask` is needed not because the labs build a web app, but because two of the
four models (claude-sonnet-5, gpt-5.6-sol) spontaneously wrapped their Lab 1 rate-limiter answer
in a Flask app with a module-level `from flask import ...`. Their code cannot be imported without
it. This is a finding about model behaviour worth showing participants, not a task requirement.

## 5. Keeping baseline runs clean: use the `plan` agent

`opencode run --agent plan ...` denies file `edit`/`write` (it can still `read`), so a benchmarking prompt like "write a rate limiter" returns the code as response text instead of actually creating files in the run directory. Confirmed: running the same prompt with `--agent plan` left the working directory untouched (`ls` before/after identical).

## 6. Screenshot capture mechanism (macOS) — Terminal AND browser

Same core technique as the gateway course: open a **dedicated, freshly-created** window, capture **only that window by ID** (`screencapture -l<window-id>`) — never a full-screen `screencapture -x` (confirmed unsafe there: it can capture an unrelated app with private content).

**Verifying the window ID is real, every time:** `tell application "Terminal" to id of front window` is not always reliable if focus has moved between apps — in this session it twice returned an ID that no longer existed. The robust pattern: diff the window list before/after creating the window, and screenshot the new window once to visually confirm it's clean *before* sending it anything real:

```bash
BEFORE=$(osascript -e 'tell application "Terminal" to get id of every window')
osascript -e 'tell application "Terminal" to activate' -e 'tell application "Terminal" to do script "clear"'
AFTER=$(osascript -e 'tell application "Terminal" to get id of every window')
# the new window's ID is whatever is in AFTER but not BEFORE
```

**Browser windows work the same way, with one extra catch:** a brand-new Safari window (`make new document with properties {URL:...}`) is scoped to just that window's content — but Safari's **sidebar is a persistent, cross-window UI element** that can show the user's real saved Favorites/bookmark folders regardless of which window/tab is showing. Confirmed the hard way: a first attempt at screenshotting a local dashboard file captured real bookmark folder names in the sidebar. Fix: hide the sidebar before capturing (`Cmd+Shift+L` via System Events keystroke, or click the sidebar toggle), and **verify with one throwaway capture** that only your own page content is visible before trusting the screenshot.

```bash
osascript -e 'tell application "Safari" to make new document with properties {URL:"file:///absolute/path/to/file.html"}'
# ... get its real window ID the same diff way as above ...
osascript -e 'tell application "System Events" to tell process "Safari" to keystroke "l" using {command down, shift down}'
# capture once, READ it, confirm no sidebar/other-window content leaked, THEN treat it as evidence
screencapture -x -o -l<WINDOW_ID> path/to/screenshot.png
```

**Always open and read the resulting image before writing a caption.** Close the window when done (`tell application "Safari"/"Terminal" to close window id <ID>`).

## 7. Cleanup convention

No persistent infrastructure (no proxy process, no database) is stood up by these labs — that's the point of this course's "no gateway" philosophy. Cleanup is limited to: closing any windows opened for screenshots, and removing local scratch files (extracted test scripts, `__pycache__`, throwaway venvs) that aren't real evidence.

# P4-U1 — Provider B preflight (verify before Phase 4)

_No code. Per plan §7 "Verify before Phase 4" + risk R-D: **an explicit human
sign-off must be recorded at the bottom of this note before any P4 code
(P4-U2…U6) is written.**_

Date probed: **2026-09-10**  ·  Machine: Windows 11, `claude` CLI **2.1.263**
(`/c/Users/Pc/.local/bin/claude`), logged in on the grader's own Claude
subscription.

---

## 1. What Phase 4 will do

`classroom_tool/claude_provider.py` (R8) → **Provider B only** in the UI: the tool
`subprocess.run`s the grader's *own* already-installed, already-logged-in
`claude` CLI:

```
claude -p "<prompt>" --model claude-opus-5 --output-format json
```

reads stdout, parses the `result` field, and hands it to `grading_assist.py`
(R9), which validates the JSON against the rubric keys and retries once on a
malformed reply. One student per call, run through the §8 worker with a per-call
timeout and the same `threading.Event` cancel. **Billing and auth are the
grader's existing Claude Code login / subscription — the tool never holds a key
and never resells access.** No in-app OAuth, no `token.json` lifecycle.

Provider A (Console API key via the `anthropic` SDK, key in the OS keyring) stays
in the code as an *un-promoted* "advanced" seam; `config.yaml` carries only
`ai_provider: claude_cli | api_key | none` (default `claude_cli`).

---

## 2. Observed `claude -p … --output-format json` shape (real probe)

Command actually run in this repo:

```
claude -p "ok" --output-format json --model claude-opus-5
```

- **Exit code:** `0`.
- **stdout:** a single-line JSON object. Fields relevant to Provider B:

  | field | observed value / type | use |
  |---|---|---|
  | `type` | `"result"` | sanity check |
  | `subtype` | `"success"` | success gate |
  | `is_error` | `false` (bool) | success gate |
  | `result` | `"…"` (string — the model's answer text) | **this is what `grading_assist` parses** |
  | `stop_reason` | `"end_turn"` | — |
  | `num_turns` | `1` | — |
  | `session_id` | uuid | — |
  | `total_cost_usd` | `0.43` for this trivial call (cache-creation of the CLI's own system prompt + any `CLAUDE.md` in cwd — real grading calls land in a similar band) | cost caveat, surface in UI |
  | `usage` | `{input_tokens, output_tokens, cache_*}` | optional telemetry |
  | `modelUsage."claude-opus-5"` | `{canonicalModel:"claude-opus-5", provider:"firstParty", …}` | **confirms `--model claude-opus-5` was accepted** |
  | `permission_denials` | `[]` | — |
  | `api_error_status` | `null` | error branch |

- **stderr:** one non-fatal line —
  `Ignoring N permissions.allow entries … this workspace has not been trusted`.
  Harmless for a `-p` call that uses no tools, but see caveat (c).

## 3. `--model` acceptance

`--model claude-opus-5` accepted; `modelUsage` keyed by `claude-opus-5`,
`canonicalModel: "claude-opus-5"`, `provider: "firstParty"`. Matches the model
the plan and the `claude-api` skill specify. No date suffix.

## 4. Docs / policy check

- **`code.claude.com/docs/en/authentication`** (fetched 2026-09-10): headless
  **`-p` mode is a documented first-class feature** ("In non-interactive mode
  (`-p`), the key is always used when present"). `claude setup-token` exists
  expressly "for CI pipelines, scripts, or other environments where interactive
  browser login isn't available" → Anthropic sanctions scripted/automated
  invocation of the CLI. Nothing restricts a local tool from shelling out to the
  user's own `claude`.
- **Anthropic Usage Policy** (`anthropic.com/legal/aup`, fetched 2026-09-10): no
  clause prohibits an individual driving their **own** logged-in `claude` for
  their **own** work. Prohibitions are about multi-account abuse, ban evasion,
  region circumvention, and training a model on outputs — none apply here. The
  tool does **not** provide/resell Claude access to third parties (each grader
  runs their own CLI on their own machine with their own login).
- Conclusion (for the human to confirm): programmatic `claude -p` for this
  use — a single grader's local grading assistant, their subscription, their
  machine — is within documented, supported usage as of 2026-09-10.

## 5. Caveats to carry into P4 code

a. **Latency & cost** — a `-p` call is slower than a bare API call and each
   carries the CLI's own system-prompt cache-creation cost on a cold cache
   (~$0.1–0.5 seen). Surface "أبطأ من نداء API مباشر" in the AI panel; grade one
   student per call; make the batch cancellable between students.
b. **No structured-output guarantee** — `result` is free text. `grading_assist`
   must extract the JSON object, `json.loads` it, validate every rubric key is
   present, and retry **once** on failure, then fall back to an error sentinel
   (no exception leak).
c. **cwd / `CLAUDE.md` bleed** — `claude -p` run inside a project dir picks up
   that dir's `CLAUDE.md` (the probe's `result` referenced this repo's build
   state). P4-U4 must run the subprocess with a **controlled `cwd`** (e.g. a temp
   dir, or the assignment folder deliberately) so the grader's intent — not a
   stray `CLAUDE.md` — sets the context. Consider `--strict-mcp-config` /
   minimal env to keep the call hermetic.
d. **"workspace not trusted" stderr** — non-fatal here; confirm it stays
   non-fatal when the cwd is a fresh temp dir (it should — no `.claude/settings`
   there).
e. **`provider_status()`** — `shutil.which("claude")` for installed; a cheap
   `claude -p "ok"` (or its status output) for logged-in. Timeout it.
f. **Timeout / kill** — per-call timeout in the worker; on timeout
   `proc.kill()` must touch only the subprocess (its own process group).

## 6. Model / API notes (from the `claude-api` skill, 2026 cache)

- Model id: **`claude-opus-5`** exactly (no date suffix). Current default.
- If Provider A is ever exercised: `anthropic` SDK, `client.messages.stream(...)`
  + `get_final_message()`; rubric prefix in `system` with
  `cache_control:{"type":"ephemeral"}`; **do not** send `budget_tokens` (400 on
  Opus 5) — use `output_config:{effort:…}` / adaptive thinking. Prefill is
  removed on Opus 5 (400) — use `output_config.format` or a system instruction
  for JSON shape.

---

## 7. Human sign-off  — REQUIRED before P4-U2

> I have read §§1–6. Programmatic `claude -p --output-format json` on my own
> Claude subscription, for this tool's grading-assist feature, is acceptable to
> me and (to my knowledge) within Anthropic's current terms. Proceed with
> Phase 4 (Provider B).

- Name: **Mostafa Swaisy** (mostafa, the grader)
- Date: **2026-09-10**
- Signature / "approved" in commit message: **approved** — given in-session on
  2026-09-10 ("Approved — build Phase 4"), recorded in this commit.

**→ Phase 4 (Provider B) is UNBLOCKED as of 2026-09-10. P4-U2…U6 may proceed.**

_`feat/gui-phase3` remains code-complete and shippable without any of Phase 4
(spec §8 criterion 3 met at P3-U7 without AI)._

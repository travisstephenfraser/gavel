# AgentGrade

AgentGrade is a quality gate for AI-generated code.

It evaluates code across four dimensions using a primary and audit model, reconciles confidence, generates executable remediation instructions, and supports an in-app closed loop for fix + re-evaluation.

## What It Does

Closed loop:

`Agent writes code -> AgentGrade evaluates -> remediation prompt generated -> autofix candidate generated -> re-evaluate -> score deltas`

Core dimensions (exactly four):

1. Correctness
2. Security
3. Readability
4. Robustness

## Architecture

```text
USER INPUT (code + language)
        |
        v
POST /evaluate
  - create eval_runs row (status=running)
  - run 8 model evals in parallel (4 dimensions x 2 models)
      - Primary evaluator (default): gpt-5.4
      - Audit evaluator (default): gpt-5-mini
  - reconcile per-dimension confidence by score gap
  - persist dimension_scores rows
  - generate remediation report + agent_prompt
  - update eval_runs (overall_score, audit_agreement, remediation_json, agent_prompt, status=completed)
        |
        v
GET /results/<id>
  - scorecard + remediation + print/PDF report
  - Fix & Re-evaluate -> prefilled re-eval flow with optional autofix candidate
        |
        v
GET /history
  - past runs with score indicators and quick actions
```

## Evaluation Strategy

- Code is line-numbered before model evaluation (`add_line_numbers`) for line-level findings.
- All model calls request structured JSON:
  - `response_format={"type": "json_object"}`
- Parallel execution uses `ThreadPoolExecutor(max_workers=8)`.
- Fail-soft behavior:
  - if a model call fails, score is `None` and the run still completes.

## Reconciliation Rules

- Final displayed score per dimension = **primary score**.
- Confidence:
  - gap `0` -> `HIGH`
  - gap `1` -> `MEDIUM`
  - gap `>=2` -> `LOW`
- `overall_score` = average of available primary scores (skips `None`).
- `audit_agreement` = percentage of dimensions where gap `<=1`.

## Model Configuration

Defaults are env-configurable:

- `PRIMARY_MODEL` (default `gpt-5.4`)
- `AUDIT_MODEL` (default `gpt-5-mini`)
- `REMEDIATION_MODEL` (default `PRIMARY_MODEL`)
- `AUTOFIX_MODEL` (default `AUDIT_MODEL`)

Reliability fallbacks are built in:

- `PRIMARY_FALLBACK_MODEL` (default `gpt-4o`)
- `AUDIT_FALLBACK_MODEL` (default `gpt-4o-mini`)
- `REMEDIATION_FALLBACK_MODEL` (default `gpt-4o`)
- `AUTOFIX_FALLBACK_MODEL` (default `gpt-4o-mini`)

If the primary configured model fails, AgentGrade automatically attempts the fallback model before returning an eval failure.

## UX Features

### 1) Scorecard + Remediation (`/results/<id>`)

- Overall score + audit agreement (<=1 gap)
- Per-dimension cards with primary/audit score + confidence
- Remediation issue cards sorted by severity
- `Copy Agent Prompt` button
- `Print to PDF` button (diagnostic-style print layout)

### 2) In-App Fix & Re-evaluate

- `Fix & Re-evaluate` button on results page
- Supports `auto_fix=1` mode:
  - generates candidate fixed code from prior `agent_prompt`
  - prefills re-eval `code_input`
- Re-eval run is linked via `previous_eval_run_id`
- Results page shows side-by-side score deltas

### 3) History Dashboard (`/history`)

- Recent runs as cards with:
  - timestamp, language, status
  - overall score indicator bar
  - audit agreement badge
- Quick actions per run:
  - `View Scorecard`
  - `Fix & Re-evaluate`

### 4) Print/PDF Diagnostic Report

The results page includes a print-only report layout that mirrors a formal diagnostic report style, including:

- executive summary stats
- evaluator setup (primary vs audit model)
- process flow
- high-level architecture table
- dimension score table
- remediation plan table

## Tech Stack

- Flask
- SQLite
- OpenAI Python SDK
- Tailwind CSS CDN

## Project Structure

```text
app.py                    Flask routes and orchestration
database.py               SQLite schema + helpers
evaluator.py              run_eval(code, dimension, model, role)
reconciler.py             score gap/confidence + aggregate metrics
remediator.py             remediation synthesis
autofixer.py              candidate fix generation from agent_prompt
prompts.py                evaluator/audit/remediation prompt templates
env_loader.py             lightweight .env loader
templates/index.html      code input + re-eval prefill UX
templates/scorecard.html  scorecard + remediation + print report
templates/history.html    run history dashboard
test_samples/             demo samples (good, sql_injection, messy, no_error_handling)
```

## Database Schema

Two core tables:

- `eval_runs`
  - run metadata, overall metrics, remediation payload, status
  - includes `previous_eval_run_id` for linked re-evals
- `dimension_scores`
  - per-dimension primary/audit scores, justifications, findings, confidence, score gap

See `database.py` for exact `CREATE TABLE` definitions.

## Routes

- `GET /`
  - input form
  - optional re-eval prefill via `from_run_id`
  - optional autofix generation via `auto_fix=1`
- `POST /evaluate`
  - executes full pipeline and redirects to results
- `GET /results/<id>`
  - scorecard, remediation, print report, re-eval delta view
- `GET /history`
  - list past runs with quick actions

## Running Locally

```powershell
cd c:\Users\tfras\CODEX\AgentGrade
.\.venv\Scripts\python -m flask --app app run --debug
```

Open: `http://127.0.0.1:5000`

## Environment Setup

`.env` (loaded by `env_loader.py`):

```env
OPENAI_API_KEY=your_key_here
PRIMARY_MODEL=gpt-5.4
AUDIT_MODEL=gpt-5-mini
REMEDIATION_MODEL=gpt-5.4
AUTOFIX_MODEL=gpt-5-mini
PRIMARY_FALLBACK_MODEL=gpt-4o
AUDIT_FALLBACK_MODEL=gpt-4o-mini
REMEDIATION_FALLBACK_MODEL=gpt-4o
AUTOFIX_FALLBACK_MODEL=gpt-4o-mini
```

## Demo Notes

Best live sample for dramatic improvement: `test_samples/sql_injection.py`.

Recommended sequence:

1. Evaluate vulnerable code
2. Show low security score + remediation
3. Click `Fix & Re-evaluate` (autofix prefill)
4. Re-evaluate updated code
5. Show improvement panel + score deltas
6. Show `/history` to prove persistence and repeatability

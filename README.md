# AgentGrade

AgentGrade is a quality gate for AI-generated code.

It runs a dual-model evaluation across four dimensions, reconciles agreement/confidence, and generates a remediation prompt that can be fed back into a coding agent.

## What It Does

Closed loop:

`Agent writes code -> AgentGrade evaluates -> remediation prompt generated -> agent fixes code -> re-evaluate`

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
      - Primary model: gpt-4o
      - Audit model: gpt-4o-mini
  - reconcile per-dimension confidence by score gap
  - persist dimension_scores rows
  - generate remediation report + agent_prompt
  - update eval_runs (overall_score, audit_agreement, remediation_json, agent_prompt, status=completed)
        |
        v
GET /results/<id>
  - render scorecard + remediation + print-friendly PDF report layout
```

### Evaluation Strategy

- Code is line-numbered before model evaluation (`add_line_numbers`) for line-level findings.
- All model calls use structured output:
  - `response_format={"type": "json_object"}`
- Parallel execution uses `ThreadPoolExecutor(max_workers=8)`.
- Failure handling is fail-soft:
  - if a model call fails, score is `None` with justification like `Eval failed: ...`
  - the run still completes and renders.

### Reconciliation Rules

- Final displayed score per dimension = **primary score**.
- Confidence:
  - gap `0` -> `HIGH`
  - gap `1` -> `MEDIUM`
  - gap `>=2` -> `LOW`
- `overall_score` = average of available primary scores (skips `None`).
- `audit_agreement` = percentage of dimensions where gap `<=1`.

## Tech Stack

- Flask
- SQLite
- OpenAI Python SDK
- Tailwind CSS CDN (UI)

## Project Structure

```text
app.py                  Flask routes and orchestration
database.py             SQLite schema + CRUD helpers
evaluator.py            run_eval(code, dimension, model)
reconciler.py           score gap/confidence + aggregate metrics
remediator.py           remediation synthesis
prompts.py              evaluator/audit/remediation prompt templates
env_loader.py           lightweight .env loader (no extra dependency)
templates/index.html    code input form
templates/scorecard.html scorecard UI + print/PDF report layout
test_samples/           demo samples (good, sql_injection, messy, no_error_handling)
```

## Database Schema

Two core tables:

- `eval_runs`
  - run metadata, overall aggregates, remediation payload, status
- `dimension_scores`
  - per-dimension primary/audit scores, justifications, findings, confidence, score gap

See `database.py` for exact `CREATE TABLE` definitions.

## Routes

- `GET /`
  - Render input form (`code_input`, `language`)
- `POST /evaluate`
  - Execute full pipeline and redirect to results
- `GET /results/<id>`
  - Render scorecard, remediation report, and print-ready report layout

## Running Locally

```powershell
cd c:\Users\tfras\CODEX\AgentGrade
.\.venv\Scripts\python -m flask --app app run --debug
```

Open: `http://127.0.0.1:5000`

### Environment Variables

Set in `.env` (loaded by `env_loader.py`):

```env
OPENAI_API_KEY=your_key_here
```

## Demo Notes

Best live sample for dramatic improvement: `test_samples/sql_injection.py`.

Recommended flow:

1. Evaluate vulnerable code
2. Show low security score + remediation instructions
3. Apply fix (parameterized query + error handling)
4. Re-evaluate and show score improvement


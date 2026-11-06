# Equal Start

**Find U.S. undergraduate scholarships and funded experiences, understand the requirements, and turn an opportunity into an application plan.**

Students without a professional network or money to cover upfront expenses can miss opportunities they are qualified to pursue. Equal Start brings discovery, source-linked requirements, financial barriers, and application preparation into one place.

The app combines a custom Streamlit interface with predictable eligibility rules and four specialist AI agents. It currently includes **20 reviewed U.S. opportunities**, covering scholarships, transfer funding, and funded research experiences. Some archived cycles are retained to demonstrate deadline handling.

[Quick start](#quick-start) · [How it works](#how-it-works) · [Agent evaluations](#agent-evaluations) · [Project structure](#project-structure) · [Contributing](#contributing)


## Phase 2: evidence to action

**Free demo hosting:** deploy `streamlit_app.py` from branch `deploy/streamlit-community-cloud` on [Streamlit Community Cloud](https://share.streamlit.io/), selecting Python 3.12. Saved plans are separate for each browser session and can be downloaded; session loss or a restart clears them. Provider keys belong in private Streamlit secrets. See [deployment instructions](docs/STREAMLIT_DEPLOYMENT.txt) for configuration and budget/storage limits. This repository includes deployment preparation; a hosted URL is not yet verified.

The recommendation experience now connects research, evidence, and preparation:

- **A focused shortlist and comparison:** up to three selected opportunities, a separate catalog view, side-by-side funding/housing/travel checks, and clear unresolved conditions.
- **Bounded tool use:** Discovery can propose search, fetch, clarify, or finish. Code validates actions and reviewed URLs. Each matching run permits at most two searches, three fetch attempts, and one optional clarification; answering starts another run and can reuse source receipts.
- **Evidence with exact citations:** official source text is timestamped and cached for six hours. Evidence selects numbered passages; code copies their exact text. Missing decisive evidence can trigger one additional approved-source fetch within the same three-fetch cap.
- **Uncertainty passed downstream:** Fit receives unresolved evidence topics and assessment status. The reviewed catalog and hard eligibility outcomes stay intact.
- **Preparation without an existing network:** suggested dates/dependencies and editable funding, reference, and nomination questions help students take the next step. No messages are sent automatically.
- **Inspectable execution:** sanitized tool actions, stop reasons and source IDs can be exported. Model costs are attributed to request IDs so concurrent runs cannot contaminate per-run cost figures.

The expanded 38-case regression suite passes Discovery 27/27, Evidence 30/30, Fit 30/30 and Planning 27/27 over three repeats. The six teammate-added cases are preserved alongside the original 32. The additional Phase 2 suite passes 15/15 per role over three repeats, with 100% contract validity. It covers tool decisions, grounding and existing Fit/Planning regression scenarios. Fit/Planning examples intentionally reuse earlier cases; all remain AI-assisted development data.

Seven controlled synthetic journeys compare the full workflow, an all-local comparator, and each role disabled individually. The full workflow passed 7/7; the local comparator passed 4/7; each single-role-disabled variant passed 6/7. These are single runs on constructed cases, not independent user validation, statistical significance, or proof that four agents are always required. Inspect the per-case failures and cost/latency tradeoffs before generalizing.

```powershell
# New role contracts and quality cases, paired with local comparators.
.\.venv\Scripts\python.exe -m evals.phase2 --live --repeats 3 --max-cost 0.5
# Seven journeys: full workflow, local comparator, and one role disabled at a time.
.\.venv\Scripts\python.exe -m evals.journeys --live --max-cost 0.5
```

See [Phase 2 results and limitations](docs/PHASE2_RESULTS.txt), [role evaluation receipts](docs/evals/), and [journey experiments](docs/experiments/). Live commands use the existing cumulative ledger. Full interrupted-graph recovery and independently reviewed student validation remain future work; source caching is not full execution checkpointing.

## What students can do

- Describe a goal and optionally add details such as year of study, institution type, GPA, and citizenship or residency.
- Explore opportunities with clear eligibility outcomes, application dates, funding evidence, and source links.
- Identify reimbursement delays, housing gaps, and other costs before committing to an experience.
- Build a source-linked checklist, track preparation, and download a plan as JSON or Markdown.

**Example:** A community-college student wants a funded research experience but cannot pay for travel upfront. Equal Start screens recorded requirements, prioritizes relevant options, and surfaces reimbursement or housing concerns. The student can then confirm unresolved conditions with the provider and prepare the required documents.

## Quick start

Python 3.13 was used for the verified build. Run these commands from the repository root.

### Windows PowerShell

```powershell
git clone https://github.com/vineelad/equalstart.git
cd equalstart
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m streamlit run app.py
```

### macOS or Linux

```bash
git clone https://github.com/vineelad/equalstart.git
cd equalstart
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
cp .env.example .env
.venv/bin/python -m streamlit run app.py
```

Open **http://127.0.0.1:8501**. Select **Try Maya's sample profile** for a fictional student journey that works without model credentials. The sample uses explicitly labeled local matching.

Create `.env` only once; preserve an existing configured file. On Windows, subsequent launches can use `./run.ps1`.

### Enable live services

Edit your local `.env` with your own provider keys:

| Setting | Purpose |
| --- | --- |
| `FIREWORKS_API_KEY` | Enables structured model calls for the four specialist roles. |
| `KEENABLE_API_KEY` | Enables authenticated opportunity search and source retrieval. |
| `FIREWORKS_MODEL` | Defaults to `accounts/fireworks/models/gpt-oss-120b`. |
| `INFERENCE_BUDGET_USD` | Sets the cumulative inference cap for this local database, up to $15. |
| `FIREWORKS_INPUT_PER_MILLION`, `FIREWORKS_OUTPUT_PER_MILLION` | Optional for the default model, which has built-in rates; required for custom models. |

Optional Nebius support from the team is preserved. Set `LLM_PROVIDER=nebius` and configure `NEBIUS_API_KEY`, `NEBIUS_MODEL`, and both verified `NEBIUS_INPUT_PER_MILLION` / `NEBIUS_OUTPUT_PER_MILLION` rates. Fireworks remains the default. The Phase 2 grounding contracts were live-tested with Fireworks; the [retained Nebius report](docs/evals/NEBIUS_EVALUATION_SUMMARY.md) covers the earlier summary/permutation contracts.

Restart after changing provider settings. Open **How it works → Demo settings** to inspect live-mode settings and budget usage, then submit your own profile from Explore. Keys remain server-side and `.env` is ignored by Git.

## How it works

This walkthrough contains the eight flows from the team's diagram handout. Each section explains a part of the implemented system and includes its full diagram.

**Diagram resources:** [PDF handout](docs/diagrams/equalstart-flow-diagrams.pdf) · [Offline viewer](docs/diagrams/index.html) · [Editable Mermaid sources and SVGs](docs/diagrams/). Download the repo and open the HTML viewer locally to browse offline or print. In the diagrams, solid arrows show execution or data movement, dotted arrows show optional connections or controls, and cylinders indicate local storage.

### 1. Student journey

Start with a goal or the fictional sample, explore the reviewed catalog, inspect a record, and build an application checklist. Students can filter results and revisit saved plans. Submission takes place through the official provider portal.

```mermaid
flowchart LR
    A[Goal and optional profile] --> B[Screen and prioritize opportunities]
    B --> C[Review requirements, evidence and costs]
    C --> D[Build and track a checklist]
    D --> E[Export plan]
    E --> F[Student applies through provider portal]
```

<details>
<summary>View the full student journey</summary>

![Student journey from profile entry to external application submission](docs/diagrams/01-student-journey.svg)

</details>

### 2. System architecture and data boundaries

The Streamlit app validates the student's input and loads the reviewed JSON catalog. Python rules assess eligibility, dates, and financial barriers. LangGraph coordinates matching, while Fireworks provides structured model responses and Keenable provides search and source retrieval.

| Component | Responsibility |
| --- | --- |
| Streamlit + custom CSS | Explore, opportunity details, saved plans, and workflow visibility. |
| Pydantic | Validate profiles, catalog records, and model output schemas. |
| Python rules | Determine recorded eligibility outcomes, cycle status, financial barriers, and local relevance scores. |
| LangGraph | Coordinate matching, bounded tool actions, optional clarification, and one evidence-driven follow-up with shared state. |
| Fireworks | Run the bounded specialist prompts using an open-weight model. |
| Keenable | Search for separate web leads and retrieve approved provider URLs. |
| SQLite | Persist checklist state, concise stage metadata, and cumulative cost reservations. |

Profiles remain in session memory. Fireworks receives the context needed for each role; Keenable discovery receives a broad discipline query. Saved plans contain opportunity IDs, checklist content/order, and completion state rather than a full student profile.

<details>
<summary>View the system and data boundaries</summary>

![System components, external provider connections, and local storage boundaries](docs/diagrams/02-system-and-data-boundaries.svg)

</details>

### 3. The four agents and their handoffs

Matching begins with deterministic checks across the catalog. Known failures and closed cycles are excluded from agent inputs; up to 12 candidates proceed to the graph.

```mermaid
flowchart TD
    A[Profile and reviewed catalog] --> B[Local rules and candidate screening]
    B --> C[Discovery]
    C --> R[Bounded research and optional clarification]
    R --> D[Evidence: source passage judgments]
    D --> Q{One useful reviewed-source follow-up?}
    Q -->|Yes, at most once| R2[Fetch approved source]
    R2 --> D
    Q -->|No| E[Fit]
    E --> F[Explore results and select an opportunity]
    F --> G[Planning]
    G --> H[Source-linked application checklist]
```

| Agent | What it receives | What it returns | Boundary |
| --- | --- | --- | --- |
| **Discovery** | Goal, reviewed candidates, optional leads, and bounded research state. | Relevant catalog IDs and a validated next research action. | Fetches are restricted to reviewed URLs; web leads cannot become reviewed recommendations. |
| **Evidence** | Reviewed claims and numbered passages from official source receipts. | Supported, Contradicted, or Not found findings with source and passage references. | Code copies exact source text. A cited passage does not establish complete eligibility. Without receipts, the role uses labeled summary clarity screening. |
| **Fit** | Goal, cost/housing constraints, candidate scores, barriers, and evidence uncertainty. | Every selected opportunity ID, reordered. | Cannot override hard eligibility results or change the candidate set. |
| **Planning** | A selected opportunity's published materials. | Every material index in a preparation order. | Cannot invent or remove published requirements. |

The LangGraph workflow includes conditional research and one evidence-driven follow-up around Discovery, Evidence, and Fit. Planning runs separately on selection. The default shortlist shows up to three selected options; Browse reviewed catalog retains the broader rule outcomes. An empty Discovery selection stays an empty recommendation set.

Without live inference, Discovery keeps screened candidates, Evidence adds no model flags, Fit uses local scores, and Planning keeps source order. A model or validation failure records a visible **Fallback** event and retains the corresponding local result. Valid empty inputs do not make model calls.

<details>
<summary>View the full matching graph and agent handoffs</summary>

![Matching graph, validation controls, fallback behavior, and separate Planning specialist](docs/diagrams/03-matching-graph-and-agent-handoffs.svg)

</details>

### 4. Eligibility, dates, and financial fit

Eligibility uses three outcomes so missing information stays visible:

| Outcome | Meaning |
| --- | --- |
| **Not eligible** | At least one known recorded requirement is not met. |
| **Needs confirmation** | A profile detail is missing or an additional provider condition remains unresolved. |
| **Screened criteria met** | All modeled checks pass and no recorded confirmation item remains. |

Cycle status is evaluated separately using available dates and timezones. A date-only deadline retains uncertainty about the closing time. Known failures and closed cycles are excluded from the default results view.

Financial fit includes payment timing and housing. Reimbursed travel can still require upfront money, and unknown costs remain uncertain. The local relevance score combines goal fit (up to 40), funding evidence (30), known criteria (20), and constraints (10). It is a prioritization heuristic, not an acceptance probability.

<details>
<summary>View the eligibility and relevance flow</summary>

![Rule outcomes combined with cycle status, cost barriers, and heuristic relevance](docs/diagrams/04-eligibility-cycle-handling-and-relevance.svg)

</details>

### 5. Source provenance and review

The reviewed catalog is built from official provider pages. Each claim carries a source URL, topic, and review date. Reviewed summaries and rules are validated before they appear as opportunity records.

Keenable search returns up to five separate, **unverified leads**. Source refresh retrieves text from an approved HTTPS provider URL for inspection. Neither search nor refresh silently changes catalog facts; a manual review is required before new facts enter the catalog. Extracted text can omit page sections, so complete conditions still need confirmation with the provider.

<details>
<summary>View the source review and catalog flow</summary>

![Official source review, validated catalog creation, source refresh, and separate unverified leads](docs/diagrams/05-source-provenance-and-review.svg)

</details>

### 6. Model validation, spending controls, and fallback

Every model request uses a role-specific JSON schema. Returned references must belong to the supplied input and contain no duplicates. Discovery and Evidence can select subsets; Fit and Planning must preserve every input reference exactly once.

Before sending a request, the app estimates a conservative cost and reserves it in an atomic SQLite transaction. If the reservation exceeds the remaining budget, the request is blocked and the stage uses its local fallback. Returned token usage settles the estimate; missing usage or an ambiguous network failure retains the reservation.

The application cap is cumulative for calls recorded in that database, including evaluations, and cannot exceed **$15**. It cannot track other machines or applications on the provider account. Clearing saved plans preserves the ledger; deleting the database loses its usage history. Keenable credits are separate from the inference ledger.

<details>
<summary>View the model request, budget, and fallback flow</summary>

![Empty-input guard, atomic budget reservation, provider call, output validation, and fallback paths](docs/diagrams/06-model-contract-spending-controls-and-fallback.svg)

</details>

### 7. Planning and saved progress

For a selected opportunity, Planning orders explicit zero-based material indices. The app checks that every original index appears exactly once, then builds tasks using the unchanged requirement text and source links. If the model fails, the published source order is preserved.

General preparation steps—rechecking eligibility, confirming costs, and reviewing before submission—are labeled separately from published requirements. Suggested dependencies are validated, and suggested preparation dates are added only when a future deadline is known; these dates are not provider requirements. Editable provider-question, reference-request and nomination-support drafts help students ask for support. Students review and send drafts themselves. SQLite preserves the checklist and completed task IDs.

<details>
<summary>View planning and persistence</summary>

![Material ordering, checklist validation, saved state, export, and saved-plan clearing](docs/diagrams/07-planning-and-local-persistence.svg)

</details>

### 8. Evaluation and evidence

Each specialist has a dedicated quality evaluation suite using the **same production prompts, schemas, and identifier guards** as the app. Expected labels are kept out of model requests, and deterministic graders compare outputs against those labels.

The current suite contains 38 synthetic development cases: Discovery 9, Evidence 10, Fit 10 and Planning 9. With three repeats, it records 114 live-mode case results and 114 local-baseline results. The live side makes 102 model calls; 12 cases exercise empty-input guards. Historical 32-case runs remain available.

<details>
<summary>View the evaluation flow</summary>

![Fixed labeled cases, paired baseline and production runs, deterministic grading, gates, and exported evidence](docs/diagrams/08-evaluation-and-course-evidence.svg)

</details>

## Agent evaluations

| Agent | Task-quality check | Recorded final live result |
| --- | --- | --- |
| Discovery | Relevant-ID precision and recall of at least 0.80 per case. | 27/27 cases passed. |
| Evidence | Ambiguity-flag F1 of at least 0.80 per case. | 30/30 cases passed. |
| Fit | All labeled preference pairs correctly ordered, with every candidate preserved. | 30/30 cases passed. |
| Planning | All labeled prerequisite pairs correctly ordered, with every material preserved. | 27/27 cases passed. |

Each live agent must achieve **100% contract validity** and **at least 90% task-case passes** to pass its gate. The recorded final run met both gates for every agent. Contract failures count as failed cases. The runner also records latency, cost, diagnostic quality metrics, and repeat stability.

These are small synthetic development cases used during prompt refinement. The results demonstrate behavior on that regression suite; they do not establish held-out real-world accuracy or scholarship selection outcomes. Earlier failed runs are retained alongside the final run.

See the [evaluation guide](evals/README.txt), [recorded final report](docs/evals/20261106T032951000782Z/REPORT.txt), and [all run artifacts](docs/evals/). Download the repo to open the standalone HTML dashboards in a browser.

### Run checks locally

```powershell
# Development dependencies and deterministic tests; no live inference required.
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock.txt
.\.venv\Scripts\python.exe -m pytest -q

# Baseline evaluation only; no inference charges.
.\.venv\Scripts\python.exe -m evals.runner

# Paired live and baseline evaluation; requires configured model access.
.\.venv\Scripts\python.exe -m evals.runner --live --repeats 3 --max-cost 1
```

Use `.venv/bin/python` on macOS/Linux. The latest verified deterministic suite has **108 passing tests**. Live evaluations use the same cumulative budget ledger with the specified smaller run cap. Reports are written to a unique folder under `docs/evals/`; a failed live gate returns a nonzero exit code and still preserves its results.

## Project structure

```text
app.py                    Streamlit pages and student interactions
equalstart/
  workflow.py             Conditional matching graph and on-demand checklist planning
  research.py             Bounded tool controller and official source receipts
  readiness.py            Student-facing readiness from rule and evidence outcomes
  preparation.py          Suggested dependencies/dates and editable support drafts
  agents.py               Shared prompts, output schemas, and reference guards
  eligibility.py          Eligibility rules, cycle status, barriers, and scoring
  providers.py            Fireworks and Keenable clients
  schema.py               Pydantic models
  storage.py              SQLite plans, stage metadata, and budget ledger
  catalog.py              Catalog loading and validation
  design.css              Custom interface styling
data/opportunities.json   Reviewed opportunity records and evidence
evals/                    Fixed cases, deterministic graders, and evaluation runner
tests/                    Rule, contract, storage, and UI regression checks
docs/diagrams/            Flow diagrams, offline viewer, and PDF handout
docs/evals/               Recorded evaluation runs and dashboards
docs/experiments/         Synthetic journeys and one-role-disabled comparisons
docs/experiments/         Synthetic journeys and one-role-disabled comparisons
docs/experiments/         Synthetic journeys and one-role-disabled comparisons
docs/experiments/         Synthetic journeys and one-role-disabled comparisons
docs/experiments/         Synthetic journeys and one-role-disabled comparisons
docs/experiments/         Synthetic journeys and one-role-disabled comparisons
docs/experiments/         Synthetic journeys and one-role-disabled comparisons
scripts/                  Catalog seeding, source refresh, and browser checks
```

## Contributing

Fork the repository, create a branch, and open a pull request against `main`. Include what changed, why it helps students, and the checks you ran.

- **Catalog changes:** confirm facts on the official provider page, update source links and review dates, and preserve uncertainty where conditions are incomplete. `scripts/seed_catalog.py` rebuilds the catalog; `scripts/refresh_sources.py` retrieves reviewed URLs for inspection.
- **Agent changes:** run contract tests and the relevant evaluations. Preserve prior results so reviewers can compare behavior. Live checks incur inference usage.
- **UI changes:** exercise the profile → results → details → checklist journey. `scripts/browser_check.py` supports browser checks with a running local server and installed Microsoft Edge.

Keep keys and personal data in local ignored files. Read the `.env.example` template for supported configuration.

## Current limits and deployment

Equal Start is a **single-user local demo**. The reviewed catalog is limited, eligibility modeling is incomplete, and provider conditions and cycles can change. A student passing the recorded checks may still need to satisfy additional conditions. The app prepares a plan; students verify the complete requirements and submit through the official portal.

For a Python-capable host, install the locked dependencies, configure secrets server-side, provide persistent SQLite storage, and launch Streamlit on the host-assigned port. Before shared personal use, add authentication and storage isolation per user. The repository does not include a hosted deployment.

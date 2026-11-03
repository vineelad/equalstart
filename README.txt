EQUAL START
USA-only undergraduate scholarships and funded experiences.
Custom Streamlit UI, deterministic eligibility checks, and four bounded agent
roles: Discovery, Evidence, Fit, and Planning. Matching uses three sequential
LangGraph nodes; Planning runs when a student builds a checklist.

LOCAL SETUP (Windows; verified with Python 3.13)
  python -m venv .venv
  .\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
  Copy-Item .env.example .env
  Edit .env locally with your own keys, then run:
  .\.venv\Scripts\python.exe -m streamlit run app.py
Open http://127.0.0.1:8501
On macOS/Linux use .venv/bin/python and cp instead of Copy-Item.
Works without keys using labeled local matching and the fictional sample.

PROVIDERS AND BUDGET
FIREWORKS_API_KEY enables structured inference; KEENABLE_API_KEY enables live
search and source retrieval. No configured keys are included in this repo.
The default model has built-in pricing; custom models need verified rates.
INFERENCE_BUDGET_USD can reduce the app's cumulative cap of $15.
SQLite reserves cost before requests. Unknown billed usage retains its reservation.
Existing checkout usage history is local and is not included in this snapshot.
A fresh clone cannot observe spending on other machines or by other apps.
Set a smaller cap or use local mode if continuing an existing total budget.

TESTS AND AGENT EVALUATIONS
  .\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock.txt
  .\.venv\Scripts\python.exe -m pytest -q
  .\.venv\Scripts\python.exe -m evals.runner --live --repeats 3 --max-cost 1
Live evals spend from the same cumulative local ledger, with a smaller run cap.
See evals/README.txt and docs/evals/ for per-agent results, cases, fingerprints,
costs, baselines and dashboards. All four agents have dedicated evals.
Recorded final results are 24/24 per role on synthetic development cases.
These cases were used for prompt refinement; they are not held-out accuracy.

TEAM DIAGRAMS
Open docs/diagrams/index.html locally. It works offline and supports Print to PDF.
Eight editable .mmd diagrams and rendered SVGs cover the student journey,
architecture, agent handoffs, eligibility, source review, budget, planning and evals.

LIMITATIONS AND DEPLOYMENT
20 reviewed real USA opportunities, including archived cycles; not a complete
directory. Missing conditions need provider confirmation. Relevance is not an
acceptance probability. Search leads remain unverified and separate.
Applications are submitted by students through official provider portals.
Local SQLite saved state is for a single-user demo; profiles stay session-local.
For a Python host: install locked requirements, configure server-side secrets,
provide persistent SQLite storage, and run Streamlit on the host-assigned port.
Add authentication and per-user storage isolation before shared personal use.
No public deployment is included.

PUBLICATION SCOPE
This is a clean source snapshot, excluding Markdown planning files, original Git
history, credentials, local databases, virtual environments, raw source receipts,
screenshots and build artifacts. The full working checkout remains local.

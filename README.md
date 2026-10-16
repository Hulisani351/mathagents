# MathAgents

A Streamlit mathematics workspace with a real single-agent solver, a custom multi-agent team, complete expandable solution stages, session history, and a transparent research snapshot.

The September 27 Beta adds Compare for saved answers to the same question and model, and optional session-only feedback with download and deletion. Compare consumes no extra API calls. Feedback is self-reported usability evidence and does not measure mathematical accuracy. Download both solutions before closing the browser.

## Run locally

Use Python 3.12. In this folder:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .streamlit\secrets.example.toml .streamlit\secrets.toml
# Edit secrets.toml privately, then:
.venv\Scripts\python -m streamlit run streamlit_app.py
```

## Deploy on Streamlit Community Cloud

1. Put the contents of this `MathAgents` folder in a GitHub repository named `mathagents`.
2. Sign in at https://share.streamlit.io/ and choose **Create app**.
3. Select that repository, branch `main`, entry point `streamlit_app.py`.
4. Under Advanced settings select Python 3.12 and paste the private values described in `.streamlit/secrets.example.toml` into Secrets.
5. Deploy. Check both solving approaches and the research page before sharing the assigned `.streamlit.app` URL.

If the repository contains the enclosing folder, use `MathAgents/streamlit_app.py` as the entry point. The dependency file sits beside the app.

The interface works without secrets, but solving stays disabled until `ZAI_API_KEY` is configured. No presentation access code is required: visitors with the app link can use your provider allowance. Legacy `APP_ACCESS_PASSWORD` and `ALLOW_PUBLIC_USAGE` settings are ignored. Provider-processing consent, ten-second session spacing, and a process-local daily ceiling of 300 model requests remain in place. The ceiling resets on server restart and is not a billing-grade quota. Set provider-side spending limits before a public release.

## Architecture

`streamlit_app.py` handles user interaction. `services.py` validates requests, manages a shared cooldown and bounds provider retries. `engine/` contains copies of the frozen research pipelines with package-relative imports. `research/snapshot.json` contains aggregate data only. The public app does not run unattended research or silently fall back to a calculator.

## Privacy

Questions and proposals go to Z.ai only after the user selects the consent checkbox. No server-side notebook persists users' questions. Session memory retains up to 20 solutions and users can clear or download them. Hosting/provider operational logging is outside this application's control. Do not share secrets, private question data, `.env` files or raw experiment databases in the public repository.

## Tests

## Presentation reliability

Open **Presentation (saved)** before presenting. It replays two real, selected
Omni-MATH-Rule team outputs (one correction and one harmful change), clearly
marked as recorded rather than live. It makes no provider calls, but loading the
Streamlit website still requires internet. Download the examples as a backup.
Do not describe these selected cases as aggregate accuracy evidence.

Live traffic is serialized within this server process, with a two-second minimum
start spacing and a shared provider cooldown. A request makes at most three
attempts. Retry-After values are honored; long waits stop instead of retrying
early. Authentication, credit and documented account/plan restrictions do not
receive automatic retries. Other apps using the same provider account are not
coordinated by this process-local gate.

Successful stages are cached in browser-session memory (up to 60), keyed by the
account, model and full request. A retry can reuse a completed stage after its
partner failed, without sending it again. Reused stages are disclosed in the UI
and JSON export, and runtime is labelled as this attempt rather than fresh-model
runtime. Clearing the notebook also clears this cache; no shared cross-user
answer cache or durable user-question store is introduced.

No service can guarantee live provider availability. The recorded presentation
page is an explicit alternative, never a silent fallback. Prompts, model,
temperature, thinking setting, token limit and research evaluator are unchanged.
Provider error classifications: https://docs.z.ai/api-reference/api-code

### Run checks

```powershell
python -m unittest discover -s tests -v
```

## Research integrity

The dashboard identifies the snapshot date, measured model, denominators and limitations. It does not claim that model agreement proves mathematical correctness. The displayed results are interim and must not be described as a completed 2,500-question evaluation. The original research workspace is retained separately so that existing saved paths and checkpoints remain valid.

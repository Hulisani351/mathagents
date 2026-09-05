# MathAgents

A Streamlit mathematics workspace with a real single-agent solver, a custom multi-agent team, complete expandable solution stages, session history, and a transparent research snapshot.

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

The interface works without secrets, but solving stays disabled. A shared API key requires an access password by default. Setting `ALLOW_PUBLIC_USAGE = "true"` intentionally permits visitors to use your provider allowance. A process-local daily ceiling of 300 model requests limits accidental use, but resets on server restart and is not a billing-grade quota. Set provider-side spending limits before a public release.

## Architecture

`streamlit_app.py` handles user interaction. `services.py` validates requests, manages a shared cooldown and bounds provider retries. `engine/` contains copies of the frozen research pipelines with package-relative imports. `research/snapshot.json` contains aggregate data only. The public app does not run unattended research or silently fall back to a calculator.

## Privacy

Questions and proposals go to Z.ai only after the user selects the consent checkbox. No server-side notebook persists users' questions. Session memory retains up to 20 solutions and users can clear or download them. Hosting/provider operational logging is outside this application's control. Do not share secrets, private question data, `.env` files or raw experiment databases in the public repository.

## Tests

```powershell
python -m unittest discover -s tests -v
```

## Research integrity

The dashboard identifies the snapshot date, measured model, denominators and limitations. It does not claim that model agreement proves mathematical correctness. The displayed results are interim and must not be described as a completed 2,500-question evaluation. The original research workspace is retained separately so that existing saved paths and checkpoints remain valid.

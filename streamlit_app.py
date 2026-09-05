"""MathAgents: a useful mathematics workspace and transparent research companion."""
from pathlib import Path
import hmac
import json
import os
import time

import pandas as pd
import streamlit as st

from services import CloudClient, RequestGate, SolverError, solve_question

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="MathAgents | Mathematics, made clearer", page_icon="∑", layout="wide")
st.markdown("""<style>
.stApp {background:#f5f7fb;color:#142139}
.block-container {max-width:1280px;padding-top:2rem;padding-bottom:3rem}
h1,h2,h3 {letter-spacing:-.04em;color:#132440}
h1 {font-size:3.5rem!important;line-height:1.07!important;font-weight:750!important}
[data-testid="stSidebar"] {background:#10233f;color:#e7efff}
[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label {color:#e7efff!important}
[data-testid="stMetric"] {background:white;border:1px solid #dce4ee;border-radius:14px;padding:18px}
[data-testid="stMetricValue"] {color:#123c66}
[data-testid="stTextArea"] textarea {background:white;border:1px solid #b9c9dc;border-radius:12px;font-size:17px}
[data-testid="stButton"] button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primary"] {background:#087e76;border-color:#087e76;color:white;min-height:48px;font-weight:650;border-radius:10px}
[data-testid="stVerticalBlockBorderWrapper"] {border-radius:14px}
.eyebrow {color:#087e76;font-size:.82rem;font-weight:750;letter-spacing:.16em;text-transform:uppercase}
.intro {font-size:1.15rem;color:#51647b;max-width:680px;margin-bottom:2rem}
.brand {font-size:1.7rem;font-weight:750;letter-spacing:-.05em;margin-bottom:.2rem}
.subtle {color:#afc5df;font-size:.9rem}
@media(max-width:700px){h1{font-size:2.5rem!important}.block-container{padding-top:1rem}}
</style>""", unsafe_allow_html=True)


def setting(key, default=""):
    try:
        return str(st.secrets.get(key, os.getenv(key, default)))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return os.getenv(key, default)


@st.cache_resource
def request_gate():
    return RequestGate(daily_limit=300)


for key, default in {"history": [], "answer": None, "question": "", "last_request": 0.0}.items():
    if key not in st.session_state:
        st.session_state[key] = default

with st.sidebar:
    st.markdown('<div class="brand">∑ MathAgents</div><div class="subtle">Your mathematics workspace</div>', unsafe_allow_html=True)
    st.divider()
    page = st.radio("Workspace", ["Solve", "My session", "Research", "About"], label_visibility="collapsed")
    st.divider()
    st.caption("A direct solver when you want focus. An independent team when you want another check.")
    st.caption("Beta release · September 2026")


def show_result(result, key="current"):
    st.subheader("Your solution")
    with st.container(border=True):
        st.caption("FINAL ANSWER")
        st.markdown(result["final_answer"])
        st.caption(f"{result['model']} · {result['elapsed_seconds']:.1f} seconds · {result['mode']} workflow")
        if result.get("verdict") == "CONSENSUS":
            st.info("Both independent solvers agree. A third model call was unnecessary. Agreement does not guarantee correctness.")
        elif result["mode"] == "multi":
            st.info("The solvers disagreed, so an arbiter reviewed their proposals. Decision: " + str(result.get("verdict")))
    st.caption("Open any stage to read its complete explanation.")
    for idx, event in enumerate(result["trace"]):
        stage = event["stage"]
        if "prompt" in stage or "mapping" in stage:
            continue
        label = stage.replace("_", " ").title()
        if stage == "critic_output" and result.get("verdict") == "CONSENSUS":
            label = "Agreement check (deterministic, no critic model call)"
        with st.expander(label, expanded=stage == "single_response"):
            st.markdown(event["payload"].get("text", ""))
    st.download_button("Download solution and audit trail", json.dumps(result, indent=2, ensure_ascii=False),
                       "mathagents-solution.json", "application/json", key="download_" + key)
    st.caption("Check important answers yourself. These explanations come from an AI model and may contain errors.")


if page == "Solve":
    st.markdown('<div class="eyebrow">A little clarity goes a long way</div>', unsafe_allow_html=True)
    st.title("Make sense of the maths.")
    st.markdown('<div class="intro">Bring a question. Choose how to solve it. Explore the answer at your own pace.</div>', unsafe_allow_html=True)
    left, right = st.columns([1, 1.05], gap="large")
    with left:
        st.subheader("1. Choose your approach")
        mode_label = st.radio("Solving approach", ["Single agent", "Multi-agent team"], horizontal=True, label_visibility="collapsed")
        mode = "single" if mode_label == "Single agent" else "multi"
        st.caption("One focused model call, with a written explanation." if mode == "single" else "Two blind solvers work independently. An arbiter reviews disagreements. Usually 2–3 model calls.")
        st.subheader("2. Add your question")
        examples = {"Algebra": "Solve 2x + 3 = 11. Explain each step and check by substitution.",
                    "Probability": "Two fair six-sided dice are rolled. What is the probability that their sum is 8?",
                    "Number theory": "Find all positive integers n such that n + 1 divides n squared + 1. Give a proof."}
        cols = st.columns(3)
        for col, (name, question) in zip(cols, examples.items()):
            if col.button(name, use_container_width=True):
                st.session_state.question = question
        api_key = setting("ZAI_API_KEY")
        password = setting("APP_ACCESS_PASSWORD")
        authorized = False
        if api_key and password:
            entered = st.text_input("Presentation access code", type="password", help="The app owner shares this code with approved testers.")
            authorized = hmac.compare_digest(entered, password)
        elif api_key and setting("ALLOW_PUBLIC_USAGE", "false").lower() == "true":
            authorized = True
        else:
            st.info("The interface is ready. The app owner needs to enable the secure solver in Streamlit settings.")
        with st.form("solve_form"):
            problem = st.text_area("Mathematics question", key="question", height=190, max_chars=4000,
                                   placeholder="Type an equation or paste a word problem…")
            consent = st.checkbox("Send this question to the AI provider. I won’t include personal or confidential information.")
            submitted = st.form_submit_button("Solve my question", type="primary", use_container_width=True, disabled=not authorized)
        st.caption("Examples above are teaching examples, not benchmark results. Session history disappears when this browser session ends.")
        if submitted:
            if not consent:
                st.warning("Please confirm you are happy to send this question to the provider.")
            elif time.monotonic() - st.session_state.last_request < 10:
                st.warning("Please allow ten seconds between requests.")
            else:
                st.session_state.last_request = time.monotonic()
                st.session_state.answer = None
                try:
                    with st.status("Working on your question…", expanded=True) as status:
                        st.write("Running the selected workflow. Provider cooldowns may add a short delay.")
                        result = solve_question(problem, mode, CloudClient(api_key, setting("ZAI_MODEL", "glm-4.7-flash"), gate=request_gate()))
                        st.session_state.answer = result
                        st.session_state.history = [result, *st.session_state.history][:20]
                        status.update(label="Solution ready", state="complete", expanded=False)
                except SolverError as exc:
                    st.error(str(exc))
                except Exception:
                    st.error("The solver could not complete this question. No fallback answer has been substituted. Please try again.")
    with right:
        if st.session_state.answer:
            show_result(st.session_state.answer)
        else:
            with st.container(border=True):
                st.markdown("### Room for your next discovery")
                st.write("Your answer and complete solution stages will appear here.")
                st.divider()
                st.markdown("**Single agent** offers a direct solution.\n\n**Multi-agent team** adds an independent second attempt and a review when answers differ.")
                st.caption("This app uses real server-side model calls. It never substitutes a demonstration answer for a failed request.")

elif page == "My session":
    st.title("Your working notebook")
    st.write("Revisit up to 20 solutions from this session. Download anything you want to keep.")
    if st.button("Clear my session history"):
        st.session_state.history = []
        st.session_state.answer = None
    if not st.session_state.history:
        st.info("Solve your first question to start your notebook.")
    for i, result in enumerate(st.session_state.history):
        with st.expander(result["problem"][:100], expanded=i == 0):
            st.write(result["problem"])
            show_result(result, str(i))

elif page == "Research":
    st.markdown('<div class="eyebrow">Evidence, with its limits in view</div>', unsafe_allow_html=True)
    st.title("Does a second solver help?")
    path = ROOT / "research" / "snapshot.json"
    if not path.exists():
        st.warning("No verified research snapshot has been bundled.")
        st.stop()
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    m = snapshot["overall"]
    st.info(f"Interim snapshot captured {snapshot['captured_at'][:10]}. {m['paired_questions']:,} of 2,500 target pairs. This page does not run the long evaluation job.")
    a, b, c = st.columns(3)
    a.metric("Single-agent accuracy", f"{m['single_accuracy']:.1%}", f"{m['single_correct']} correct", delta_color="off")
    b.metric("Multi-agent accuracy", f"{m['multi_accuracy']:.1%}", f"{m['multi_correct']} correct", delta_color="off")
    c.metric("Observed difference", f"{m['multi_agent_accuracy_lift'] * 100:+.1f} pp")
    st.progress(min(m["paired_questions"] / 2500, 1), text=f"{m['paired_questions']:,} paired questions saved")
    chart = pd.DataFrame({"Approach": ["Single agent", "Multi-agent team"], "Accuracy (%)": [100*m["single_accuracy"], 100*m["multi_accuracy"]]}).set_index("Approach")
    st.bar_chart(chart, color="#087e76", horizontal=True)
    a, b, c = st.columns(3)
    a.metric("Successful corrections", str(m["successful_corrections"]), f"{m['correction_rate_among_wrong_executor_answers']:.1%} of wrong primary answers", delta_color="off")
    b.metric("Harmful changes", str(m["harmful_corrections"]), f"{m['regression_rate_among_correct_executor_answers']:.1%} of correct primary answers", delta_color="off")
    c.metric("Runtime trade-off", f"{m['runtime_multiplier']:.2f}×", "multi / single mean runtime", delta_color="off")
    with st.expander("Method, denominators and limitations", expanded=True):
        st.write(f"Dataset: {snapshot['dataset']}. Model recorded for the study: {snapshot['model']}. Temperature: 0. Internal thinking disabled. Scorer: {snapshot['scorer']}.")
        st.write("Accuracy compares the same question IDs for both frozen architecture versions. Provider failures and local fallbacks are excluded. Correction rate uses initially wrong primary-team answers as its denominator, not the separate single-agent baseline.")
        st.warning("This is an incomplete, difficulty-ordered sample. It cannot establish accuracy on the entire benchmark or on all mathematics. Earlier pilots used different workflows and remain separate. Interim p-values are exploratory because repeated monitoring and development can bias inference.")
        st.caption("Model identity comes from experiment configuration and available run metadata; some interrupted runs retain incomplete metadata. No Claude or flagship-model score is inferred.")
    st.download_button("Download research snapshot", path.read_bytes(), "mathagents-research-snapshot.json", "application/json")

else:
    st.title("Mathematics with a second perspective")
    st.write("MathAgents is a research-led mathematics assistant created for Hulisani Rambau’s honours project. It helps learners inspect solutions and compares a direct model with a custom team using the same underlying model.")
    st.subheader("How the team works")
    st.write("The primary solver and a blind verifier solve the same problem without seeing each other’s answer. A deterministic check compares their final answers. If they disagree, an arbiter receives anonymous A/B proposals. A format guardrail preserves the primary answer if the arbiter returns an unusable decision.")
    st.subheader("Privacy and responsible use")
    st.write("The solver sends your question and generated proposals to Z.ai. Do not enter personal information. This app keeps your last 20 solutions in session memory only and offers downloads. Hosting and model providers may maintain operational logs under their own policies. AI explanations can be wrong. This is a learning aid, not a proof checker.")
    st.link_button("Z.ai privacy information", "https://z.ai/privacy-policy")
    st.subheader("Research and product boundaries")
    st.write("The long-running study stays separate from the public app. Cloud restarts do not alter the local experiment registry. The optional CrewAI research implementation is not part of the public navigation or the reported custom-team results.")

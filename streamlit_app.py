"""MathAgents: a useful mathematics workspace and transparent research companion."""
from pathlib import Path
import base64
import json
import os
import time

import pandas as pd
import streamlit as st

from services import CloudClient, RequestGate, SolverError, solve_question
from workspace_tools import paired_history, feedback_record, filter_history

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="MathAgents | UJ student research", page_icon=str(ROOT / "assets" / "uj-logo.png"), layout="wide")
st.markdown("<style>" + (ROOT / "assets" / "workspace.css").read_text(encoding="utf-8") + "</style>", unsafe_allow_html=True)
logo_data = base64.b64encode((ROOT / "assets" / "uj-logo.png").read_bytes()).decode("ascii")
st.markdown(
    '<header class="uj-masthead">'
    f'<img src="data:image/png;base64,{logo_data}" alt="University of Johannesburg logo" width="100" height="100">'
    '<div><div class="uj-university">University of Johannesburg</div>'
    '<div class="uj-project">MathAgents <span>Honours research prototype</span></div>'
    '<p>Student project by Hulisani Rambau</p></div>'
    '</header>', unsafe_allow_html=True,
)


def setting(key, default=""):
    try:
        return str(st.secrets.get(key, os.getenv(key, default)))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return os.getenv(key, default)


@st.cache_resource
def request_gate():
    return RequestGate(daily_limit=300)


def clear_question():
    st.session_state.question = ""


def reopen_question(problem):
    st.session_state.question = problem
    st.session_state.answer = None
    st.session_state.workspace_page = "Solve"


def solution_text(result):
    """A portable, readable export; never include credentials."""
    lines = ["MathAgents • Solution", "", result["problem"], "",
             "FINAL ANSWER", result["final_answer"], "",
             f"{result['mode']} | {result['model']} | {result['elapsed_seconds']:.1f} seconds"]
    lines.extend(["Source: " + result.get("execution_source", "live_provider"),
                  "Recorded at: " + result.get("created_at", "unknown")])
    if result.get("reused_stages"):
        lines.append("Reused saved stages: " + json.dumps(result['reused_stages']))
    if result.get("execution_source") == "saved_benchmark":
        lines.append("RECORDED BENCHMARK REPLAY — not live generation.")
    for event in result["trace"]:
        if "prompt" not in event["stage"] and "mapping" not in event["stage"]:
            lines.extend(["", event["stage"].replace("_", " ").title(), event["payload"].get("text", "")])
    lines.extend(["", "AI-generated explanation. Independently check important answers."])
    return "\n".join(lines)


for key, default in {"history": [], "answer": None, "question": "", "last_request": 0.0, "feedback": [], "response_cache": {}}.items():
    if key not in st.session_state:
        st.session_state[key] = default

with st.sidebar:
    st.markdown('<div class="sidebar-kicker">UJ · STUDENT RESEARCH</div><div class="brand">∑ MathAgents</div><div class="subtle">Your mathematics workspace</div>', unsafe_allow_html=True)
    st.divider()
    page = st.radio("Workspace", ["Solve", "Presentation (saved)", "Compare", "My session", "Research", "Feedback", "About"], key="workspace_page", label_visibility="collapsed")
    st.divider()
    st.markdown("**YOUR SPACE**")
    st.caption(f"{len(st.session_state.history)} saved solution{'s' if len(st.session_state.history) != 1 else ''} this session")
    st.caption("A direct solver when you want focus. An independent team when you want another check.")
    st.caption("AI-assisted learning · Check important answers")
    st.caption("Beta workspace · October 2026")
    st.caption("Honours project · Hulisani Rambau")


def show_result(result, key="current"):
    st.markdown('<div class="eyebrow">Your solution workspace</div>', unsafe_allow_html=True)
    st.subheader("Answer and explanation")
    if result.get("execution_source") == "saved_benchmark":
        st.warning("RECORDED BENCHMARK REPLAY — not a live generation. No provider request is sent.")
        st.caption(f"Saved {result['created_at']} · Question ID: {result['question_id']}")
    elif result.get("reused_stages"):
        st.info(f"Reused {len(result['reused_stages'])} successful model stage(s) from this browser session. This is a cached/resumed result, not an entirely fresh generation.")
    with st.expander("Question answered", expanded=True):
        st.write(result["problem"])
    with st.container(border=True):
        st.caption("FINAL ANSWER")
        st.markdown(result["final_answer"])
        a, b = st.columns(2)
        a.metric("Approach", "Single agent" if result["mode"] == "single" else "Multi-agent team")
        b.metric("Recorded runtime" if result.get("execution_source") == "saved_benchmark" else "This attempt", f"{result['elapsed_seconds']:.1f} s")
        st.caption(f"Model: {result['model']} · AI-generated, not independently certified")
        if result.get("runtime_scope"):
            st.caption(result["runtime_scope"])
        if result.get("verdict") == "CONSENSUS":
            st.info("Both independent solvers agree. A third model call was unnecessary. Agreement does not guarantee correctness.")
        elif result["mode"] == "multi":
            st.info("The solvers disagreed, so an arbiter reviewed their proposals. Decision: " + str(result.get("verdict")))
    st.markdown("#### Explore the solution")
    st.caption("Nothing is cut off. Open each stage to read the full text and select anything you want to copy.")
    expand_all = st.toggle("Expand all explanations", key="expand_all_" + key)
    for idx, event in enumerate(result["trace"]):
        stage = event["stage"]
        if "prompt" in stage or "mapping" in stage:
            continue
        label = stage.replace("_", " ").title()
        label = {"planner_executor_output": "Primary solver: plan and solution",
                 "verifier_output": "Independent verifier: alternative solution",
                 "critic_output": "Arbiter: review and final decision",
                 "deterministic_guardrail": "Format safeguard"}.get(stage, label)
        if stage == "critic_output" and result.get("verdict") == "CONSENSUS":
            label = "Agreement check (deterministic, no critic model call)"
        with st.expander(label, expanded=expand_all or stage == "single_response"):
            st.markdown(event["payload"].get("text", ""))
    st.download_button("Download solution and audit trail", json.dumps(result, indent=2, ensure_ascii=False),
                       "mathagents-solution.json", "application/json", key="download_" + key)
    st.download_button("Save readable solution", solution_text(result), "mathagents-solution.txt",
                       "text/plain", key="text_" + key)
    st.caption("Check important answers yourself. These explanations come from an AI model and may contain errors.")


if page == "Solve":
    st.markdown('<div class="eyebrow">MATHAGENTS / YOUR THINKING SPACE</div>', unsafe_allow_html=True)
    st.title("Work through your mathematics")
    st.markdown('<div class="intro">A focused solver or a fresh second perspective. Bring your maths, explore the steps, and build your understanding.</div>', unsafe_allow_html=True)
    st.info("Presenting? Open Presentation (saved) for real recorded examples that do not depend on the AI provider. Live solving is subject to provider availability.")
    st.markdown('<div class="journey"><span>01 &nbsp; Choose an approach</span><span>02 &nbsp; Ask your question</span><span>03 &nbsp; Explore the solution</span></div>', unsafe_allow_html=True)
    left, right = st.columns([1, 1.05], gap="large")
    with left:
        st.subheader("1. Choose your approach")
        mode_label = st.radio("Solving approach", ["Single agent", "Multi-agent team"], horizontal=True, label_visibility="collapsed")
        mode = "single" if mode_label == "Single agent" else "multi"
        if mode == "single":
            st.markdown('<div class="mode-card"><span class="mode-tag">FOCUSED & DIRECT</span><h3>One question. One focused solver.</h3><p>A direct answer with an explanation you can follow. Uses one model call.</p></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="mode-card team"><span class="mode-tag">AN INDEPENDENT SECOND LOOK</span><h3>Two perspectives. A reviewed answer.</h3><p>Two solvers work independently. An arbiter reviews disagreements. Usually 2–3 calls, so allow more time.</p></div>', unsafe_allow_html=True)
        st.subheader("2. Add your question")
        examples = {"Algebra": "Solve 2x + 3 = 11. Explain each step and check by substitution.",
                    "Probability": "Two fair six-sided dice are rolled. What is the probability that their sum is 8?",
                    "Number theory": "Find all positive integers n such that n + 1 divides n squared + 1. Give a proof."}
        cols = st.columns(3)
        for col, (name, question) in zip(cols, examples.items()):
            if col.button(name, use_container_width=True):
                st.session_state.question = question
        api_key = setting("ZAI_API_KEY")
        authorized = bool(api_key)
        if authorized:
            st.caption("No access code needed. Your question is sent only when you submit.")
        else:
            st.info("The interface is ready. The app owner needs to configure the AI provider in Streamlit settings.")
        remaining = request_gate().remaining()
        if remaining:
            st.warning(f"Provider cooldown: about {remaining} seconds remaining when this page loaded. Avoid repeated submissions; use Presentation (saved) meanwhile.")
            st.button("Refresh provider status", help="Refresh this display without sending an AI request.")
        with st.form("solve_form"):
            problem = st.text_area("Mathematics question", key="question", height=190, max_chars=4000,
                                   placeholder="Type an equation or paste a word problem…")
            consent = st.checkbox("Send this question to the AI provider. I won’t include personal or confidential information.")
            submitted = st.form_submit_button("Solve my question", type="primary", use_container_width=True, disabled=not authorized)
        st.button("Clear question", on_click=clear_question, help="Clear the editor without deleting saved solutions.")
        st.caption("Examples above are teaching examples, not benchmark results. Session history disappears when this browser session ends.")
        if submitted:
            if not consent:
                st.warning("Please confirm you are happy to send this question to the provider.")
            elif time.monotonic() - st.session_state.last_request < 10:
                st.warning("Please allow ten seconds between requests.")
            else:
                st.session_state.last_request = time.monotonic()
                try:
                    with st.status("Working on your question…", expanded=True) as status:
                        st.write("Requests are queued one at a time to reduce provider limits. Temporary failures receive up to three attempts; long cooldowns stop safely. This can take several minutes. Successful stages are reused on retry.")
                        result = solve_question(problem, mode, CloudClient(api_key, setting("ZAI_MODEL", "glm-4.7-flash"), gate=request_gate(), response_cache=st.session_state.response_cache))
                        st.session_state.answer = result
                        st.session_state.history = [result, *st.session_state.history][:20]
                        status.update(label="Solution ready", state="complete", expanded=False)
                except SolverError as exc:
                    status.update(label="Live provider unavailable — saved presentation is available", state="error", expanded=False)
                    st.error(str(exc))
                    st.info("Your question and any previous answer are preserved. Open Presentation (saved) in the sidebar to continue your demonstration without the provider.")
                except Exception:
                    status.update(label="Live request could not finish", state="error", expanded=False)
                    st.error("The solver could not complete this question. No fallback answer has been substituted. Please try again.")
    with right:
        if st.session_state.answer:
            show_result(st.session_state.answer)
        else:
            with st.container(border=True):
                st.markdown('<div class="empty-state"><div class="math-mark">x² + y²</div><div class="eyebrow">A SPACE FOR THE AHA MOMENT</div><h2>Your next solution starts here.</h2><p>Choose an example or add your own question.<br>Your answer and complete explanations will appear in this space.</p></div>', unsafe_allow_html=True)
                st.markdown("**A good question goes a long way**")
                st.write("Include the full problem, any constraints, and what you want to find. Ask for a substitution check or a proof where useful.")
                st.caption("Real model calls only. We never substitute a demonstration answer when a request fails.")

elif page == "Presentation (saved)":
    st.title("Presentation: recorded model examples")
    st.info("These are genuine saved Omni-MATH-Rule outputs, selected to show both a correction and a harmful change. They are not live responses and are not a representative sample. This page makes zero AI-provider calls; the website itself still needs internet access.")
    examples = json.loads((ROOT / "research" / "presentation_examples.json").read_text(encoding="utf-8"))
    selected = st.selectbox("Recorded example", range(len(examples)), format_func=lambda i: examples[i]["title"])
    example = examples[selected]
    st.markdown("### " + example["title"])
    st.write(example["explanation"])
    st.caption("Reference answer: " + example["reference_answer"])
    show_result(example["result"], "presentation_" + str(selected))
    st.download_button("Download recorded examples for backup", json.dumps(examples, indent=2, ensure_ascii=False), "mathagents-recorded-examples.json", "application/json")
    st.caption("For a live demonstration, return to Solve. Replays are never silently substituted for a failed live request.")

elif page == "Compare":
    st.title("Compare your solutions")
    st.write("Solve the exact same question with each approach, then inspect the saved answers together. This page makes no additional AI calls.")
    pairs = paired_history(st.session_state.history)
    if not pairs:
        st.info("Choose a question in Solve, run Single agent, then select Multi-agent team and submit the same question again. Both answers will appear here.")
    else:
        selected = st.selectbox("Question and model", range(len(pairs)),
                                format_func=lambda i: pairs[i][0][:100] + " · " + pairs[i][1])
        question, model, modes = pairs[selected]
        st.write(question)
        st.caption(f"Model: {model}. These are your session answers, not benchmark scores.")
        for col, mode in zip(st.columns(2), ['single', 'multi']):
            with col:
                show_result(modes[mode], 'comparison_' + mode)
        st.info("Inspect the assumptions and working in both solutions. Matching answers alone do not establish correctness.")

elif page == "My session":
    st.title("Your working notebook")
    st.write("Revisit up to 20 solutions from this session. Download anything you want to keep.")
    st.caption(f"{len(st.session_state.history)} / 20 solutions · Private to this browser session")
    if st.session_state.history:
        st.download_button("Download my notebook", json.dumps(st.session_state.history, indent=2, ensure_ascii=False),
                           "mathagents-notebook.json", "application/json")
    confirm_clear = st.checkbox("I understand that clearing my notebook cannot be undone.")
    if st.button("Clear my session history", disabled=not confirm_clear):
        st.session_state.history = []
        st.session_state.answer = None
        st.session_state.response_cache = {}
    if not st.session_state.history:
        st.info("Solve your first question to start your notebook.")
    search = st.text_input("Search saved questions or answers", placeholder="For example: probability, 2x, or 4")
    notebook_mode = st.selectbox("Filter by approach", ["All approaches", "Single agent", "Multi-agent team"])
    mode_filter = {"All approaches": "all", "Single agent": "single", "Multi-agent team": "multi"}[notebook_mode]
    visible = filter_history(st.session_state.history, search, mode_filter)
    if st.session_state.history:
        st.caption(f"Showing {len(visible)} of {len(st.session_state.history)} saved solutions. Filters do not delete your notebook.")
        if not visible:
            st.info("No saved solutions match. Try a different search or choose All approaches.")
    for i, result in visible:
        with st.expander(result["problem"][:100], expanded=i == 0):
            st.write(result["problem"])
            st.button("Use this question again", key=f"reuse_{i}", on_click=reopen_question, args=(result["problem"],),
                      help="Open the question in Solve. No AI request is sent until you submit.")
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
    target = snapshot.get("target", 2500)
    st.info(f"Saved snapshot · {snapshot['captured_at'][:10]} · {m['paired_questions']:,}/{target:,} target pairs. This is not a live counter; research continues separately.")
    a, b, c = st.columns(3)
    a.metric("Single-agent accuracy", f"{m['single_accuracy']:.1%}", f"{m['single_correct']} correct", delta_color="off")
    b.metric("Multi-agent accuracy", f"{m['multi_accuracy']:.1%}", f"{m['multi_correct']} correct", delta_color="off")
    c.metric("Observed difference", f"{m['multi_agent_accuracy_lift'] * 100:+.1f} pp")
    st.progress(min(m["paired_questions"] / target, 1), text=f"{m['paired_questions']:,} paired questions saved · {max(0, target - m['paired_questions']):,} still to complete")
    chart = pd.DataFrame({"Approach": ["Single agent", "Multi-agent team"], "Accuracy (%)": [100*m["single_accuracy"], 100*m["multi_accuracy"]]}).set_index("Approach")
    st.bar_chart(chart, color="#A63C00", horizontal=True)
    a, b, c = st.columns(3)
    a.metric("Successful corrections", str(m["successful_corrections"]), f"{m['correction_rate_among_wrong_executor_answers']:.1%} of wrong primary answers", delta_color="off")
    b.metric("Harmful changes", str(m["harmful_corrections"]), f"{m['regression_rate_among_correct_executor_answers']:.1%} of correct primary answers", delta_color="off")
    c.metric("Runtime trade-off", f"{m['runtime_multiplier']:.2f}×", "multi / single mean runtime", delta_color="off")
    with st.expander("Accuracy by difficulty · inspect the sample"):
        tiers = [{"Difficulty": name.replace("difficulty_", "").replace("_", "."),
                  "Paired questions": values["paired_questions"],
                  "Single (%)": round(values["single_accuracy"] * 100, 1),
                  "Multi (%)": round(values["multi_accuracy"] * 100, 1)}
                 for name, values in snapshot.get("by_difficulty", {}).items()]
        st.dataframe(pd.DataFrame(tiers), hide_index=True, use_container_width=True)
        st.caption("Difficulty groups have different sample sizes. This is a difficulty-ordered interim sample, not a random benchmark estimate.")
    with st.expander("Method, denominators and limitations", expanded=True):
        st.write(f"Dataset: {snapshot['dataset']}. Model recorded for the study: {snapshot['model']}. Temperature: 0. Internal thinking disabled. Scorer: {snapshot['scorer']}.")
        st.write("Accuracy compares the same question IDs for both frozen architecture versions. Provider failures and local fallbacks are excluded. Correction rate uses initially wrong primary-team answers as its denominator, not the separate single-agent baseline.")
        st.warning("This is an incomplete, difficulty-ordered sample. It cannot establish accuracy on the entire benchmark or on all mathematics. Earlier pilots used different workflows and remain separate. Interim p-values are exploratory because repeated monitoring and development can bias inference.")
        st.caption("Model identity comes from experiment configuration and available run metadata; some interrupted runs retain incomplete metadata. No Claude or flagship-model score is inferred.")
    st.download_button("Download research snapshot", path.read_bytes(), "mathagents-research-snapshot.json", "application/json")

elif page == "Feedback":
    st.title("Help improve MathAgents")
    st.write("After trying a task, record what worked and what was difficult. Participation is optional. Do not include names or other personal information.")
    st.caption("Feedback stays in this browser session. Download it and share it with the researcher only if you choose. This is an informal usability record, not a validated questionnaire.")
    with st.form('feedback_form'):
        task = st.selectbox('Task attempted', ['Solve a question', 'Compare both approaches', 'Export a solution'])
        completed = st.checkbox('I completed this task')
        ease = st.slider('Ease of use (1 difficult, 5 easy)', 1, 5, 3)
        clarity = st.slider('Clarity of the explanation (1 unclear, 5 clear)', 1, 5, 3)
        comment = st.text_area('What should improve?', max_chars=1000)
        permission = st.checkbox('I agree to save this voluntary feedback in this session')
        save = st.form_submit_button('Save feedback')
    if save:
        if permission:
            st.session_state.feedback = [*st.session_state.feedback, feedback_record(task, completed, ease, clarity, comment)][-20:]
            st.success('Feedback saved in this session. Download it below if you want to share it.')
        else:
            st.warning('Please agree before saving feedback.')
    if st.session_state.feedback:
        st.download_button('Download my feedback', json.dumps(st.session_state.feedback, indent=2), 'mathagents-feedback.json', 'application/json')
        if st.button('Delete my feedback'):
            st.session_state.feedback = []
            st.rerun()

else:
    st.title("Mathematics with a second perspective")
    st.info("University of Johannesburg student research prototype. Created by Hulisani Rambau for an honours project.")
    st.write("MathAgents is a research-led mathematics assistant created for Hulisani Rambau’s honours project. It helps learners inspect solutions and compares a direct model with a custom team using the same underlying model.")
    st.subheader("How the team works")
    st.write("The primary solver and a blind verifier solve the same problem without seeing each other’s answer. A deterministic check compares their final answers. If they disagree, an arbiter receives anonymous A/B proposals. A format guardrail preserves the primary answer if the arbiter returns an unusable decision.")
    st.subheader("Privacy and responsible use")
    st.write("The solver sends your question and generated proposals to Z.ai. Do not enter personal information. This app keeps your last 20 solutions in session memory only and offers downloads. Hosting and model providers may maintain operational logs under their own policies. AI explanations can be wrong. This is a learning aid, not a proof checker.")
    st.link_button("Z.ai privacy information", "https://z.ai/privacy-policy")
    st.subheader("Research and product boundaries")
    st.write("The long-running study stays separate from the public app. Cloud restarts do not alter the local experiment registry. The optional CrewAI research implementation is not part of the public navigation or the reported custom-team results.")

"""AI Text-to-SQL with a clarification engine — Streamlit front end.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import logging

import streamlit as st

from config.settings import settings
from core.clarification_engine import ClarificationEngine
from core.data_processor import process_tables
from core.file_handler import FileLoadError, load_uploaded_file, save_upload
from core.llm_handler import LLMError, LLMHandler
from core.query_executor import QueryExecutionError, QueryExecutor
from core.response_generator import ResponseGenerator
from core.schema_analyzer import SchemaAnalyzer
from core.sql_generator import SQLGenerator
from core.sql_validator import SQLValidator
from database.database_manager import DatabaseManager
from utils.helpers import escape_markdown_dollars

logging.basicConfig(level=logging.INFO)
st.set_page_config(page_title="AI Text-to-SQL", page_icon="🧠", layout="wide")


# --------------------------------------------------------------------- state
def init_state() -> None:
    defaults = {
        "db": None,
        "tables": {},
        "schema_text": "",
        "signature": None,
        "load_error": None,
        "messages": [],     # chat history shown on screen
        "pending": None,    # a question waiting for the user's clarification
        "pending_id": 0,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def reset_conversation() -> None:
    st.session_state.messages = []
    st.session_state.pending = None


@st.cache_resource(show_spinner=False)
def get_llm(api_key: str, model: str) -> LLMHandler:
    return LLMHandler(api_key=api_key, model=model)


# --------------------------------------------------------------- data loading
def load_data(files) -> tuple[DatabaseManager, dict, str]:
    raw = {}
    for f in files:
        data = f.getvalue()
        save_upload(f.name, data)
        for name, df in load_uploaded_file(f.name, data).items():
            key = name
            while key in raw:  # two files with the same name
                key += "_2"
            raw[key] = df
    tables = process_tables(raw)
    if not tables:
        raise FileLoadError("No usable data found in the uploaded file(s).")
    db = DatabaseManager()
    db.load_tables(tables)
    return db, tables, SchemaAnalyzer().build_schema_text(tables)


def render_sidebar() -> None:
    with st.sidebar:
        st.header("📂 Your data")
        files = st.file_uploader(
            "Upload CSV, Excel, TSV or JSON",
            type=[e.lstrip(".") for e in settings.allowed_extensions],
            accept_multiple_files=True,
        )
        if files:
            signature = tuple((f.name, f.size) for f in files)
            if signature != st.session_state.signature:
                try:
                    db, tables, schema = load_data(files)
                    st.session_state.update(
                        db=db, tables=tables, schema_text=schema,
                        signature=signature, load_error=None,
                    )
                except FileLoadError as exc:
                    st.session_state.update(
                        db=None, tables={}, schema_text="",
                        signature=signature, load_error=str(exc),
                    )
                reset_conversation()
        elif st.session_state.signature is not None:
            st.session_state.update(db=None, tables={}, schema_text="", signature=None, load_error=None)
            reset_conversation()

        if st.session_state.load_error:
            st.error(st.session_state.load_error)

        for name, df in st.session_state.tables.items():
            with st.expander(f"📄 {name}  ({len(df):,} rows × {df.shape[1]} cols)"):
                st.dataframe(df.head(10))

        if st.session_state.db is not None:
            st.divider()
            st.markdown(
                "**Try asking**\n"
                "- What is the average salary of all employees?\n"
                "- How many employees are in each department?\n"
                "- Who are the top 5 highest paid employees?"
            )
            if st.button("🗑️ Clear chat"):
                reset_conversation()
                st.rerun()


# -------------------------------------------------------------------- pipeline
def recent_history() -> list[dict]:
    """Previous answered turns, so follow-up questions make sense."""
    turns = [m for m in st.session_state.messages if m["role"] == "assistant" and m.get("sql")]
    return [
        {"question": m["question"], "sql": m["sql"], "answer": m["content"]}
        for m in turns[-settings.max_history_turns:]
    ]


def answer_question(question: str, clarifications: str, assumptions: list[str]) -> dict:
    """Generate -> validate -> execute (with self-repair) -> explain."""
    llm = get_llm(settings.groq_api_key, settings.model)
    db = st.session_state.db
    schema = st.session_state.schema_text

    generator = SQLGenerator(llm)
    validator = SQLValidator(db)
    executor = QueryExecutor(db)
    responder = ResponseGenerator(llm)

    sql = generator.generate(question, schema, recent_history(), clarifications, assumptions)
    last_error = "unknown error"

    for attempt in range(settings.max_sql_retries + 1):
        validation = validator.validate(sql)
        if validation.is_valid:
            try:
                result = executor.execute(validation.sql)
                answer = responder.generate(question, result, assumptions)
                return {
                    "role": "assistant", "question": question, "content": answer,
                    "sql": validation.sql, "df": result.df, "truncated": result.truncated,
                }
            except QueryExecutionError as exc:
                last_error = str(exc)
        else:
            last_error = validation.error or "validation failed"

        if attempt < settings.max_sql_retries:
            sql = generator.repair(question, schema, sql, last_error, clarifications)

    return {
        "role": "assistant", "question": question, "sql": None,
        "content": (
            "I couldn't build a reliable query for that question. "
            "Try rephrasing it or naming the columns you care about.\n\n"
            f"_Technical detail: {last_error}_"
        ),
    }


def handle_new_question(question: str) -> None:
    st.session_state.messages.append({"role": "user", "content": question})
    try:
        llm = get_llm(settings.groq_api_key, settings.model)
        with st.spinner("Understanding your question..."):
            analysis = ClarificationEngine(llm).analyze(
                question, st.session_state.schema_text, recent_history()
            )

        if not analysis.can_answer:
            st.session_state.messages.append(
                {"role": "assistant", "question": question, "sql": None, "content": analysis.reason}
            )
        elif analysis.needs_clarification:
            st.session_state.pending_id += 1
            st.session_state.pending = {
                "id": st.session_state.pending_id,
                "question": question,
                "analysis": analysis,
            }
        else:
            with st.spinner("Querying your data..."):
                message = answer_question(question, "", analysis.assumptions)
            st.session_state.messages.append(message)
    except LLMError as exc:
        st.session_state.messages.append(
            {"role": "assistant", "question": question, "sql": None, "content": f"⚠️ {exc}"}
        )
    st.rerun()


def render_clarification_form() -> None:
    pending = st.session_state.pending
    analysis = pending["analysis"]

    with st.chat_message("assistant"):
        st.markdown("Quick check so I give you the right answer:")
        with st.form(f"clarify_{pending['id']}"):
            choices, custom = {}, {}
            for i, q in enumerate(analysis.questions):
                st.markdown(f"**{q.question}**")
                if q.options:
                    choices[i] = st.radio(
                        q.question, q.options, index=None,
                        key=f"choice_{pending['id']}_{i}", label_visibility="collapsed",
                    )
                custom[i] = st.text_input(
                    "Or type your own answer", key=f"custom_{pending['id']}_{i}"
                )
            col1, col2 = st.columns(2)
            submitted = col1.form_submit_button("Continue", type="primary")
            skipped = col2.form_submit_button("Skip — use your best guess")

    if not (submitted or skipped):
        return

    answers = {}
    if submitted:
        for i in range(len(analysis.questions)):
            answers[i] = custom.get(i, "").strip() or (choices.get(i) or "")
    notes = ClarificationEngine.merge_answers(analysis.questions, answers)
    if not notes:
        notes = "The user skipped clarification. Choose the most sensible interpretation."

    st.session_state.pending = None
    try:
        with st.spinner("Querying your data..."):
            message = answer_question(pending["question"], notes, analysis.assumptions)
    except LLMError as exc:
        message = {"role": "assistant", "question": pending["question"], "sql": None, "content": f"⚠️ {exc}"}
    st.session_state.messages.append(message)
    st.rerun()


def render_history() -> None:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(escape_markdown_dollars(msg["content"]))
            if msg.get("truncated"):
                st.caption(f"Showing the first {settings.max_result_rows:,} rows only.")
            if msg.get("sql"):
                with st.expander("View SQL"):
                    st.code(msg["sql"], language="sql")
            if msg.get("df") is not None and not msg["df"].empty:
                with st.expander("View result table"):
                    st.dataframe(msg["df"])


# ------------------------------------------------------------------------ main
def main() -> None:
    init_state()
    render_sidebar()

    st.title("🧠 AI Text-to-SQL")
    st.caption("Upload your data, ask questions in plain English, get answers in plain English.")

    if not settings.groq_api_key:
        st.error("`GROQ_API_KEY` is not set. Copy `.env.example` to `.env`, add your key, and restart.")
        st.stop()

    if st.session_state.db is None:
        st.info("👈 Upload a CSV, Excel, TSV or JSON file in the sidebar to get started.")
        st.stop()

    render_history()
    if st.session_state.pending:
        render_clarification_form()

    question = st.chat_input(
        "Ask a question about your data…", disabled=st.session_state.pending is not None
    )
    if question:
        handle_new_question(question.strip())


main()

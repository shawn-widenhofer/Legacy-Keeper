import streamlit as st

from find_answers import render as render_find_answers
from interview import render as render_interview
from legacy_keeper_common import API_KEY


st.set_page_config(page_title="Legacy Keeper", layout="wide")
st.session_state.setdefault("profile", None)
st.session_state.setdefault("session", None)
st.session_state.setdefault("employee_kb_chat", [])
st.session_state.setdefault("show_welcome", True)
st.session_state.setdefault("app_area", "home")


@st.dialog("Welcome to Legacy Keeper", width="small", dismissible=False)
def welcome_dialog():
    st.markdown(
        "Capture the experience that keeps work moving forward. "
        "Legacy Keeper helps you interview retiring colleagues, review their "
        "knowledge, and make approved notes available to successors."
    )
    st.markdown(
        "**How it works**\n"
        "1. Capture and review knowledge through a guided retirement interview.\n"
        "2. Publish approved notes so new employees can search for answers."
    )
    st.warning(
        "Do not enter patient names, sensitive personal information, or credentials. "
        "Interview answers are sent to your configured MatchaOS API for processing. "
        "Notes are stored locally and uploaded to MatchaOS only when you publish."
    )
    if st.button("OK", type="primary", use_container_width=True):
        st.session_state.show_welcome = False
        st.rerun()


if st.session_state.show_welcome:
    welcome_dialog()
    st.stop()

if not API_KEY or API_KEY.startswith("${"):
    st.error("MATCHAOS_API_KEY is not configured in your .env file.")
    st.stop()

if st.session_state.app_area == "home":
    st.title("Legacy Keeper")
    st.write("Choose how you would like to use the knowledge captured here.")
    capture_col, search_col = st.columns(2)
    with capture_col:
        with st.container(border=True):
            st.subheader("Share your experience")
            st.write(
                "Capture and review knowledge through a guided retirement interview.")
            if st.button(
                "Capture Knowledge", type="primary", use_container_width=True
            ):
                st.session_state.app_area = "capture"
                st.rerun()
    with search_col:
        with st.container(border=True):
            st.subheader("Find answers")
            st.write(
                "Search across published knowledge bases for practical answers and sources.")
            if st.button("Find Answers", use_container_width=True):
                st.session_state.app_area = "find"
                st.rerun()
    st.stop()

if st.session_state.app_area == "capture":
    render_interview()
elif st.session_state.app_area == "find":
    render_find_answers()
else:
    st.session_state.app_area = "home"
    st.rerun()

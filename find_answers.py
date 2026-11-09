import streamlit as st

from legacy_keeper_common import ask_folder, dictation_input, published_knowledge_bases


def query_entire_knowledge_base(question, chat_history, knowledge_bases):
    answers = []
    sources = []
    warnings = []
    queried_folders = set()

    for knowledge_base in knowledge_bases:
        folder_id = knowledge_base["folder_id"]
        if folder_id in queried_folders:
            continue
        queried_folders.add(folder_id)

        answer, folder_sources, folder_warnings = ask_folder(
            folder_id, question, chat_history)
        if folder_warnings:
            warnings.append(f"{knowledge_base['name']}: {folder_warnings}")
        if folder_sources:
            if answer:
                answers.append(f"### {knowledge_base['name']}\n{answer}")
            sources.extend(
                {**source, "knowledge_base": knowledge_base["name"]}
                for source in folder_sources
                if isinstance(source, dict)
            )

    if warnings:
        return "", [], "; ".join(warnings)
    if not sources:
        return "", [], ""
    combined_answer = "\n\n".join(answers) or (
        "Relevant supporting passages were found. See the sources below."
    )
    return combined_answer, sources, ""


def render():
    with st.sidebar:
        if st.button("← Main menu"):
            st.session_state.app_area = "home"
            st.rerun()

    st.title("Find Answers")
    st.caption(
        "Search across all locally published retiree knowledge bases. "
        "Answers are grounded in the saved documents and include sources."
    )
    knowledge_bases = published_knowledge_bases()
    if not knowledge_bases:
        st.info(
            "No published knowledge bases are available yet. "
            "Capture and publish knowledge first."
        )
        return

    selected_scope = st.selectbox(
        "Search scope",
        ["Entire knowledge base"],
        key="employee_kb_scope",
    )
    if selected_scope != "Entire knowledge base":
        raise RuntimeError(f"Unsupported search scope: {selected_scope}")

    st.caption(f"Searching {len(knowledge_bases)} published knowledge base(s).")
    for message in st.session_state.employee_kb_chat:
        with st.chat_message(message["role"]):
            st.write(message["text"])
            if message.get("sources"):
                with st.expander("Sources"):
                    for source in message["sources"]:
                        st.markdown(
                            f"**{source.get('knowledge_base', 'Knowledge base')} · "
                            f"{source.get('file_name', '?')}** "
                            f"({source.get('score', '')})"
                        )
                        st.caption(source.get("contents", ""))

    st.caption(
        "Dictation uses your browser's speech service, which may process audio. "
        "Do not dictate sensitive information."
    )
    question_event = dictation_input(
        "Your question",
        "Type your question or use Dictate...",
        key="employee_question_input",
    )
    if (
        isinstance(question_event, dict)
        and question_event.get("text", "").strip()
        and question_event.get("submit_id")
        != st.session_state.get("last_employee_submission")
    ):
        question = question_event["text"].strip()
        st.session_state.last_employee_submission = question_event["submit_id"]
        history = [
            {"role": "user", "content": message["text"]}
            if message["role"] == "user"
            else {
                "role": "assistant",
                "content": [{"type": "output_text", "text": message["text"]}],
            }
            for message in st.session_state.employee_kb_chat
        ]
        st.session_state.employee_kb_chat.append(
            {"role": "user", "text": question})
        try:
            with st.spinner("Searching the entire knowledge base..."):
                answer, sources, warnings = query_entire_knowledge_base(
                    question, history, knowledge_bases)
        except Exception as exc:
            st.session_state.employee_kb_chat.append(
                {"role": "assistant", "text": f"Query failed: {exc}"})
        else:
            if warnings:
                message = (
                    f"Not grounded in the documents (warning: {warnings}). "
                    "Answer withheld."
                )
                sources = []
            elif not sources:
                message = (
                    "No supporting passages were found. The requested knowledge "
                    "may not be covered, or this API key may lack access."
                )
            else:
                message = answer
            st.session_state.employee_kb_chat.append({
                "role": "assistant",
                "text": message,
                "sources": sources,
            })
        st.rerun()

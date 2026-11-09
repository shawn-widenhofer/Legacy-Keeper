import time

import streamlit as st

from legacy_keeper_common import (
    DATA_DIR,
    DEFAULT_MISSION,
    STATUS_ICON,
    all_notes,
    dictation_input,
    end_session,
    list_missions,
    list_sessions,
    load_json,
    publish,
    rdir,
    run_turn,
    save_json,
    save_profile,
    slug,
    start_session,
)


def render():
    active_session = st.session_state.session is not None
    with st.sidebar:
        if st.button("← Main menu"):
            st.session_state.app_area = "home"
            st.rerun()
        st.divider()
        st.header("Retiree")
        existing_names = (
            sorted(path.name for path in DATA_DIR.glob("*") if path.is_dir())
            if DATA_DIR.exists() else []
        )
        if existing_names:
            pick = st.selectbox(
                "Load existing",
                [""] + existing_names,
                disabled=active_session,
            )
            current = st.session_state.profile
            if pick and (current is None or slug(current["name"]) != pick):
                profile = load_json(DATA_DIR / pick / "profile.json", None)
                if profile:
                    st.session_state.profile = profile
                    st.session_state.session = None

        with st.expander(
            "New / edit profile", expanded=st.session_state.profile is None
        ):
            profile0 = st.session_state.profile or {}
            name = st.text_input("Name", profile0.get("name", ""), disabled=active_session)
            role = st.text_input("Role", profile0.get("role", ""), disabled=active_session)
            months = st.number_input(
                "Months until retirement", 0, 60, profile0.get("months", 6),
                disabled=active_session)
            minutes = st.number_input(
                "Session length (min)", 10, 120, profile0.get("minutes", 40),
                disabled=active_session)
            if st.button("Save profile", disabled=active_session):
                if not name.strip():
                    st.error("Enter a name before saving the profile.")
                else:
                    st.session_state.profile = {
                        "name": name.strip(),
                        "role": role.strip(),
                        "months": int(months),
                        "minutes": int(minutes),
                        "topics": profile0.get("topics", {}),
                        "current_topic": profile0.get("current_topic"),
                        "last_gaps": profile0.get("last_gaps", []),
                        "publish": profile0.get("publish"),
                    }
                    save_profile()
                    st.rerun()

        profile = st.session_state.profile
        if profile:
            st.subheader("Captured topics")
            if profile.get("topics"):
                for topic, status in profile["topics"].items():
                    st.write(f"{STATUS_ICON.get(status, '⚪')} {topic}")
            else:
                st.caption("Topics will be added as they come up in interviews.")

            if st.session_state.session is None:
                if st.button("▶ Start open-topic interview", type="primary"):
                    try:
                        with st.spinner("Starting..."):
                            start_session()
                    except Exception as exc:
                        st.session_state.session = None
                        st.error(f"Could not start: {exc}")
                    else:
                        st.rerun()

            else:
                phase = st.session_state.session.get("phase", "interview")
                if phase == "ready_to_end":
                    if st.button("■ Complete session + coverage check"):
                        try:
                            with st.spinner("Checking coverage..."):
                                end_session()
                        except Exception as exc:
                            st.error(f"Coverage check failed (session is still saved): {exc}")
                        else:
                            st.rerun()
                elif phase == "final_answer":
                    st.caption("Answer the final open-ended question, then complete the session.")
                elif st.button("■ Ask final open-ended question"):
                    try:
                        with st.spinner("Preparing the final question..."):
                            run_turn(
                                "Ask the final open-ended question now.",
                                hidden=True,
                                turn_mode="final_question",
                            )
                    except Exception as exc:
                        st.error(f"Could not prepare the final question: {exc}")
                    else:
                        st.rerun()

    st.title("Capture Knowledge")
    profile = st.session_state.profile
    if not profile:
        st.info("Create a retiree profile in the sidebar to begin.")
        return

    view = st.radio(
        "View",
        ["Interview", "Review notes", "Publish to Matcha", "Export"],
        horizontal=True,
        label_visibility="collapsed",
    )

    if view == "Interview":
        session = st.session_state.session
        if session is None:
            st.write(f"Ready to interview **{profile['name']}** ({profile['role']}).")
            if profile.get("last_gaps"):
                st.subheader("Suggested follow-ups from the last coverage check")
                for gap in profile["last_gaps"]:
                    st.write(f"- {gap}")
            history = list_sessions(profile["name"])
            if history:
                st.subheader("Interview history")
                for saved in history[:10]:
                    topic = (
                        saved.get("initial_topic")
                        or saved.get("current_topic")
                        or "Unknown topic"
                    )
                    started = time.strftime(
                        "%Y-%m-%d %H:%M",
                        time.localtime(saved.get("started", 0)),
                    )
                    status = "Completed" if saved.get("ended") else "Saved"
                    st.caption(
                        f"{started} · {topic} · "
                        f"{len(saved.get('notes', []))} notes · {status}"
                    )
        else:
            elapsed = (time.time() - session["started"]) / 60
            topic = session.get("current_topic") or "Choose a topic to discuss"
            st.caption(
                f"Topic: **{topic}** · "
                f"{elapsed:.0f}/{profile['minutes']} min · "
                f"{len(session['notes'])} notes this session"
            )
            for message in session["history"]:
                if message.get("hidden"):
                    continue
                if message["role"] == "assistant":
                    st.chat_message("assistant").write(
                        message.get("say") or message["content"])
                else:
                    st.chat_message("user").write(message["content"])
            st.info(
                "Using your voice to dictate answers is highly recommended. "
                "Select Dictate, speak your response, then select Send. You can also type. "
                "Dictation uses your browser's speech service, which may process audio; "
                "do not dictate sensitive information."
            )
            phase = session.get("phase", "interview")
            if phase == "ready_to_end":
                st.info("The final response is saved. Complete the session from the sidebar.")
            else:
                answer_event = dictation_input(
                    "Your answer",
                    "Share your answer or any additional documentation...",
                    key="interview_answer_input",
                )
                if (
                    isinstance(answer_event, dict)
                    and answer_event.get("text", "").strip()
                    and answer_event.get("submit_id")
                    != st.session_state.get("last_interview_submission")
                ):
                    prompt = answer_event["text"].strip()
                    st.chat_message("user").write(prompt)
                    try:
                        with st.spinner("..."):
                            run_turn(
                                prompt,
                                turn_mode=(
                                    "final_answer"
                                    if phase == "final_answer"
                                    else "interview"
                                ),
                            )
                    except Exception as exc:
                        st.error(f"Model call failed, please resend your answer: {exc}")
                    else:
                        st.session_state.last_interview_submission = answer_event["submit_id"]
                        st.rerun()

    elif view == "Review notes":
        st.write(
            "Confirm, edit, or reject each note. "
            "Only confirmed notes are published by default."
        )
        notes = all_notes(profile["name"])
        if not notes:
            st.info("No notes yet. End a session to move its notes here.")
        else:
            edited = st.data_editor(
                notes,
                num_rows="dynamic",
                column_config={
                    "review": st.column_config.SelectboxColumn(
                        "review", options=["pending", "confirmed", "rejected"]),
                    "text": st.column_config.TextColumn("note", width="large"),
                    "quote": st.column_config.TextColumn(
                        "retiree's words", width="large"),
                },
            )
            if st.button("Save review"):
                if hasattr(edited, "to_dict"):
                    edited = edited.to_dict("records")
                save_json(rdir(profile["name"]) / "notes.json", edited)
                st.success("Saved.")

    elif view == "Publish to Matcha":
        st.write(
            "Uploads one markdown file per topic, plus an overview, into a folder "
            "in a MatchaMission. Re-publishing updates the same files."
        )
        st.warning(
            "Publish to a test Mission first, and only with owner approval for production. "
            "Interview content can include sensitive details."
        )
        try:
            missions = [mission for mission in list_missions() if mission.get("canEdit")]
        except Exception as exc:
            st.error(f"Could not list Missions: {exc}")
            return
        if not missions:
            st.info("No Missions where you have edit rights were returned.")
            return
        prior = (profile.get("publish") or {}).get("mission_id") or DEFAULT_MISSION
        ids = [mission["id"] for mission in missions]
        mission_id = st.selectbox(
            "Target Mission",
            ids,
            index=ids.index(prior) if prior in ids else 0,
            format_func=lambda mission_id: next(
                f"{mission['name']} ({mission.get('workspaceName') or 'no workspace'})"
                for mission in missions if mission["id"] == mission_id
            ),
        )
        include_pending = st.checkbox(
            "Also publish notes still marked pending (unreviewed)", value=False)

        notes = all_notes(profile["name"])
        allowed = {"confirmed"} | ({"pending"} if include_pending else set())
        usable = [note for note in notes if note.get("review") in allowed]
        counts = {}
        for note in usable:
            topic = note.get("topic") or "Other"
            counts[topic] = counts.get(topic, 0) + 1
        st.write(
            f"**{len(usable)}** notes will be published across "
            f"**{len(counts)}** topic files."
        )
        for topic, count in counts.items():
            st.write(f"- {topic}: {count}")

        phi_ok = st.checkbox(
            "I reviewed these notes and they contain no PHI/PII or credentials")
        if st.button(
            "Publish", type="primary", disabled=not (phi_ok and usable)
        ):
            try:
                with st.spinner("Uploading and waiting for indexing..."):
                    results = publish(profile, mission_id, include_pending)
            except Exception as exc:
                st.error(f"Publish failed: {exc}")
            else:
                st.success("Published.")
                st.dataframe(results)
                if any(result["warnings"] or not result["indexed"] for result in results):
                    st.warning(
                        "Some files had warnings or were still indexing. "
                        "Check before relying on queries."
                    )

    elif view == "Export":
        notes = [
            note for note in all_notes(profile["name"])
            if note.get("review") != "rejected"
        ]
        markdown = [f"# Knowledge base: {profile['name']} ({profile['role']})", ""]
        for topic in profile["topics"]:
            items = [note for note in notes if note.get("topic") == topic]
            if items:
                markdown.append(f"## {topic}")
                markdown += [
                    f"- {'✔ ' if note.get('review') == 'confirmed' else ''}"
                    f"{note.get('text') if isinstance(note.get('text'), str) else ''}"
                    for note in items
                ]
                markdown.append("")
        output = "\n".join(markdown)
        st.download_button(
            "Download Markdown",
            output,
            file_name=f"{slug(profile['name'])}-knowledge.md",
        )
        st.markdown(output)

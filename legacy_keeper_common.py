import json
import os
import re
import time
import uuid
from datetime import date, datetime
from pathlib import Path

import requests
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("MATCHAOS_BASE_URL", "https://matchaos.harriscomputer.com/api").rstrip("/")
API_KEY = os.getenv("MATCHAOS_API_KEY", "").strip()
MODEL = os.getenv("MATCHAOS_MODEL", "claude-sonnet-5-5")
RESPONSE_LLM = os.getenv("MATCHAOS_RESPONSE_LLM", "gemini.fastResponse")
DEFAULT_MISSION = os.getenv("MATCHAOS_MISSION_ID", "").strip()

DATA_DIR = Path("interview_data")
STATUS_ICON = {"untouched": "⚪", "thin": "🟡", "covered": "🟢"}
PUT_MAX_BYTES = 140_000
DICTATION_INPUT = components.declare_component(
    "legacy_keeper_dictation_input",
    path=str(Path(__file__).parent / "components" / "dictation_input"),
)

SYSTEM_TEMPLATE = """You are a knowledge-capture interviewer. You are interviewing {name}, a {role} who is retiring in {months} months. Your goal is to capture what they know so a successor can use it later.

Method:
- Current topic: "{current_topic}". Keep a consistent, concise topic label for notes. If the person changes subjects, update the topic label to match.
- Prefer real incidents over general questions. Probe for what they noticed, options considered, actions taken, and what a new person might miss.
- Ask ONE question at a time. Keep every turn to 1-2 sentences.
- Follow up on vague answers ("it depends", "you just know") by asking for a concrete example.
- Occasionally play a curious new hire: "Why not just do X?"
- Every ~10 turns, briefly summarize what you heard and ask them to correct it.
- Never supply facts yourself. You are capturing their knowledge, not adding to it.
- Do not ask for or record patient names or other PHI/PII; if the retiree starts to give some, steer them to describe the situation generically.
- Session length target: {minutes} minutes. Elapsed: {elapsed:.0f} minutes.
{turn_instruction}

Previously captured topics and coverage:
{topic_map}

Respond with ONLY a JSON object, no markdown fences:
{{"say": "your next question or remark",
  "topic": "the topic this turn is about",
  "notes": ["facts/rules of thumb/gotchas/contacts learned from the retiree's LAST answer, in their own words; empty list if none"],
  "topic_status": "thin" or "covered" or null,
  "switch_to": "topic label to move to next, or null"}}"""

COVERAGE_PROMPT = """Below is a topic map and the interview notes captured so far for {name}.
Rate each topic's coverage depth: "untouched" (nothing captured), "thin" (a little, lacking concrete incidents or reasoning), or "covered" (concrete incidents, reasoning, and gotchas captured).
Also list up to 5 specific follow-up questions that would fill the biggest gaps.

Topics: {topics}

Notes:
{notes}

Respond with ONLY JSON: {{"statuses": {{"<topic>": "untouched|thin|covered"}}, "gaps": ["..."]}}"""

QUERY_CONTEXT = (
    "The documents are knowledge-capture notes from a retired employee, grouped by topic. "
    "Answer ONLY from those documents. Name the topic file you drew from and say whether the "
    "entry is marked confirmed by the retiree. Quote the relevant note briefly. If the documents "
    "do not cover the question, say the retiree did not cover it. Never guess or add outside knowledge."
)


def _headers():
    return {
        "Authorization": f"Bearer {API_KEY}",
        "matcha-api-key": API_KEY,
        "User-Agent": "MatchaOS-SDK/1.0",
    }


def request(method, path, **kw):
    kw.setdefault("timeout", (10, 120))
    return requests.request(method, f"{BASE_URL}{path}", headers=_headers(), **kw)


def check(response, what):
    if response.status_code >= 400:
        raise RuntimeError(f"{what}: HTTP {response.status_code} {response.text[:200]}")
    return response


def call_model(system, messages, max_tokens=1000):
    payload = {
        "model": MODEL,
        "max_completion_tokens": max_tokens,
        "reasoning_effort": "low",
        "messages": [{"role": "system", "content": system}] + messages,
    }
    data = check(request("POST", "/v1/chat/completions", json=payload), "chat").json()
    if "error" in data:
        raise RuntimeError(f"chat: {data['error']}")
    choice = data["choices"][0]
    text = (choice.get("message") or {}).get("content") or ""
    if choice.get("finish_reason") == "length":
        raise RuntimeError("Answer truncated at max_completion_tokens")
    if not text.strip():
        raise RuntimeError("Model returned an empty answer")
    return text


@st.cache_data(ttl=300, show_spinner=False)
def list_missions():
    out, offset = [], 0
    while True:
        data = check(
            request("GET", "/v1/missions", params={"limit": 20, "offset": offset}),
            "list missions",
        ).json()
        out += data["data"]
        if not data.get("hasMore"):
            return out
        offset += 20


def ensure_folder(mission_id, name, description):
    offset = 0
    while True:
        data = check(
            request("GET", f"/v1/missions/{mission_id}/folders",
                    params={"limit": 100, "offset": offset}),
            "list folders",
        ).json()
        for folder in data["data"]:
            if folder["name"] == name and not folder.get("isSystem"):
                return folder["id"]
        if not data.get("hasMore"):
            break
        offset += 100
    response = check(
        request("POST", f"/v1/missions/{mission_id}/folders",
                json={"name": name, "description": description}),
        "create folder",
    )
    return response.json()["id"]


def list_files(folder_id):
    files, offset, limit = [], 0, 20
    while True:
        response = request(
            "GET", f"/v1/folders/{folder_id}/files",
            params={"limit": limit, "offset": offset},
        )
        if response.status_code == 503 and limit > 1:
            limit = max(1, limit // 2)
            continue
        data = check(response, "list files").json()
        files += data["data"]
        if not data.get("hasMore"):
            return files
        offset += limit


def wait_indexed(file_id, timeout=45):
    end = time.time() + timeout
    while time.time() < end:
        data = check(request("GET", f"/v1/files/{file_id}"), "get file").json()
        if data.get("indexed"):
            return True
        time.sleep(2)
    return False


def upsert_markdown(folder_id, existing, filename, content):
    data = content.encode("utf-8")
    part = {"file": (filename, data, "text/markdown")}
    old = existing.get(filename)
    if old is None:
        response = check(
            request("POST", f"/v1/folders/{folder_id}/files", files=part), "upload")
        action = "created"
    elif len(data) < PUT_MAX_BYTES:
        response = check(
            request("PUT", f"/v1/files/{old['id']}/content", files=part), "replace")
        action = "replaced"
    else:
        check(request("DELETE", f"/v1/files/{old['id']}"), "delete old")
        response = check(
            request("POST", f"/v1/folders/{folder_id}/files", files=part), "upload")
        action = "re-created"
    file_id = response.json()["id"]
    warnings = response.headers.get("x-matcha-warnings", "")
    indexed = True if action == "replaced" else wait_indexed(file_id)
    return file_id, action, warnings, indexed


def ask_folder(folder_id, question, chat_history):
    payload = {
        "folder_id": folder_id,
        "input": question,
        "chat_history": chat_history[-18:],
        "context": QUERY_CONTEXT,
        "options": {"responseLLM": RESPONSE_LLM, "includeSources": True, "max_hits": 10},
    }
    response = check(request("POST", "/v1/completions", json=payload), "mission query")
    warnings = response.headers.get("x-matcha-warnings", "")
    data = response.json()
    if data.get("status") != "success":
        raise RuntimeError(f"Matcha error: {data.get('error', 'unknown')}")
    texts, sources = [], list(data.get("sources") or [])
    for output in data.get("output", []):
        for item in output.get("content", []):
            if item.get("type") == "output_text":
                texts.append(item.get("text", ""))
                sources += item.get("sources") or []
    return "\n".join(texts).strip(), sources, warnings


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-") or "item"


def s(value):
    return value if isinstance(value, str) else ""


def load_json(path, default):
    try:
        return json.loads(path.read_text()) if path.exists() else default
    except json.JSONDecodeError:
        return default


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False))
    tmp.replace(path)


def parse_json(text):
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {
        "say": text.strip(), "topic": None, "notes": [],
        "topic_status": None, "switch_to": None,
    }


def rdir(name):
    return DATA_DIR / slug(name)


def published_knowledge_bases():
    bases = []
    if not DATA_DIR.exists():
        return bases
    for path in sorted(DATA_DIR.iterdir()):
        if not path.is_dir():
            continue
        profile = load_json(path / "profile.json", None)
        if not isinstance(profile, dict):
            continue
        publication = profile.get("publish")
        if not isinstance(publication, dict) or not publication.get("folder_id"):
            continue
        bases.append({
            "key": path.name,
            "name": profile.get("name") or path.name,
            "role": profile.get("role", ""),
            "folder_id": publication["folder_id"],
        })
    return bases


def save_profile():
    profile = st.session_state.profile
    save_json(rdir(profile["name"]) / "profile.json", profile)


def all_notes(name):
    return load_json(rdir(name) / "notes.json", [])


def list_sessions(name):
    sessions_dir = rdir(name) / "sessions"
    if not sessions_dir.exists():
        return []
    sessions = [
        session
        for path in sessions_dir.glob("*.json")
        if isinstance((session := load_json(path, None)), dict)
    ]
    return sorted(sessions, key=lambda session: session.get("started", 0), reverse=True)


def persist_session():
    session, profile = st.session_state.session, st.session_state.profile
    save_json(rdir(profile["name"]) / "sessions" / f"{session['id']}.json", session)


def start_session():
    profile = st.session_state.profile
    session_id = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
    st.session_state.session = {
        "id": session_id,
        "started": time.time(),
        "history": [],
        "notes": [],
        "current_topic": None,
        "initial_topic": None,
        "phase": "interview",
        "notes_saved_count": 0,
    }
    run_turn("Begin the session.", hidden=True)


def run_turn(user_text, hidden=False, turn_mode="interview"):
    session, profile = st.session_state.session, st.session_state.profile
    session["history"].append({
        "role": "user", "content": user_text, "hidden": hidden, "ts": time.time(),
    })
    persist_session()

    elapsed = (time.time() - session["started"]) / 60
    topic_map = "\n".join(f"- {topic}: {status}" for topic, status in profile["topics"].items())
    if turn_mode == "final_question":
        turn_instruction = (
            "Ask one final, open-ended question inviting any additional knowledge, "
            "examples, documents, resources, people to consult, or discussion the "
            "person wants to share. Do not close the interview yet."
        )
    elif turn_mode == "final_answer":
        turn_instruction = (
            "This is the person's answer to the final open-ended question. Capture "
            "useful facts as notes, briefly thank them, and do not ask another question."
        )
    elif not session.get("current_topic"):
        turn_instruction = (
            "This is the opening of a new interview. Ask exactly what topic they "
            "would like to discuss today. Do not assume a topic or ask a second question."
        )
    else:
        turn_instruction = ""
    system = SYSTEM_TEMPLATE.format(
        name=profile["name"], role=profile["role"], months=profile["months"],
        minutes=profile["minutes"],
        current_topic=session.get("current_topic") or "not chosen yet",
        elapsed=elapsed, turn_instruction=turn_instruction, topic_map=topic_map,
    )
    api_messages = [
        {"role": message["role"], "content": message["content"]}
        for message in session["history"]
    ]
    try:
        raw = call_model(system, api_messages, max_tokens=800)
    except Exception:
        session["history"].pop()
        persist_session()
        raise
    turn = parse_json(raw)
    session["history"].append({
        "role": "assistant", "content": raw, "say": turn.get("say", ""), "ts": time.time(),
    })
    model_topic = turn.get("topic")
    if isinstance(model_topic, str):
        model_topic = model_topic.strip()
    else:
        model_topic = ""
    topic = (
        None
        if hidden and turn_mode == "interview" and not session.get("current_topic")
        else model_topic or session.get("current_topic")
    )
    if not topic and not hidden:
        topic = user_text.strip().rstrip(".!?")[:80] or "General discussion"
    if topic:
        session["current_topic"] = topic
        if not session.get("initial_topic"):
            session["initial_topic"] = topic
        profile["topics"].setdefault(topic, "untouched")
    quote = "" if hidden else user_text[:800]
    if not hidden:
        for note in turn.get("notes") or []:
            session["notes"].append({
                "topic": topic or "General discussion",
                "text": note, "quote": quote, "session": session["id"],
            })

    if turn_mode == "final_question":
        session["phase"] = "final_answer"
    elif turn_mode == "final_answer":
        session["phase"] = "ready_to_end"
    elif turn.get("topic_status") in ("thin", "covered") and topic in profile["topics"]:
        if profile["topics"][topic] != "covered":
            profile["topics"][topic] = turn["topic_status"]
    switch_to = turn.get("switch_to")
    if turn_mode == "interview" and isinstance(switch_to, str) and switch_to.strip():
        session["current_topic"] = switch_to.strip()
        profile["topics"].setdefault(session["current_topic"], "untouched")
        session["initial_topic"] = session.get("initial_topic") or session["current_topic"]
    profile["current_topic"] = session.get("current_topic")
    save_profile()
    persist_session()


def end_session():
    session, profile = st.session_state.session, st.session_state.profile
    master = all_notes(profile["name"])
    saved_count = session.get("notes_saved_count", 0)
    if saved_count < len(session["notes"]):
        master += [
            {**note, "review": "pending"}
            for note in session["notes"][saved_count:]
        ]
        save_json(rdir(profile["name"]) / "notes.json", master)
        session["notes_saved_count"] = len(session["notes"])
        persist_session()

    notes_text = "\n".join(f"[{note['topic']}] {note['text']}" for note in master) or "(none)"
    raw = call_model(
        "You are a careful analyst. Output only JSON.",
        [{"role": "user", "content": COVERAGE_PROMPT.format(
            name=profile["name"], topics=list(profile["topics"]), notes=notes_text,
        )}],
        max_tokens=1500,
    )
    result = parse_json(raw)
    for topic, status in (result.get("statuses") or {}).items():
        if topic in profile["topics"] and status in STATUS_ICON:
            profile["topics"][topic] = status
    profile["last_gaps"] = result.get("gaps", [])
    save_profile()
    session["ended"] = time.time()
    persist_session()
    st.session_state.session = None


def topic_markdown(profile, topic, notes):
    lines = [
        f"# {topic}", "",
        f"Knowledge captured from {profile['name']} ({profile['role']}) in retirement interviews.",
        f"Published: {date.today().isoformat()}", "",
        "Each entry is something the retiree said. Entries marked confirmed were "
        "reviewed and approved by the retiree.", "",
    ]
    for note in notes:
        status = "confirmed" if note.get("review") == "confirmed" else "unreviewed"
        lines.append(f"- {s(note.get('text'))}")
        lines.append(f"  - Status: {status}")
        if s(note.get("session")):
            lines.append(f"  - Session: {note['session']}")
        if s(note.get("quote")):
            quote = " ".join(note["quote"].split())
            lines.append(f"  - Retiree's words: \"{quote}\"")
    return "\n".join(lines) + "\n"


def overview_markdown(profile):
    lines = [
        f"# Knowledge base overview: {profile['name']}", "",
        f"Role: {profile['role']}",
        f"Last published: {date.today().isoformat()}", "",
        "## Topic coverage", "",
    ]
    lines += [f"- {topic}: {status}" for topic, status in profile["topics"].items()]
    if profile.get("last_gaps"):
        lines += ["", "## Known gaps from the last coverage check", ""]
        lines += [f"- {gap}" for gap in profile["last_gaps"]]
    lines += [
        "", "Topics marked untouched or thin were not fully covered by the retiree. "
        "Say so rather than guessing.",
    ]
    return "\n".join(lines) + "\n"


def publish(profile, mission_id, include_pending):
    allowed = {"confirmed"} | ({"pending"} if include_pending else set())
    usable = [note for note in all_notes(profile["name"]) if note.get("review") in allowed]
    by_topic = {}
    for note in usable:
        by_topic.setdefault(note.get("topic") or "Other", []).append(note)

    folder_name = f"Retiree - {profile['name']}"
    folder_id = ensure_folder(
        mission_id, folder_name, f"Knowledge-capture interviews with {profile['name']}")
    existing = {file["name"]: file for file in list_files(folder_id)}
    files = [("00-overview.md", overview_markdown(profile))]
    files += [
        (f"{slug(topic)}.md", topic_markdown(profile, topic, notes))
        for topic, notes in by_topic.items()
    ]
    results = []
    for filename, content in files:
        _, action, warnings, indexed = upsert_markdown(
            folder_id, existing, filename, content)
        results.append({
            "file": filename,
            "action": action,
            "indexed": indexed,
            "warnings": warnings,
            "kb": round(len(content.encode()) / 1024, 1),
        })
    profile["publish"] = {
        "mission_id": mission_id,
        "folder_id": folder_id,
        "published": datetime.now().isoformat(timespec="seconds"),
    }
    save_profile()
    return results


def dictation_input(label, placeholder, key):
    return DICTATION_INPUT(
        label=label,
        placeholder=placeholder,
        key=key,
        default=None,
    )

# Legacy Keeper

Legacy Keeper is a Streamlit app for capturing, reviewing, and publishing
knowledge from experienced or retiring colleagues.

## Run locally

Use Python 3.11 or newer. From this folder, create and activate a virtual
environment, install dependencies, and configure the required MatchaOS settings:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set your MatchaOS API key and other required values. Never
commit `.env` or share its contents. Then start the app:

```powershell
python -m streamlit run .\retiree_interviewer_matcha.py
```

Open the local URL printed by Streamlit, usually `http://localhost:8501`.

## Documentation

See [USER_GUIDE.md](./USER_GUIDE.md) for interview workflows, review and
publishing steps, privacy notes, and Windows server pilot deployment guidance.

## Local data and privacy

Profiles, interview sessions, and notes are stored in the local
`interview_data` folder. This folder and local secrets are excluded from Git.
Back up this data securely; do not commit real interview data or API
credentials. Interview content is sent to the configured MatchaOS API for
processing.

The current app is intended for a controlled pilot. It does not provide
application-level user authentication or per-user authorization. Review the
deployment and privacy guidance in the user guide before sharing access.

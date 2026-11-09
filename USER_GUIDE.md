# Legacy Keeper User Guide

Legacy Keeper helps capture knowledge from experienced or retiring colleagues,
review the notes, and make approved knowledge searchable. This guide describes
the current app workflow.

## Start the app

From the project folder, run:

```powershell
python -m streamlit run .\retiree_interviewer_matcha.py
```

Streamlit prints a local URL, usually `http://localhost:8501`. Open it in your
browser. Keep the terminal running while you use the app.

## Create or load a person's profile

1. On the home page, choose **Capture Knowledge**.
2. In the sidebar, either select a person under **Load existing** or expand
   **New / edit profile** to create a profile.
3. Enter the person's name, role, time until retirement, and target session
   length, then choose **Save profile**. There is no topic list to prepare.

Use the same profile when returning to interview the same person. Each person's
profile, interview sessions, and notes are stored separately.

## Conduct multiple interviews

The interviewer asks what the person would like to discuss at the start of each
session. Topics are captured as they come up. A person can have as many sessions
as needed, including multiple sessions about the same topic.

1. Select the person in **Load existing**.
2. Select **Start open-topic interview**. The first question asks what topic
   they would like to discuss today.
3. Conduct the conversation. The app records topics and notes under this
   person's profile as the discussion unfolds.
4. When ready to wrap up, select **Ask final open-ended question**. The
   interviewer invites any additional knowledge, examples, documentation,
   resources, people to consult, or discussion.
5. Answer that final question. Then select **Complete session + coverage
   check** to save notes and check topic coverage.
6. To cover another subject, start another open-topic interview with the same
   person. They can choose a new subject or revisit one from an earlier session.

Captured topics appear in the sidebar, and completed and saved sessions appear
under **Interview history**. Session notes remain associated with the person
and topic, so different people can discuss similarly named topics without
sharing their notes.

### Recommended: dictate interview answers

Using your voice to dictate answers is highly recommended for a natural
interview. Select **Dictate**, speak your response, and select **Send**. You can
also type your response if you prefer or if dictation is unavailable. The
interviewer's questions and responses appear as text on screen. Dictation uses
your browser's speech service, which may process audio; do not dictate
sensitive information.

## Review notes

1. Open **Review notes**.
2. Review each note and its supporting quote.
3. Mark notes as **confirmed**, **pending**, or **rejected**, and edit or remove
   content as appropriate.
4. Select **Save review**.

Only confirmed notes are published by default. Review notes for accuracy and
appropriateness before sharing them.

## Publish knowledge

1. Open **Publish to Matcha**.
2. Choose a target Mission where you have edit rights.
3. Leave **Also publish notes still marked pending** unchecked unless you
   specifically intend to include unreviewed notes.
4. Review the notes and confirm they contain no PHI/PII or credentials by
   selecting the confirmation checkbox.
5. Select **Publish** and check the results and any indexing warnings.

Publishing updates the files for the person's knowledge base in the selected
Mission. Use a test Mission first and get the appropriate owner's approval
before publishing to production.

## Export notes

Open **Export** to preview and download the person's non-rejected notes as a
Markdown file.

## Find answers

From the home page, choose **Find Answers** to query knowledge bases that have
been published to Matcha. Check the returned sources and note-review status.

## Pilot deployment on a Windows server

The current app is a Streamlit application. Run it with Streamlit; Waitress is
a WSGI server and cannot directly host this app. If Waitress becomes a
requirement, the app will need to be migrated to a WSGI-compatible framework.

For an initial group of users, deploy a controlled pilot:

1. **Prepare the server.** Use a supported Windows Server machine and a
   dedicated folder for the application. Install a supported Python version
   and the exact application dependencies in a virtual environment. Record the
   Python version and dependency versions so the deployment can be reproduced.
2. **Configure secrets.** Provide the required MatchaOS settings through a
   protected environment configuration. Restrict access to the configuration
   and never place real API keys in source control, screenshots, logs, or this
   guide. Rotate any key that may have been exposed.
3. **Choose durable data storage.** The app currently stores interview
   profiles, sessions, and notes as JSON files in `interview_data` relative to
   its working directory. Ensure the service account can write there, back up
   the folder, and preserve it across application updates. Do not have separate
   server instances write to the same data folder; this file-based storage is
   not designed for concurrent multi-instance use.
4. **Run under a Windows service account.** Use a dedicated, non-administrator
   account with only the required folder and network permissions. Set the
   service working directory to the project folder so relative data paths
   resolve consistently. Use a Windows service wrapper such as WinSW or NSSM
   to run:

   ```powershell
   .\.venv\Scripts\python.exe -m streamlit run .\retiree_interviewer_matcha.py --server.headless true --server.address 127.0.0.1 --server.port 8501
   ```

   Configure the wrapper to start on boot, restart after unexpected exits, and
   write standard output and errors to access-controlled log files. Test the
   service while logged off; an interactive terminal run is not a substitute
   for verifying the Windows service.
5. **Add controlled network access.** For users on the server itself, open
   `http://127.0.0.1:8501`. For other users, put an approved HTTPS reverse
   proxy (for example, IIS configured for reverse proxy and WebSockets) in
   front of Streamlit. Keep Streamlit bound to `127.0.0.1`; do not expose port
   8501 directly to the network. Require organizational authentication and
   restrict access to the intended pilot group.
6. **Test with non-sensitive sample data.** Verify sign-in/access controls,
   interview creation, topic changes, note review, publishing to a test Mission,
   backups, and service restart behavior before inviting users. The current app
   does not provide user authentication or per-user authorization itself, so
   do not treat network placement alone as sufficient protection for sensitive
   or production use.

### Updating the pilot during active development

1. Announce a maintenance window and stop the Windows service before updating.
2. Back up `interview_data`, the protected configuration, and the currently
   deployed application version. Keep secrets out of the application backup
   if it is stored somewhere with broader access.
3. Deploy a reviewed, known version of the code and its dependencies. Avoid
   editing the running server's files directly; keep a copy of the last known
   working version so you can roll back.
4. Start the service and verify its logs and health in a browser. Test the
   changed workflow with non-sensitive data.
5. If validation fails, stop the service, restore the previous application
   version, and restart it. Restore data only if it was changed incompatibly;
   preserve a copy of current data before any restore.

For a small pilot, use one application instance with scheduled backups. Before
expanding access, assess authentication, authorization, privacy, audit logging,
data retention, backup recovery, and concurrent access. Consider moving
profiles and notes to a database before running multiple workers or instances.

## Privacy and troubleshooting

- Do not enter patient names, sensitive personal information, or credentials.
- Interview answers are sent to the configured MatchaOS API for processing.
  Notes are stored locally and are uploaded only when you publish.
- Browser dictation uses the browser's speech service, which may process audio.
  Avoid dictating sensitive information.
- If an interview answer fails to process, the app asks you to resend it.
- If coverage checking fails after a session, the session and notes are saved;
  you can retry the coverage check.

## Keeping this guide current

This guide reflects the current Streamlit interface. When workflows, labels, or
data handling change, update the relevant steps here along with the app change.

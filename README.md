# GitLab Review Tracker

A small Windows desktop application for coordinating code reviews on GitLab
merge requests. Reviewers can mark commits and changed files as reviewed,
see who has completed each review, and open the relevant GitLab diff in their
browser.

The application makes read-only GitLab API requests. Review state is stored as
JSON files in a shared directory, allowing a team to see one another's review
progress without requiring write access to GitLab.

## Features

- Browse the project's open merge requests and their commits.
- Track review status independently for each reviewer.
- Mark an entire commit or individual files as reviewed.
- Derive a commit's reviewers from reviewers of all of its files.
- Open a selected file's diff in the current merge request.
- Detect merge commits and explain when they have no direct diff.
- Refresh shared review state automatically every 30 seconds.
- Store the GitLab access token in a dedicated Settings window that can grow with future application settings.

## Requirements

- Windows
- Python 3.10 or later
- Tkinter, usually included with the standard Windows Python installer
- Network access to the GitLab instance and the shared review-state directory

## Installation

Create a virtual environment, install the dependency, and start the app:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

To activate the environment in a new PowerShell session, run:

```powershell
.venv\Scripts\Activate.ps1
```

## Getting Started

1. Open **Settings** and enter a Personal Access Token with the `read_api` scope.
2. Enter the GitLab project URL, for example `https://gitlab.example.com/group/project/.
3. Select **Fetch MRs**, then choose an open merge request.
4. Select a commit to load its changed files.
5. Double-click a commit or file row to toggle your review status. Reviewed
   rows are highlighted and list the reviewers' GitLab usernames.
6. Select **View diff** in a file row to open that file's merge request diff in
   the default browser.

Selecting a commit loads its file list on demand. File lists are cached in
memory for the current session. The review state is re-read from shared
storage every 30 seconds, so changes made by teammates appear automatically.

## Review State

Review state is scoped to a commit and merge request:

- Toggling a commit toggles the same state for all files in that commit.
- A commit is shown as reviewed by a user only when that user has reviewed
  every file in the commit.
- A file appearing in multiple commits has separate review state for each
  commit.
- A merge commit with no direct file changes can still be marked reviewed
  directly.

By default, state is stored under:

```text
\\vi.vector.int\user\Tmp\CT_DEM\gitlab-review-tracker
```

Override this location for local development or testing with
`GRT_STATE_ROOT`:

```powershell
$env:GRT_STATE_ROOT = "$PWD\.review-state"
python main.py
```

Each project and merge request gets its own JSON state file. Writes use a
temporary file followed by an atomic rename, so readers do not see partial
JSON documents. Concurrent updates use last-write-wins semantics.

## Configuration and Security

The refresh interval is configured in the Settings window. Set
`refresh interval seconds` to the number of seconds between shared-state
refreshes; values below one second are treated as one second.

| Variable | Default | Description |
| --- | ---: | --- |
| `GRT_STATE_ROOT` | The shared network path above | Root directory for review-state files |

The project URL and token are cached in
`%USERPROFILE%\.gitlab_review_tracker.json` as plain text. Protect this file
like a credential, or remove it when the token should no longer be cached.
Use a token with only `read_api`; the application does not call GitLab write
endpoints.

## GitLab API Usage

The client uses these read-only GitLab REST API resources:

- `GET /user`
- `GET /projects/:id`
- `GET /projects/:id/merge_requests`
- `GET /projects/:id/merge_requests/:iid/commits`
- `GET /projects/:id/repository/commits/:sha/diff`

For very large commits, GitLab may return more changes than the current
per-page limit. The client currently requests up to 100 results per endpoint.

## Known Limitations

- The application currently targets Windows and uses Tkinter for its UI.
- Review state is file-based rather than stored in GitLab, so the shared
  directory must be reachable and writable by every reviewer.
- The diff link opens GitLab's merge request diff view and uses GitLab's file
  anchor format. If that format changes, the diff still opens but may not
  scroll directly to the selected file.
- The token cache is intentionally simple and does not use the operating
  system credential store.

## Project Structure

| File | Purpose |
| --- | --- |
| `main.py` | Tkinter application and review workflow |
| `gitlab_client.py` | Read-only GitLab REST API client |
| `review_state_store.py` | Shared JSON review-state management |
| `requirements.txt` | Python dependencies |

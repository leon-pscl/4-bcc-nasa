- Branch `handoff`: no code; only new commits, never rewritten.
- inbox/<YYYY-MM-DD-HHMM>-<topic>.md: every message from Claude, saved verbatim when the owner
  pastes it. First line: "From: Claude (pasted by the owner)".
- reports/<YYYY-MM-DD-HHMM>-<topic>.md: one report per stopping point (end of a task, or a
  question you're blocked on). Never edited after it's pushed; corrections go in a new report.
- STATE.md, overwritten at every report: one table with task | branch | last commit |
  CI (run, conclusion) | merged into pascual (hash) | tag | status (working/waiting/done) |
  waiting on (Claude/owner/team lead/nothing). Then the data on the PC (latest date,
  data_version, snapshot) and the open questions (ID, one line, which report).
- Times in Asia/Manila. Commit messages: "inbox: <topic>", "report: <topic>", "state: update".
- The repo is public: never write the FIRMS MAP_KEY, a full FIRMS URL, `docker compose config`
  or `docker inspect` output, email addresses, tokens or other personal data.
- When blocked on a question, push the report and stop.

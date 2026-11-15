From: Claude (pasted by the owner), 15 Nov 2026 12:50

Two parts: (1) set up the handoff channel, (2) next steps from your two 12:38 reports.

## 1. Handoff channel

From now on you report on an orphan branch `handoff` in the repo, and Claude reads it there.
Claude can't push; its messages reach you through the owner.

1. Create the orphan branch `handoff` in its own worktree, so your other work isn't touched.
2. Add README.md (the protocol below, verbatim), STATE.md, and the folders inbox/ and reports/.
3. Save this message verbatim as inbox/2026-11-15-1250-handoff-and-next-steps.md.
4. Backfill your two 12:38 reports (fix/disk-space and fix/map-draw) as
   reports/2026-11-15-1238-fix-disk-space.md and reports/2026-11-15-1238-fix-map-draw.md,
   in the template below.
5. Write STATE.md and push `handoff`. Never merge, rebase or force-push it.
   It has no .github/workflows, so pushes there don't run CI.

### Protocol (README.md)

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

Report template:

  # Report: <topic>, <YYYY-MM-DD HH:MM>
  Task: <task name, or the inbox file it answers>
  Branch and commits: <branch> <hash> <one line each>; merged into pascual at <hash> (or "not merged")
  CI: <run number and conclusion per pushed commit>, or "not checked"
  Tests: <pytest / npm run check summary>; new tests: <names>
  Numbers: <every number the task asks for, with units>
  Done:
  Not done (and why):
  Deviations from the task:
  Risks:
  Questions for Claude:
    Q-<YYYYMMDD>-<n>: <question>. Options: <a>, <b>. Recommended: <x>. Meanwhile: <what you do, or "stopped">
  Next: <what you do next, or "waiting for Q-...">

## 2. Next steps, in this order

A. fix/disk-space: add the C2 guard on the same branch before merging. The sweep empties
   DUCKDB_TEMP_DIR every run, so a wrong setting must not be able to delete other files.
   - At startup, refuse a DUCKDB_TEMP_DIR that is "/", "/tmp", the home folder, or DATA_RAW or
     DATA_PROCESSED or anything inside or above them.
   - Refuse one whose last folder name doesn't contain "duckdb".
   - Tests: each of those is refused with a clear message; "/tmp/duckdb" is accepted.
   Then, with CI green on the final commit, merge into pascual. Put the section 1 numbers and the
   correct ${DATA_DIR:-./data} text in the merge commit message (single-quote it in the shell).
   Report the merge hash and the CI run.

B. Tags: add an annotated tag v1-southeast-asia on f14a797, an alias of
   checkpoint/pre-major-changes-2026-11-15, and push it. Don't move or delete any existing tag.

C. Data snapshot for v1. It only adds hard links, so it's non-destructive. Do it only while no
   pipeline is running, and before any pipeline run after the merge:
   - Hard-link every file of E:\datasets\processed into E:\snapshots\v1-southeast-asia\processed.
   - Leave out _staging, _part_* and _writer.lock.
   - Write a SHA-256 checksum list to E:\snapshots\v1-southeast-asia\manifest.csv.
   - Report the file count, the total size and the data_version.
   If anything about this looks different on the PC from what's described, stop and ask.

D. Raw CSVs (49.10 GB in raw/manual): read-only checks, delete nothing. Report one table:
   - each subfolder's size, and what the download is (a repeated request, another region,
     or something else)
   - whether each CSV has its zip next to it, with a matching SHA-256 in a manifest
   - whether each CSV is in the ingest state with its rows published

E. Map follow-ups:
   (a) Replace JSON.stringify(state.area) in the outside-change check with an areaKey() helper
       that builds the key in a fixed order, with a test. Branch fix/area-key, after A.
   (b) Rule from now on: stop only the processes you started (by PID), never by name or
       "all python". In the report, say whether anything else was running when you stopped
       them earlier.

F. Then fix/c1-slim (3E), branched off pascual after A merges: the code, the tests and the
   migration script, checked on sample and synthetic data. Don't run the migration on
   E:\datasets until Claude says so; it runs right before the grid-edge rebuild.

Report after A–D, then carry on with E(a) and F.

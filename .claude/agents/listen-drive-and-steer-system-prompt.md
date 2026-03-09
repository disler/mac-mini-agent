# Job Reporting

Complete the work detailed to you end to end while tracking progress and marking your task complete with a summary message when you're done.

You are running as job `{{JOB_ID}}`. Your job file is at `apps/listen/jobs/{{JOB_ID}}.yaml`.

## Workflows

You have three workflows: `Work & Progress Updates`, `Summary`, and `Clean Up`.
**All three are mandatory.** The job is not complete until all three are done.

### 1. Work & Progress Updates

First and foremost - accomplish the task at hand.
Execute the task until it is complete.
You're operating fully autonomously, your results should reflect that.

Periodically append a single-sentence status update to the `updates` list in your job YAML file.
Do this after completing meaningful steps — not every tool call, but at natural checkpoints.

Example — read the file, append to the updates list, write it back:

```bash
# Use yq to append an update (keeps YAML valid)
yq -i '.updates += ["Set up test environment and installed dependencies"]' apps/listen/jobs/{{JOB_ID}}.yaml
```

### 2. Summary

When you have finished all work, write a concise summary of everything you accomplished
to the `summary` field in the job YAML file.

```bash
yq -i '.summary = "Opened Safari, captured accessibility tree with 42 elements, saved screenshot to /tmp/steer/a1b2c3d4.png"' apps/listen/jobs/{{JOB_ID}}.yaml
```

### 3. Clean Up

**This step is mandatory — do not skip it.** After writing your summary, run cleanup before you finish.

Before starting your task, note which apps are already running so you know what to close afterward:
```bash
osascript -e 'tell application "System Events" to get name of every process whose background only is false'
```

Clean up everything you created:

- **Kill tmux sessions you created** — `drive session kill <name>` — only sessions YOU created, not your own job session
- **Close apps you opened** that were not already running before your task — use `osascript -e 'quit app "AppName"'`
- **Remove temp files** you wrote to `/tmp/` — `rm /tmp/steer-* /tmp/your-files`
- **Close extra windows** — if an app was already running, close only the windows you opened
- **Remove idle coding instances** — close any Claude Code, PI, Gemini, Codex, or OpenCode windows just sitting doing nothing

After cleanup, append a final update confirming cleanup is done:
```bash
yq -i '.updates += ["Cleanup complete — closed opened apps and removed temp files"]' apps/listen/jobs/{{JOB_ID}}.yaml
```

Do NOT kill your own job session (`job-{{JOB_ID}}`) — the worker process handles that.

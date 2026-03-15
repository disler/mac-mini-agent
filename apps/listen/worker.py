"""Job worker — runs a Claude Code agent in a visible Terminal window.

Creates a headed tmux session, sends the claude command with sentinel
markers, polls for completion, then updates the job YAML.
"""

import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

SENTINEL_PREFIX = "__JOBDONE_"
POLL_INTERVAL = 2.0


def _tmux(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a tmux command."""
    return subprocess.run(["tmux", *args], capture_output=True, text=True, check=check)


def _session_exists(name: str) -> bool:
    result = _tmux("has-session", "-t", name, check=False)
    return result.returncode == 0


def _open_terminal(session_name: str, cwd: str) -> None:
    """Open a new Terminal.app window with a tmux session attached."""
    tmux_cmd = f"cd '{cwd}' && tmux new-session -A -s {session_name}"
    escaped = tmux_cmd.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run(
        ["osascript", "-e", f'tell application "Terminal" to do script "{escaped}"'],
        capture_output=True,
        text=True,
    )
    # Wait for session to appear
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if _session_exists(session_name):
            return
        time.sleep(0.2)
    raise RuntimeError(f"tmux session '{session_name}' did not appear within 5s")


def _send_keys(session: str, keys: str) -> None:
    """Send keys to tmux session then press Enter."""
    _tmux("send-keys", "-t", f"{session}:", keys)
    _tmux("send-keys", "-t", f"{session}:", "Enter")


def _capture_pane(session: str) -> str:
    result = _tmux("capture-pane", "-p", "-t", f"{session}:", "-S", "-500")
    return result.stdout


def _wait_for_sentinel(session: str, token: str) -> int:
    """Poll until sentinel appears. No timeout — waits forever."""
    pattern = re.compile(
        rf"^{re.escape(SENTINEL_PREFIX)}{token}:(\d+)\s*$", re.MULTILINE
    )
    while True:
        time.sleep(POLL_INTERVAL)
        captured = _capture_pane(session)
        match = pattern.search(captured)
        if match:
            return int(match.group(1))


def main():
    if len(sys.argv) < 3:
        print("Usage: worker.py <job_id> <prompt>")
        sys.exit(1)

    job_id = sys.argv[1]
    prompt = sys.argv[2]

    jobs_dir = Path(__file__).parent / "jobs"
    job_file = jobs_dir / f"{job_id}.yaml"

    if not job_file.exists():
        print(f"Job file not found: {job_file}")
        sys.exit(1)

    repo_root = Path(__file__).parent.parent.parent
    sys_prompt_file = (
        repo_root / ".claude" / "agents" / "listen-drive-and-steer-system-prompt.md"
    )
    sys_prompt = sys_prompt_file.read_text().replace("{{JOB_ID}}", job_id)

    # Write system prompt to a temp file to avoid shell escaping issues
    sys_prompt_tmp = Path(f"/tmp/steer-sysprompt-{job_id}.txt")
    sys_prompt_tmp.write_text(sys_prompt)

    # Write user prompt to a temp file to avoid tmux send-keys truncation
    prompt_tmp = Path(f"/tmp/steer-prompt-{job_id}.txt")
    prompt_tmp.write_text(f"/listen-drive-and-steer-user-prompt {prompt}")

    session_name = f"job-{job_id}"
    token = uuid.uuid4().hex[:8]

    # Build the claude command — read prompt from file to avoid truncation
    claude_cmd = (
        f"claude --dangerously-skip-permissions --print"
        f' --append-system-prompt "$(cat {sys_prompt_tmp})"'
        f' "$(cat {prompt_tmp})"'
    )

    # Wrap with sentinel: <cmd> ; echo "__JOBDONE_<token>:$?"
    wrapped = f'{claude_cmd} ; echo "{SENTINEL_PREFIX}{token}:$?"'

    start_time = time.time()

    # Strip CLAUDECODE from env so nested claude doesn't conflict
    env_clean = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    os.environ.clear()
    os.environ.update(env_clean)

    try:
        # Open headed Terminal window with tmux session
        _open_terminal(session_name, str(repo_root))

        # Send the wrapped command
        _send_keys(session_name, wrapped)

        # Update job with session info
        with open(job_file) as f:
            data = yaml.safe_load(f)
        data["session"] = session_name
        with open(job_file, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        # Wait for completion — no timeout
        exit_code = _wait_for_sentinel(session_name, token)

    except Exception as e:
        exit_code = 1
        print(f"Worker error: {e}", file=sys.stderr)

    duration = round(time.time() - start_time)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with open(job_file) as f:
        data = yaml.safe_load(f)

    data["status"] = "completed" if exit_code == 0 else "failed"
    data["exit_code"] = exit_code
    data["duration_seconds"] = duration
    data["completed_at"] = now

    with open(job_file, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    # Clean up
    sys_prompt_tmp.unlink(missing_ok=True)
    prompt_tmp.unlink(missing_ok=True)
    if _session_exists(session_name):
        _tmux("kill-session", "-t", session_name, check=False)


if __name__ == "__main__":
    main()

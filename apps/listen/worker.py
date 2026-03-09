"""Job worker — runs a Claude Code agent in a visible Terminal window.

Creates a headed tmux session, sends the claude command with sentinel
markers, polls for completion, then updates the job YAML.
"""

import fcntl
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

SENTINEL_PREFIX = "__JOBDONE_"
POLL_INTERVAL = 2.0
JOB_TIMEOUT_SECONDS = 3600  # 1 hour max per job


def _tmux(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a tmux command."""
    tmux_bin = shutil.which("tmux")
    if tmux_bin is None:
        raise RuntimeError("tmux not found in PATH")
    return subprocess.run([tmux_bin, *args], capture_output=True, text=True, check=check)


def _session_exists(name: str) -> bool:
    result = _tmux("has-session", "-t", name, check=False)
    return result.returncode == 0


def _open_terminal(session_name: str, cwd: str) -> None:
    """Open a new Terminal.app window with a tmux session attached.

    Writes a temporary shell script instead of embedding the command
    directly in the AppleScript string, eliminating AppleScript injection
    via special characters in cwd or session_name.
    """
    tmux_bin = shutil.which("tmux") or "tmux"
    script_content = (
        "#!/bin/sh\n"
        f"cd {shlex.quote(cwd)} && "
        f"{shlex.quote(tmux_bin)} new-session -A -s {shlex.quote(session_name)}\n"
    )
    fd, script_path = tempfile.mkstemp(suffix=".sh", prefix="steer-term-")
    try:
        os.write(fd, script_content.encode())
        os.close(fd)
        os.chmod(script_path, stat.S_IRWXU)  # 0o700 — owner-execute only
        # script_path is a system-generated path; safe to embed after quote-escaping
        escaped_path = script_path.replace("\\", "\\\\").replace('"', '\\"')
        subprocess.run(
            [
                "osascript",
                "-e", 'tell application "Terminal" to activate',
                "-e", f'tell application "Terminal" to do script "{escaped_path}"',
            ],
            capture_output=True,
            text=True,
        )
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise

    # Wait for session to appear
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if _session_exists(session_name):
            Path(script_path).unlink(missing_ok=True)
            return
        time.sleep(0.2)
    Path(script_path).unlink(missing_ok=True)
    raise RuntimeError(f"tmux session '{session_name}' did not appear within 5s")


def _send_keys(session: str, keys: str) -> None:
    """Send keys to tmux session then press Enter."""
    _tmux("send-keys", "-t", f"{session}:", keys)
    _tmux("send-keys", "-t", f"{session}:", "Enter")


def _capture_pane(session: str) -> str:
    result = _tmux("capture-pane", "-p", "-t", f"{session}:", "-S", "-500")
    return result.stdout


def _wait_for_sentinel(session: str, token: str, timeout: float = JOB_TIMEOUT_SECONDS) -> int:
    """Poll until sentinel appears or timeout is reached."""
    pattern = re.compile(
        rf"^{re.escape(SENTINEL_PREFIX)}{token}:(\d+)\s*$", re.MULTILINE
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL)
        captured = _capture_pane(session)
        match = pattern.search(captured)
        if match:
            return int(match.group(1))
    raise TimeoutError(f"Job timed out after {timeout}s")


def _read_job_file(job_file: Path) -> dict:
    """Read job YAML with shared file lock."""
    with open(job_file) as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
        return yaml.safe_load(f)


def _write_job_file(job_file: Path, data: dict) -> None:
    """Write job YAML with exclusive file lock."""
    with open(job_file, "r+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        f.seek(0)
        f.truncate()
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def main():
    if len(sys.argv) < 2:
        print("Usage: worker.py <job_id>")
        sys.exit(1)

    job_id = sys.argv[1]

    # Validate job_id format before any filesystem use
    if not re.match(r"^[0-9a-f]{8}$", job_id):
        print(f"Invalid job_id format: {job_id}", file=sys.stderr)
        sys.exit(1)

    repo_root = Path(__file__).parent.parent.parent

    # Load env vars BEFORE any reference to anthropic_key
    env_clean = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    os.environ.clear()
    os.environ.update(env_clean)

    from dotenv import load_dotenv
    load_dotenv(repo_root / ".env")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    jobs_dir = Path(__file__).parent / "jobs"
    job_file = jobs_dir / f"{job_id}.yaml"

    if not job_file.exists():
        print(f"Job file not found: {job_file}", file=sys.stderr)
        sys.exit(1)

    # Read prompt from YAML — not from argv (argv is visible in ps aux)
    job_data = _read_job_file(job_file)
    prompt = job_data.get("prompt", "")

    sys_prompt_file = (
        repo_root / ".claude" / "agents" / "listen-drive-and-steer-system-prompt.md"
    )
    sys_prompt = sys_prompt_file.read_text().replace("{{JOB_ID}}", job_id)

    # Create temp files with O_EXCL + 0o600 (no TOCTOU, owner-only readable)
    sys_fd, sys_prompt_path = tempfile.mkstemp(prefix=f"steer-sys-{job_id}-", suffix=".txt")
    try:
        os.write(sys_fd, sys_prompt.encode())
    finally:
        os.close(sys_fd)
    os.chmod(sys_prompt_path, stat.S_IRUSR | stat.S_IWUSR)

    prompt_fd, prompt_path = tempfile.mkstemp(prefix=f"steer-prompt-{job_id}-", suffix=".txt")
    try:
        os.write(prompt_fd, f"/listen-drive-and-steer-user-prompt {prompt}".encode())
    finally:
        os.close(prompt_fd)
    os.chmod(prompt_path, stat.S_IRUSR | stat.S_IWUSR)

    sys_prompt_tmp = Path(sys_prompt_path)
    prompt_tmp = Path(prompt_path)

    session_name = f"job-{job_id}"
    token = uuid.uuid4().hex[:8]

    # Build claude command — API key is NOT embedded in the command string
    claude_cmd = (
        f"claude --dangerously-skip-permissions"
        f' --append-system-prompt "$(cat {shlex.quote(sys_prompt_path)})"'
        f' "$(cat {shlex.quote(prompt_path)})"'
    )
    wrapped = f'{claude_cmd} ; echo "{SENTINEL_PREFIX}{token}:$?"'

    start_time = time.time()

    try:
        _open_terminal(session_name, str(repo_root))

        # Inject API key into the tmux session environment — NOT in the command string.
        # This prevents the key from appearing in scrollback or capture-pane output.
        if anthropic_key:
            _tmux("setenv", "-t", session_name, "ANTHROPIC_API_KEY", anthropic_key)
            _tmux("setenv", "-t", session_name, "CLAUDE_API_KEY", anthropic_key)

        _send_keys(session_name, wrapped)

        # Update job with session info (locked write)
        data = _read_job_file(job_file)
        data["session"] = session_name
        _write_job_file(job_file, data)

        exit_code = _wait_for_sentinel(session_name, token)

    except Exception as e:
        exit_code = 1
        print(f"Worker error: {e}", file=sys.stderr)

    duration = round(time.time() - start_time)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    data = _read_job_file(job_file)
    data["status"] = "completed" if exit_code == 0 else "failed"
    data["exit_code"] = exit_code
    data["duration_seconds"] = duration
    data["completed_at"] = now
    _write_job_file(job_file, data)

    sys_prompt_tmp.unlink(missing_ok=True)
    prompt_tmp.unlink(missing_ok=True)
    if _session_exists(session_name):
        _tmux("kill-session", "-t", session_name, check=False)


if __name__ == "__main__":
    main()

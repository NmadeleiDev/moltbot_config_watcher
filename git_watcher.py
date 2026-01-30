#!/usr/bin/env python3
import json
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import requests
from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer

from config import load_config

DEBOUNCE_SECONDS = 2.0
LOG_NAME = "git_watcher"
HEALTH_CHECK_INTERVAL = 30  # seconds
MAX_EVENT_AGE = 60  # seconds - force commit if events pending too long
POLLING_INTERVAL = 10  # seconds - fallback polling mode


class DebouncedHandler(PatternMatchingEventHandler):
    def __init__(self, on_change, patterns=None):
        # Default to watching only .md files if no patterns specified
        if patterns is None:
            patterns = ["*.md"]
        super().__init__(patterns=patterns, ignore_patterns=None, ignore_directories=True)
        self._on_change = on_change
        self._timer = None
        self._lock = threading.Lock()
        self._last_event_time = None

    def on_any_event(self, event):
        # PatternMatchingEventHandler already filters by pattern and ignores directories
        with self._lock:
            self._last_event_time = time.time()
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(DEBOUNCE_SECONDS, self._on_change)
            self._timer.daemon = True
            self._timer.start()

    def get_last_event_time(self):
        with self._lock:
            return self._last_event_time


def run_git(args, repo_path, timeout=30, env=None):
    cmd = ["git", "-C", repo_path] + args
    # Merge any additional env vars
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=run_env,
    )


def get_diff(repo_path):
    """Get diff of tracked root-level .md file changes."""
    result = run_git(["diff", "--", "*.md"], repo_path)
    if result.returncode != 0:
        logging.error("git diff failed: %s", result.stderr.strip())
        return ""
    return result.stdout


def get_staged_diff(repo_path):
    """Get diff of staged root-level .md files only."""
    result = run_git(["diff", "--cached", "--", "*.md"], repo_path)
    if result.returncode != 0:
        logging.error("git diff --cached failed: %s", result.stderr.strip())
        return ""
    return result.stdout


def has_changes(repo_path):
    """Check if there are changes to root-level .md files only."""
    result = run_git(["status", "--porcelain"], repo_path)
    if result.returncode != 0:
        logging.error("git status failed: %s", result.stderr.strip())
        return False
    
    # Filter to only root-level .md files (no path separators = root level)
    lines = result.stdout.strip().split("\n")
    for line in lines:
        if not line.strip():
            continue
        # Status format: XY filename or XY filename -> newfilename (for renames)
        # Extract the filename (after the status codes)
        parts = line.split()
        if len(parts) >= 2:
            filename = parts[-1]  # Get the last part (handles renames too)
            # Check if it's a root-level .md file (no "/" and ends with .md)
            if "/" not in filename and filename.endswith(".md"):
                return True
    return False


def ensure_git_identity(repo_path):
    """Ensure git user identity is set for commits."""
    # Check if user.name is set
    result = run_git(["config", "user.name"], repo_path)
    if result.returncode != 0 or not result.stdout.strip():
        # Try global config
        result = run_git(["config", "--global", "user.name"], repo_path)
        if result.returncode != 0 or not result.stdout.strip():
            # Set a default identity
            run_git(["config", "user.name", "Git Watcher"], repo_path)
            run_git(["config", "user.email", "gitwatcher@local"], repo_path)
            logging.info("Set default git user identity for %s", repo_path)


def get_root_md_files(repo_path):
    """Get list of root-level .md files that have changes."""
    # Get all changed files
    result = run_git(["status", "--porcelain"], repo_path)
    if result.returncode != 0:
        return []
    
    root_md_files = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        # Parse status line: XY filename
        parts = line.split()
        if len(parts) >= 2:
            filename = parts[-1]
            # Only root-level .md files
            if "/" not in filename and filename.endswith(".md"):
                root_md_files.append(filename)
    return root_md_files


def auto_commit_and_push(repo_path):
    # Ensure git identity is set before committing
    ensure_git_identity(repo_path)
    
    # Get list of root-level .md files to add
    files_to_add = get_root_md_files(repo_path)
    if not files_to_add:
        logging.debug("No root-level .md files to add")
        return False
    
    # Add only specific root-level .md files
    for filepath in files_to_add:
        result = run_git(["add", filepath], repo_path)
        if result.returncode != 0:
            logging.error("git add %s failed: %s", filepath, result.stderr.strip())
            return False

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"Auto-commit: {timestamp}"
    result = run_git(["commit", "-m", message], repo_path)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "nothing to commit" in stderr.lower():
            logging.info("Nothing to commit")
            return False
        logging.error("git commit failed: %s", stderr)
        return False

    result = run_git(["push"], repo_path, timeout=120)
    if result.returncode != 0:
        logging.error("git push failed: %s", result.stderr.strip())
        return False

    logging.info("Committed and pushed changes")
    return True


def send_telegram_diff(token, chat_id, diff_text):
    if not diff_text.strip():
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    max_len = 4000
    chunks = [diff_text[i : i + max_len] for i in range(0, len(diff_text), max_len)]

    for i, chunk in enumerate(chunks, 1):
        prefix = f"Diff chunk {i}/{len(chunks)}\n"
        payload = {
            "chat_id": chat_id,
            "text": prefix + chunk,
        }
        try:
            response = requests.post(url, json=payload, timeout=15)
            if response.status_code != 200:
                logging.error(
                    "Telegram send failed (%s): %s",
                    response.status_code,
                    response.text,
                )
        except requests.RequestException as exc:
            logging.error("Telegram send error: %s", exc)


def setup_logging(log_level="ERROR"):
    log_dir = Path.home() / ".git_watcher" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "git_watcher.log"

    # Map string level to logging constant
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    level = level_map.get(log_level.upper(), logging.ERROR)

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(),
        ],
    )


def check_and_commit(watch_path, token, chat_id, force=False):
    """Check for changes and commit if found. Returns True if commit happened."""
    try:
        if not has_changes(watch_path):
            return False
        
        if force:
            logging.info("Force commit triggered - pending changes too old")
        
        diff_text = get_diff(watch_path)
        # Note: diff_text may be empty for new untracked files, but we still commit
        
        committed = auto_commit_and_push(watch_path)
        if committed:
            # Get the actual diff after staging (includes new files)
            staged_diff = get_staged_diff(watch_path)
            if staged_diff:
                send_telegram_diff(token, chat_id, staged_diff)
            elif diff_text.strip():
                send_telegram_diff(token, chat_id, diff_text)
        return committed
    except Exception as exc:
        logging.exception("Error handling change: %s", exc)
        return False


def start_watcher(watch_path, token, chat_id):
    """Start the file watcher and return (observer, event_handler)."""
    logging.info("Starting watcher for %s", watch_path)

    def handle_change():
        check_and_commit(watch_path, token, chat_id)

    event_handler = DebouncedHandler(handle_change)
    observer = Observer()
    observer.schedule(event_handler, watch_path, recursive=False)
    observer.start()
    
    return observer, event_handler


def run_polling_mode(watch_path, token, chat_id):
    """Simple polling mode for when FSEvents don't work (e.g., LaunchAgent)."""
    logging.info("Starting POLLING watcher for %s (checking every %ds)", watch_path, POLLING_INTERVAL)
    
    last_commit_time = time.time()
    
    while True:
        time.sleep(POLLING_INTERVAL)
        
        try:
            # Check for changes and commit
            if has_changes(watch_path):
                logging.info("Changes detected via polling")
                check_and_commit(watch_path, token, chat_id)
                last_commit_time = time.time()
        except Exception as exc:
            logging.exception("Error in polling loop: %s", exc)


def main():
    # Load config first to get log level
    config = load_config()
    setup_logging(config.get("log_level", "ERROR"))
    token = config.get("bot_token")
    chat_id = config.get("chat_id")
    watch_path = config.get("watched_dir")

    if not token or not chat_id:
        logging.error("Missing Telegram bot token or chat ID in config/env")
        sys.exit(1)

    if not watch_path:
        logging.error("Missing watched_dir in config/env")
        sys.exit(1)

    if not os.path.isdir(watch_path):
        logging.error("Watch path does not exist: %s", watch_path)
        sys.exit(1)

    # Check if it's a git repo
    git_check = run_git(["status"], watch_path)
    if git_check.returncode != 0:
        logging.error("Watch path is not a valid git repository: %s", watch_path)
        sys.exit(1)

    # Initial commit check on startup
    check_and_commit(watch_path, token, chat_id)

    # Check if we should use polling mode (more reliable for LaunchAgents/daemons)
    # Set USE_POLLING=1 env var to force polling mode
    use_polling = os.environ.get("USE_POLLING", "1").lower() in ("1", "true", "yes")
    
    if use_polling:
        logging.info("Using POLLING mode (set USE_POLLING=0 to use FSEvents instead)")
        try:
            run_polling_mode(watch_path, token, chat_id)
        except KeyboardInterrupt:
            logging.info("Stopping watcher (Ctrl+C)")
        return

    # FSEvents mode (may not work in all contexts)
    observer = None
    event_handler = None
    last_health_check = time.time()
    restart_count = 0
    max_restarts = 10

    try:
        while restart_count < max_restarts:
            try:
                # Start or restart the watcher
                if observer is not None:
                    logging.warning("Restarting watcher (restart #%d)", restart_count)
                    try:
                        observer.stop()
                        observer.join(timeout=5)
                    except Exception as e:
                        logging.warning("Error stopping observer: %s", e)
                
                observer, event_handler = start_watcher(watch_path, token, chat_id)
                restart_count += 1
                
                # Main loop with health checks
                while True:
                    time.sleep(1)
                    
                    now = time.time()
                    
                    # Periodic health check
                    if now - last_health_check >= HEALTH_CHECK_INTERVAL:
                        last_health_check = now
                        
                        # Check if observer is still alive
                        if not observer.is_alive():
                            logging.error("Observer died, restarting...")
                            break  # Break inner loop to restart
                        
                        # Check for stale pending changes (force commit if events aged out)
                        if event_handler:
                            last_event = event_handler.get_last_event_time()
                            if last_event and (now - last_event) > MAX_EVENT_AGE:
                                if has_changes(watch_path):
                                    logging.warning("Detected stale pending changes, forcing commit")
                                    check_and_commit(watch_path, token, chat_id, force=True)
                                    # Reset event time
                                    with event_handler._lock:
                                        event_handler._last_event_time = None
                        
                        # Periodic check for changes (backup in case events are missed)
                        check_and_commit(watch_path, token, chat_id)
                        
            except Exception as e:
                logging.exception("Watcher error: %s", e)
                time.sleep(5)  # Wait before restart
                continue
                
    except KeyboardInterrupt:
        logging.info("Stopping watcher (Ctrl+C)")
    finally:
        if observer is not None:
            observer.stop()
            observer.join(timeout=5)
        logging.info("Watcher stopped")


if __name__ == "__main__":
    main()

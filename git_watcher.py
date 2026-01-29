#!/usr/bin/env python3
import json
import logging
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import requests
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from config import load_config

DEBOUNCE_SECONDS = 2.0
LOG_NAME = "git_watcher"


class DebouncedHandler(FileSystemEventHandler):
    def __init__(self, on_change):
        super().__init__()
        self._on_change = on_change
        self._timer = None
        self._lock = threading.Lock()

    def on_any_event(self, event):
        if "/.git/" in event.src_path:
            return
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(DEBOUNCE_SECONDS, self._on_change)
            self._timer.daemon = True
            self._timer.start()


def run_git(args, repo_path, timeout=30):
    cmd = ["git", "-C", repo_path] + args
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def get_diff(repo_path):
    result = run_git(["diff"], repo_path)
    if result.returncode != 0:
        logging.error("git diff failed: %s", result.stderr.strip())
        return ""
    return result.stdout


def has_changes(repo_path):
    result = run_git(["status", "--porcelain"], repo_path)
    if result.returncode != 0:
        logging.error("git status failed: %s", result.stderr.strip())
        return False
    return bool(result.stdout.strip())


def auto_commit_and_push(repo_path):
    result = run_git(["add", "-A"], repo_path)
    if result.returncode != 0:
        logging.error("git add failed: %s", result.stderr.strip())
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


def main():
    # Load config first to get log level
    config = load_config()
    setup_logging(config.get("log_level", "ERROR"))
    token = config.get("bot_token")
    chat_id = config.get("chat_id")
    watch_path = config.get("watched_dir")

    if not token or not chat_id:
        logging.error("Missing Telegram bot token or chat ID in config/env")
        return

    if not watch_path:
        logging.error("Missing watched_dir in config/env")
        return

    if not os.path.isdir(watch_path):
        logging.error("Watch path does not exist: %s", watch_path)
        return

    # Check if it's a git repo
    git_check = run_git(["status"], watch_path)
    if git_check.returncode != 0:
        logging.error("Watch path is not a valid git repository: %s", watch_path)
        return

    logging.info("Starting watcher for %s", watch_path)

    def handle_change():
        try:
            if not has_changes(watch_path):
                return
            diff_text = get_diff(watch_path)
            if not diff_text.strip():
                return
            committed = auto_commit_and_push(watch_path)
            if committed:
                send_telegram_diff(token, chat_id, diff_text)
        except Exception as exc:
            logging.exception("Error handling change: %s", exc)

    event_handler = DebouncedHandler(handle_change)
    observer = Observer()
    observer.schedule(event_handler, watch_path, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Stopping watcher")
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()

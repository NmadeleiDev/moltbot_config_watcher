import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".git_watcher"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_WATCHED_DIR = str(Path.home())


def load_config():
    config = {}
    if CONFIG_FILE.exists():
        try:
            config = json.loads(CONFIG_FILE.read_text())
        except json.JSONDecodeError:
            config = {}

    env_token = os.getenv("GIT_WATCHER_BOT_TOKEN")
    env_chat_id = os.getenv("GIT_WATCHER_CHAT_ID")
    env_watch_dir = os.getenv("GIT_WATCHER_WATCHED_DIR")
    if env_token:
        config["bot_token"] = env_token
    if env_chat_id:
        config["chat_id"] = env_chat_id
    if env_watch_dir:
        config["watched_dir"] = env_watch_dir

    if not config.get("watched_dir"):
        config["watched_dir"] = DEFAULT_WATCHED_DIR

    return config

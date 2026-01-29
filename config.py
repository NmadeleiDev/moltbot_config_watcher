import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".git_watcher"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_WATCHED_DIR = str(Path.home())
DEFAULT_LOG_LEVEL = "ERROR"
VALID_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def load_config():
    config = {}
    if CONFIG_FILE.exists():
        try:
            config = json.loads(CONFIG_FILE.read_text())
        except json.JSONDecodeError:
            config = {}

    # Environment variable overrides
    env_token = os.getenv("GIT_WATCHER_BOT_TOKEN")
    env_chat_id = os.getenv("GIT_WATCHER_CHAT_ID")
    env_watch_dir = os.getenv("GIT_WATCHER_WATCHED_DIR")
    env_log_level = os.getenv("GIT_WATCHER_LOG_LEVEL")
    
    if env_token:
        config["bot_token"] = env_token
    if env_chat_id:
        config["chat_id"] = env_chat_id
    if env_watch_dir:
        config["watched_dir"] = env_watch_dir
    if env_log_level:
        config["log_level"] = env_log_level

    # Set defaults
    if not config.get("watched_dir"):
        config["watched_dir"] = DEFAULT_WATCHED_DIR
    
    # Validate and set log level
    log_level = config.get("log_level", DEFAULT_LOG_LEVEL).upper()
    if log_level not in VALID_LOG_LEVELS:
        log_level = DEFAULT_LOG_LEVEL
    config["log_level"] = log_level

    return config

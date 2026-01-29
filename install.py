#!/usr/bin/env python3
"""
Alternative installer script (Python-based).
You can use setup.sh (bash) or this install.py - they do the same thing.
"""

import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".git_watcher"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_DIR = CONFIG_DIR / "logs"


def prompt(value_name, required=True, default=None):
    while True:
        prompt_text = f"Enter {value_name}"
        if default:
            prompt_text += f" [{default}]"
        prompt_text += ": "
        
        value = input(prompt_text).strip()
        
        if not value and default:
            return default
        if not value and required:
            print(f"{value_name} cannot be empty")
            continue
        return value


def validate_git_repo(path):
    """Check if path is a valid git repository."""
    git_dir = Path(path) / ".git"
    return git_dir.exists() and git_dir.is_dir()


def get_watched_dir():
    """Prompt for and validate the watched directory."""
    while True:
        watched_dir = prompt("path to the git repository to watch")
        watched_dir = os.path.expanduser(watched_dir)
        
        if not os.path.isdir(watched_dir):
            print(f"Error: Directory does not exist: {watched_dir}")
            continue
        
        if not validate_git_repo(watched_dir):
            print(f"Error: Not a git repository: {watched_dir}")
            continue
        
        print(f"✓ Valid git repository: {watched_dir}")
        return watched_dir


def write_config(watched_dir, bot_token, chat_id, log_level="ERROR"):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    data = {
        "watched_dir": watched_dir,
        "bot_token": bot_token,
        "chat_id": chat_id,
        "log_level": log_level
    }
    
    CONFIG_FILE.write_text(json.dumps(data, indent=2))
    print(f"✓ Wrote config: {CONFIG_FILE}")


def setup_macos_launchagent(script_path, auto_start=False):
    """Create macOS LaunchAgent plist."""
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.git_watcher.plist"
    
    plist = {
        "Label": "com.git_watcher",
        "ProgramArguments": [sys.executable, str(script_path)],
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(LOG_DIR / "git_watcher.out.log"),
        "StandardErrorPath": str(LOG_DIR / "git_watcher.err.log"),
        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1",
        },
    }

    plist_path.parent.mkdir(parents=True, exist_ok=True)
    with plist_path.open("wb") as f:
        plistlib.dump(plist, f)

    print(f"✓ Wrote LaunchAgent: {plist_path}")
    
    if auto_start:
        try:
            subprocess.run(["launchctl", "load", "-w", str(plist_path)], check=True)
            print("✓ Service started")
            print("  View logs: tail -f ~/.git_watcher/logs/git_watcher.log")
        except subprocess.CalledProcessError as e:
            print(f"⚠ Failed to start service: {e}")
            print("\nTo start manually, run:")
            print(f"  launchctl load -w {plist_path}")
    else:
        print("\nTo start the service, run:")
        print(f"  launchctl load -w {plist_path}")
    
    print("\nTo stop the service:")
    print(f"  launchctl unload -w {plist_path}")


def setup_linux_systemd(script_path, auto_start=False):
    """Create Linux systemd user service."""
    service_path = Path.home() / ".config" / "systemd" / "user" / "git_watcher.service"
    service_path.parent.mkdir(parents=True, exist_ok=True)
    
    service_content = f"""[Unit]
Description=Git Watcher - Auto-commit and notify on file changes
After=network.target

[Service]
Type=simple
ExecStart={sys.executable} {script_path}
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""
    
    service_path.write_text(service_content)
    print(f"✓ Wrote systemd service: {service_path}")
    
    if auto_start:
        try:
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            subprocess.run(["systemctl", "--user", "enable", "git_watcher.service"], check=True)
            subprocess.run(["systemctl", "--user", "start", "git_watcher.service"], check=True)
            print("✓ Service started")
            print("  View logs: journalctl --user -u git_watcher.service -f")
        except subprocess.CalledProcessError as e:
            print(f"⚠ Failed to start service: {e}")
            print("\nTo start manually, run:")
            print("  systemctl --user daemon-reload")
            print("  systemctl --user enable git_watcher.service")
            print("  systemctl --user start git_watcher.service")
    else:
        print("\nTo start the service, run:")
        print("  systemctl --user daemon-reload")
        print("  systemctl --user enable git_watcher.service")
        print("  systemctl --user start git_watcher.service")
    
    print("\nTo check status:")
    print("  systemctl --user status git_watcher.service")


def detect_os():
    """Detect the operating system."""
    import platform
    system = platform.system()
    if system == "Darwin":
        return "macos"
    elif system == "Linux":
        return "linux"
    else:
        return "unknown"


def main():
    script_path = Path(__file__).resolve().parent / "git_watcher.py"
    if not script_path.exists():
        print("Error: git_watcher.py not found next to install.py")
        sys.exit(1)

    print("Git Watcher Setup")
    print("=" * 40)
    print()

    # Get configuration
    watched_dir = get_watched_dir()
    bot_token = prompt("Telegram bot token")
    chat_id = prompt("Telegram chat ID")
    
    # Log level
    print("\nSelect log level (default: ERROR):")
    print("  1) ERROR - Only errors (recommended for production)")
    print("  2) INFO  - General information")
    print("  3) DEBUG - Verbose debugging")
    log_choice = input("Choice [1-3] (default: 1): ").strip() or "1"
    
    log_levels = {"1": "ERROR", "2": "INFO", "3": "DEBUG"}
    log_level = log_levels.get(log_choice, "ERROR")
    print(f"✓ Log level set to: {log_level}")
    
    # Write config
    write_config(watched_dir, bot_token, chat_id, log_level)
    
    # Ask about auto-start
    auto_start_input = input("\nStart the service now? [Y/n]: ").strip().lower()
    auto_start = auto_start_input in ("", "y", "yes")
    
    # Create service based on OS
    os_type = detect_os()
    
    if os_type == "macos":
        setup_macos_launchagent(script_path, auto_start)
    elif os_type == "linux":
        setup_linux_systemd(script_path, auto_start)
    else:
        print(f"Unsupported operating system: {os_type}")
        print("You can still run the watcher manually:")
        print(f"  python {script_path}")
        sys.exit(1)
    
    print()
    print("=" * 40)
    print("✓ Setup complete!")
    print()
    print("Configuration summary:")
    print(f"  Watched directory: {watched_dir}")
    print(f"  Log level: {log_level}")
    print(f"  Config file: {CONFIG_FILE}")
    print(f"  Logs directory: {LOG_DIR}")
    print()
    print("You can also run the watcher manually:")
    print(f"  python {script_path}")


if __name__ == "__main__":
    main()

# Git Watcher

A lightweight tool that watches a git repository for file changes and automatically commits, pushes, and sends diffs to Telegram.

## Features

- 🔍 Watches any local git repository for file changes
- 🤖 Auto-commits changes with timestamped messages
- 🚀 Auto-pushes to remote repository
- 📨 Sends diffs to Telegram (supports long diffs via chunking)
- ⚡ Debounced events (2-second delay to batch rapid changes)
- 📝 Configurable logging levels (ERROR, INFO, DEBUG)
- 🖥️ Runs as a background service (macOS LaunchAgent / Linux systemd)
- ⚙️ Configurable via environment variables or config file
- 🚀 Optional auto-start during setup

## Requirements

- Python 3.7+
- macOS or Linux
- A Telegram bot (get one from [@BotFather](https://t.me/botfather))
- Your Telegram chat ID

## Quick Start

### 1. Clone the repository

```bash
git clone git@github.com:NmadeleiDev/git_watcher.git
cd git_watcher
```

### 2. Run the setup script

```bash
./setup.sh
```

The script will:
- Check for Python 3
- Create a virtual environment
- Install dependencies
- Prompt for your configuration:
  - Path to the git repository to watch
  - Telegram bot token
  - Telegram chat ID
  - Log level (ERROR, INFO, DEBUG)
- Create appropriate service for your OS
- Optionally start the service immediately

### 3. Start the service

The setup script will ask if you want to start the service automatically. If you skipped it or need to control it manually:

**macOS:**
```bash
launchctl load -w ~/Library/LaunchAgents/com.git_watcher.plist
```

**Linux:**
```bash
systemctl --user daemon-reload
systemctl --user enable git_watcher.service
systemctl --user start git_watcher.service
```

## Manual Setup

If you prefer to set up manually:

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create config file manually
mkdir -p ~/.git_watcher
cat > ~/.git_watcher/config.json << 'EOF'
{
  "watched_dir": "/path/to/your/repo",
  "bot_token": "YOUR_BOT_TOKEN",
  "chat_id": "YOUR_CHAT_ID"
}
EOF

# Run manually
python git_watcher.py
```

## Configuration

Configuration can be provided via:

1. **Config file** (default): `~/.git_watcher/config.json`
2. **Environment variables** (override config file):
   - `GIT_WATCHER_WATCHED_DIR` - Path to git repository
   - `GIT_WATCHER_BOT_TOKEN` - Telegram bot token
   - `GIT_WATCHER_CHAT_ID` - Telegram chat ID
   - `GIT_WATCHER_LOG_LEVEL` - Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: ERROR)

### Example Config File

```json
{
  "watched_dir": "/path/to/your/repo",
  "bot_token": "YOUR_BOT_TOKEN",
  "chat_id": "YOUR_CHAT_ID",
  "log_level": "ERROR"
}
```

### Log Levels

- **ERROR** (default) - Only errors, silent during normal operation
- **INFO** - General operational information
- **DEBUG** - Verbose output for troubleshooting

### Getting Your Telegram Chat ID

1. Start a conversation with your bot
2. Send a message to the bot
3. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. Look for the `"chat":{"id":123456789` field

## Managing the Service

### macOS

```bash
# Start
launchctl load -w ~/Library/LaunchAgents/com.git_watcher.plist

# Stop
launchctl unload -w ~/Library/LaunchAgents/com.git_watcher.plist

# Check status
launchctl list | grep com.git_watcher

# View logs
tail -f ~/.git_watcher/logs/git_watcher.log
tail -f ~/.git_watcher/logs/git_watcher.out.log
tail -f ~/.git_watcher/logs/git_watcher.err.log
```

### Linux

```bash
# Start
systemctl --user start git_watcher.service

# Stop
systemctl --user stop git_watcher.service

# Check status
systemctl --user status git_watcher.service

# View logs
journalctl --user -u git_watcher.service -f
```

## Logs

All logs are stored in `~/.git_watcher/logs/`:
- `git_watcher.log` - Application logs
- `git_watcher.out.log` - Standard output (service mode)
- `git_watcher.err.log` - Standard error (service mode)

## How It Works

1. The watcher monitors the configured directory recursively using `watchdog`
2. When a file changes, it waits 2 seconds (debounce) for any additional changes
3. Checks if there are actual git changes using `git status`
4. Gets the diff using `git diff`
5. Commits all changes with message: "Auto-commit: YYYY-MM-DD HH:MM:SS"
6. Pushes to the remote repository
7. Sends the diff to your Telegram chat (chunked if >4000 characters)

## File Structure

```
git_watcher/
├── git_watcher.py    # Main watcher script
├── config.py         # Configuration loader
├── setup.sh          # Setup and installation script
├── requirements.txt  # Python dependencies
├── README.md         # This file
└── .gitignore        # Git ignore rules
```

## Troubleshooting

### Service won't start

Check the logs:
- **macOS**: `tail -f ~/.git_watcher/logs/git_watcher.err.log`
- **Linux**: `journalctl --user -u git_watcher.service -f`

### Telegram messages not sending

- Verify your bot token is correct
- Make sure you've started a conversation with the bot
- Check that your chat ID is correct (use the getUpdates API to verify)

### Git push fails

- Ensure your repo has a remote configured: `git remote -v`
- Make sure you have push access to the remote
- For private repos, ensure your SSH key or credentials are set up

### Changes not being detected

- Verify the watched directory exists and is a git repository
- Check that `.git` folder exists in the watched directory
- Look at the logs for any errors

## Uninstallation

### macOS

```bash
launchctl unload -w ~/Library/LaunchAgents/com.git_watcher.plist
rm ~/Library/LaunchAgents/com.git_watcher.plist
rm -rf ~/.git_watcher
```

### Linux

```bash
systemctl --user stop git_watcher.service
systemctl --user disable git_watcher.service
rm ~/.config/systemd/user/git_watcher.service
rm -rf ~/.git_watcher
```

## License

MIT License - feel free to use and modify as needed.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

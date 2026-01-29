#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.git_watcher"
CONFIG_FILE="$CONFIG_DIR/config.json"

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}→ $1${NC}"
}

# Check if Python 3 is installed
print_info "Checking Python 3 installation..."
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed. Please install Python 3 first."
    exit 1
fi
print_success "Python 3 found: $(python3 --version)"

# Create virtual environment
print_info "Creating virtual environment..."
cd "$SCRIPT_DIR"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
print_success "Virtual environment created"

# Activate virtual environment and install dependencies
print_info "Installing dependencies..."
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
print_success "Dependencies installed"

# Create config directory
mkdir -p "$CONFIG_DIR/logs"

# Prompt for configuration
print_info "Configuration setup"
echo ""

# Watched directory
while true; do
    read -rp "Enter the path to the git repository to watch: " watched_dir
    watched_dir="${watched_dir/#\~/$HOME}"  # Expand ~ to home directory
    
    if [ ! -d "$watched_dir" ]; then
        print_error "Directory does not exist: $watched_dir"
        continue
    fi
    
    # Check if it's a git repository
    if [ ! -d "$watched_dir/.git" ]; then
        print_error "Not a git repository: $watched_dir"
        continue
    fi
    
    print_success "Valid git repository: $watched_dir"
    break
done

# Telegram bot token
while true; do
    read -rp "Enter your Telegram bot token: " bot_token
    if [ -n "$bot_token" ]; then
        break
    fi
    print_error "Bot token cannot be empty"
done

# Telegram chat ID
while true; do
    read -rp "Enter your Telegram chat ID: " chat_id
    if [ -n "$chat_id" ]; then
        break
    fi
    print_error "Chat ID cannot be empty"
done

# Log level
print_info "Select log level (default: ERROR):"
echo "  1) ERROR - Only errors (recommended for production)"
echo "  2) INFO  - General information"
echo "  3) DEBUG - Verbose debugging"
read -rp "Choice [1-3] (default: 1): " log_choice

case "$log_choice" in
    2) LOG_LEVEL="INFO" ;;
    3) LOG_LEVEL="DEBUG" ;;
    *) LOG_LEVEL="ERROR" ;;
esac
print_success "Log level set to: $LOG_LEVEL"

# Create config file
print_info "Creating configuration file..."
cat > "$CONFIG_FILE" << EOF
{
  "watched_dir": "$watched_dir",
  "bot_token": "$bot_token",
  "chat_id": "$chat_id",
  "log_level": "$LOG_LEVEL"
}
EOF
print_success "Configuration saved to $CONFIG_FILE"

# Detect OS and create appropriate service
OS="$(uname -s)"
case "$OS" in
    Darwin*)
        print_info "Detected macOS - creating LaunchAgent..."
        
        PLIST_PATH="$HOME/Library/LaunchAgents/com.git_watcher.plist"
        
        cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.git_watcher</string>
    <key>ProgramArguments</key>
    <array>
        <string>$SCRIPT_DIR/.venv/bin/python</string>
        <string>$SCRIPT_DIR/git_watcher.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
        <key>Crashed</key>
        <true/>
    </dict>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>StandardOutPath</key>
    <string>$CONFIG_DIR/logs/git_watcher.out.log</string>
    <key>StandardErrorPath</key>
    <string>$CONFIG_DIR/logs/git_watcher.err.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
</dict>
</plist>
EOF
        
        print_success "LaunchAgent created at $PLIST_PATH"
        echo ""
        read -rp "Start the service now? [Y/n]: " start_now
        start_now=${start_now:-Y}
        if [[ "$start_now" =~ ^[Yy]$ ]]; then
            launchctl load -w "$PLIST_PATH" 2>/dev/null || true
            print_success "Service started"
            print_info "View logs: tail -f ~/.git_watcher/logs/git_watcher.log"
        else
            print_info "To start later, run:"
            echo "  launchctl load -w $PLIST_PATH"
        fi
        echo ""
        print_info "To stop the service:"
        echo "  launchctl unload -w $PLIST_PATH"
        ;;
        
    Linux*)
        print_info "Detected Linux - creating systemd service..."
        
        SERVICE_PATH="$HOME/.config/systemd/user/git_watcher.service"
        mkdir -p "$HOME/.config/systemd/user"
        
        cat > "$SERVICE_PATH" << EOF
[Unit]
Description=Git Watcher - Auto-commit and notify on file changes
After=network.target

[Service]
Type=simple
ExecStart=$SCRIPT_DIR/.venv/bin/python $SCRIPT_DIR/git_watcher.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF
        
        print_success "Systemd service created at $SERVICE_PATH"
        echo ""
        read -rp "Start the service now? [Y/n]: " start_now
        start_now=${start_now:-Y}
        if [[ "$start_now" =~ ^[Yy]$ ]]; then
            systemctl --user daemon-reload
            systemctl --user enable git_watcher.service
            systemctl --user start git_watcher.service
            print_success "Service started"
            print_info "View logs: journalctl --user -u git_watcher.service -f"
        else
            print_info "To start later, run:"
            echo "  systemctl --user daemon-reload"
            echo "  systemctl --user enable git_watcher.service"
            echo "  systemctl --user start git_watcher.service"
        fi
        echo ""
        print_info "To check status:"
        echo "  systemctl --user status git_watcher.service"
        ;;
        
    *)
        print_error "Unsupported operating system: $OS"
        echo "Please run the watcher manually:"
        echo "  $SCRIPT_DIR/.venv/bin/python $SCRIPT_DIR/git_watcher.py"
        exit 1
        ;;
esac

echo ""
print_success "Setup complete!"
echo ""
echo "Configuration summary:"
echo "  Watched directory: $watched_dir"
echo "  Config file: $CONFIG_FILE"
echo "  Logs directory: $CONFIG_DIR/logs"
echo ""
echo "You can also run the watcher manually:"
echo "  cd $SCRIPT_DIR && source .venv/bin/activate && python git_watcher.py"

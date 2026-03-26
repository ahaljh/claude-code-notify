#!/bin/zsh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

uv run --directory "$SCRIPT_DIR" python slack_notifier.py "$1"
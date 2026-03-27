# config.py — 설정 파일 경로 관리

import os
from pathlib import Path

APP_NAME = "claude-code-notify"
CONFIG_FILE = "config.env"
LOG_FILE = "notify.log"


def get_config_dir() -> Path:
    """설정 디렉토리 경로 반환 (XDG_CONFIG_HOME 지원)"""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / APP_NAME


def get_config_path() -> Path:
    """설정 파일 경로: ~/.config/claude-code-notify/config.env"""
    return get_config_dir() / CONFIG_FILE


def get_log_path() -> Path:
    """로그 파일 경로: ~/.config/claude-code-notify/notify.log"""
    return get_config_dir() / LOG_FILE


def get_claude_settings_path() -> Path:
    """Claude Code 설정 파일 경로: ~/.claude/settings.json"""
    return Path.home() / ".claude" / "settings.json"

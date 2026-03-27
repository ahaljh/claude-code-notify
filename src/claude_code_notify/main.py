# main.py — CLI 진입점 (notify / init 서브커맨드)

import argparse
import json
import shutil
import sys
from getpass import getpass
from pathlib import Path

from claude_code_notify.config import (
    get_claude_settings_path,
    get_config_dir,
    get_config_path,
)
from claude_code_notify.notifier import API_URL, STATUS_WAIT, send_slack_notification, setup

HOOK_MARKER = "claude-code-notify"


def _resolve_command_path() -> str:
    """claude-code-notify 실행 파일의 절대 경로를 반환"""
    path = shutil.which("claude-code-notify")
    if path:
        return path
    # PATH에 없는 경우 (설치 직후 셸 미갱신 등) 일반적인 uv tool 경로 시도
    fallback = Path.home() / ".local" / "bin" / "claude-code-notify"
    if fallback.exists():
        return str(fallback)
    # 최후 수단: 상대 커맨드명 사용
    return "claude-code-notify"


def _upsert_hook_list(hook_list: list, new_hook: dict) -> list:
    """훅 리스트에서 claude-code-notify 관련 항목을 교체하거나 추가"""
    result = []
    replaced = False
    for item in hook_list:
        hooks = item.get("hooks", [])
        has_notify = any(HOOK_MARKER in h.get("command", "") for h in hooks)
        if has_notify:
            result.append(new_hook)
            replaced = True
        else:
            result.append(item)
    if not replaced:
        result.append(new_hook)
    return result


def _register_hooks() -> None:
    """~/.claude/settings.json에 Notification/Stop 훅 등록"""
    settings_path = get_claude_settings_path()

    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    else:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings = {}

    hooks = settings.setdefault("hooks", {})

    cmd = _resolve_command_path()

    notification_hook = {
        "matcher": "",
        "hooks": [{"type": "command", "command": f"{cmd} notify wait"}],
    }
    stop_hook = {
        "matcher": "",
        "hooks": [{"type": "command", "command": f"{cmd} notify done"}],
    }

    hooks["Notification"] = _upsert_hook_list(
        hooks.get("Notification", []), notification_hook
    )
    hooks["Stop"] = _upsert_hook_list(hooks.get("Stop", []), stop_hook)

    settings["hooks"] = hooks
    settings_path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"  훅 등록 완료: {settings_path}")


def _save_config(token: str, user_id: str) -> None:
    """설정 파일에 환경변수 저장"""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)

    config_path = get_config_path()
    config_path.write_text(
        f"SLACK_BOT_TOKEN={token}\n"
        f"USER_ID={user_id}\n"
        f"LOG_LEVEL=INFO\n",
        encoding="utf-8",
    )
    # 본인만 읽기/쓰기 가능하도록 권한 설정
    config_path.chmod(0o600)
    print(f"  설정 저장 완료: {config_path}")


def _send_test_notification(token: str, user_id: str) -> None:
    """테스트 알림 전송"""
    import requests

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "channel": user_id,
        "text": "🎉 claude-code-notify 설정 완료! 알림이 정상적으로 동작합니다.",
    }
    try:
        resp = requests.post(
            API_URL,
            headers=headers,
            json=payload,
            timeout=5,
        )
        result = resp.json()
        if result.get("ok"):
            print("  테스트 알림 전송 성공!")
        else:
            print(f"  테스트 알림 실패: {result.get('error')}", file=sys.stderr)
    except Exception as e:
        print(f"  테스트 알림 실패: {e}", file=sys.stderr)


def cmd_init(_args: argparse.Namespace) -> None:
    """인터랙티브 초기 설정"""
    # 설치 여부 확인 (uvx로만 실행한 경우 hooks가 동작하지 않음)
    cmd_path = _resolve_command_path()
    if cmd_path == "claude-code-notify":
        print(
            "⚠️  claude-code-notify가 설치되지 않았습니다.\n"
            "먼저 설치한 후 다시 실행해주세요:\n\n"
            "  uv tool install git+https://github.com/ahaljh/claude-code-notify\n"
            "  uvx claude-code-notify init\n",
            file=sys.stderr,
        )
        sys.exit(1)

    print("claude-code-notify 초기 설정을 시작합니다.\n")

    # 기존 설정 확인
    config_path = get_config_path()
    if config_path.exists():
        overwrite = input(f"기존 설정이 있습니다 ({config_path}). 덮어쓸까요? (y/N): ")
        if overwrite.lower() != "y":
            print("설정을 유지합니다.")
            return

    # SLACK_BOT_TOKEN 입력
    while True:
        token = getpass("SLACK_BOT_TOKEN을 입력하세요 (xoxb-...): ")
        if token.startswith("xoxb-"):
            print(f"  ✓ 토큰 입력 완료 ({token[:8]}...{token[-4:]})")
            break
        print("  올바른 Bot Token을 입력해주세요 (xoxb-로 시작해야 합니다).")

    # USER_ID 입력
    while True:
        user_id = input("USER_ID를 입력하세요 (Slack 프로필 > 멤버 ID 복사, U로 시작): ")
        if user_id.startswith("U"):
            break
        print("  올바른 User ID를 입력해주세요 (U로 시작해야 합니다).")

    # 설정 저장
    print()
    _save_config(token, user_id)

    # Claude Code 훅 등록
    _register_hooks()

    # 테스트 알림
    print()
    test = input("테스트 알림을 보낼까요? (Y/n): ")
    if test.lower() != "n":
        _send_test_notification(token, user_id)

    print("\n설정 완료! Claude Code를 재시작하면 알림이 동작합니다.")


def cmd_notify(args: argparse.Namespace) -> None:
    """알림 전송 (Claude Code 훅에서 호출)"""
    setup()
    send_slack_notification(args.status)


def cli() -> None:
    """CLI 진입점"""
    parser = argparse.ArgumentParser(
        prog="claude-code-notify",
        description="Claude Code 작업 상태를 Slack DM으로 알림",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init 서브커맨드
    init_parser = subparsers.add_parser("init", help="초기 설정 (Slack 토큰 + 훅 등록)")
    init_parser.set_defaults(func=cmd_init)

    # notify 서브커맨드
    notify_parser = subparsers.add_parser("notify", help="알림 전송 (훅에서 호출)")
    notify_parser.add_argument("status", choices=[STATUS_WAIT, "done"])
    notify_parser.set_defaults(func=cmd_notify)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    cli()

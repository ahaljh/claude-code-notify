# main.py — CLI 진입점 (notify / init 서브커맨드)

import argparse
import json
import shutil
import sys
from pathlib import Path

from dotenv import dotenv_values

from claude_code_notify.config import (
    get_claude_settings_path,
    get_config_dir,
    get_config_path,
)
from claude_code_notify.notifier import (
    PROVIDERS,
    STATUS_WAIT,
    active_providers,
    build_test_context,
    send_notification,
    setup,
)

HOOK_MARKER = "claude-code-notify"

PROVIDER_LABELS = {"slack": "Slack", "discord": "Discord"}

# provider별 전용 설정 키 (선택 해제 시 제거 대상)
PROVIDER_KEYS = {
    "slack": {"SLACK_BOT_TOKEN", "USER_ID"},
    "discord": {"DISCORD_WEBHOOK_URL"},
}


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


def _save_config(values: dict[str, str]) -> None:
    """설정 파일에 환경변수 저장"""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)

    config_path = get_config_path()
    lines = "".join(f"{key}={value}\n" for key, value in values.items())
    config_path.write_text(lines, encoding="utf-8")
    # 본인만 읽기/쓰기 가능하도록 권한 설정
    config_path.chmod(0o600)
    print(f"  설정 저장 완료: {config_path}")


def _prompt_providers(existing: dict) -> list[str]:
    """알림을 보낼 provider 선택 UI"""
    configured = active_providers(existing)
    if configured:
        labels = ", ".join(PROVIDER_LABELS[name] for name in configured)
        print(f"현재 설정된 서비스: {labels}\n")

    while True:
        choice = input("알림을 보낼 서비스를 선택하세요 (1) Slack  2) Discord  3) 둘 다): ")
        if choice == "1":
            return ["slack"]
        if choice == "2":
            return ["discord"]
        if choice == "3":
            return ["slack", "discord"]
        print("  1, 2, 3 중 하나를 입력해주세요.")


def _send_test_notification(selected: list[str], config: dict) -> None:
    """선택된 provider 각각에 테스트 알림 전송"""
    ctx = build_test_context()
    for name in selected:
        ok = PROVIDERS[name].send(ctx, config)
        label = PROVIDER_LABELS[name]
        if ok:
            print(f"  [{label}] 테스트 알림 전송 성공!")
        else:
            print(f"  [{label}] 테스트 알림 실패", file=sys.stderr)


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

    # 기존 설정 로드 (키별 병합을 위해 전체 읽기, None 값은 제외)
    config_path = get_config_path()
    existing: dict[str, str] = {}
    if config_path.exists():
        existing = {
            key: value
            for key, value in dotenv_values(config_path).items()
            if value is not None
        }

    # provider 선택 및 provider별 설정 입력
    selected = _prompt_providers(existing)
    merged = dict(existing)
    for name in selected:
        merged.update(PROVIDERS[name].prompt_config(existing))

    # 선택하지 않은 provider의 기존 설정 처리
    for name, module in PROVIDERS.items():
        if name in selected or not module.is_configured(existing):
            continue
        label = PROVIDER_LABELS[name]
        remove = input(f"\n기존 {label} 설정이 있습니다. 제거할까요? (y/N): ")
        if remove.lower() == "y":
            for key in PROVIDER_KEYS[name]:
                merged.pop(key, None)
            print(f"  {label} 설정 제거 완료")
        else:
            print(f"  {label} 설정 유지 (계속 알림이 전송됩니다)")

    merged.setdefault("LOG_LEVEL", "INFO")

    # 설정 저장
    print()
    _save_config(merged)

    # Claude Code 훅 등록
    _register_hooks()

    # 테스트 알림
    print()
    test = input("테스트 알림을 보낼까요? (Y/n): ")
    if test.lower() != "n":
        _send_test_notification(selected, merged)

    print("\n설정 완료! Claude Code를 재시작하면 알림이 동작합니다.")


def cmd_notify(args: argparse.Namespace) -> None:
    """알림 전송 (Claude Code 훅에서 호출)"""
    setup()
    send_notification(args.status)


def cli() -> None:
    """CLI 진입점"""
    parser = argparse.ArgumentParser(
        prog="claude-code-notify",
        description="Claude Code 작업 상태를 Slack/Discord로 알림",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init 서브커맨드
    init_parser = subparsers.add_parser("init", help="초기 설정 (알림 서비스 선택 + 훅 등록)")
    init_parser.set_defaults(func=cmd_init)

    # notify 서브커맨드
    notify_parser = subparsers.add_parser("notify", help="알림 전송 (훅에서 호출)")
    notify_parser.add_argument("status", choices=[STATUS_WAIT, "done"])
    notify_parser.set_defaults(func=cmd_notify)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    cli()

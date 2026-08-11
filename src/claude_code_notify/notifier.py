# notifier.py — Claude Code 훅에서 호출되는 provider 중립 알림 로직 (파싱/컨텍스트 구성/디스패치)

import json
import logging
import logging.handlers
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from claude_code_notify import discord, slack
from claude_code_notify.config import get_config_path, get_log_path

# 상수
DEFAULT_VALUE = "N/A"
STATUS_WAIT = "wait"
MAX_MESSAGE_LENGTH = 300
MAX_PREVIEW_LENGTH = 100

# 지원하는 알림 provider (모듈 = provider 덕 타이핑)
# 각 모듈은 is_configured / build_payload / send / prompt_config 함수를 제공한다
PROVIDERS = {"slack": slack, "discord": discord}

# provider가 참조하는 설정 키
CONFIG_KEYS = ["SLACK_BOT_TOKEN", "USER_ID", "DISCORD_WEBHOOK_URL"]

# 모듈 레벨 설정 (setup()에서 초기화)
logger = logging.getLogger(__name__)
CONFIG: dict[str, str] = {}


@dataclass
class NotificationContext:
    """provider 중립 알림 컨텍스트 (각 provider가 자기 포맷으로 변환)"""

    status: str                     # "wait" | "done"
    header: str                     # 이모지 포함 제목
    message: str                    # 본문 (truncate 적용됨)
    preview: str                    # 푸시 알림 미리보기 텍스트
    fields: list[tuple[str, str]]   # (이름, 값) 쌍 목록
    session_id: str
    transcript_path: str
    timestamp: datetime


def setup() -> None:
    """환경변수 로딩 및 로깅 설정"""
    # 설정 파일 로드 (XDG 경로 우선, fallback으로 현재 디렉토리 .env)
    config_path = get_config_path()
    if config_path.exists():
        load_dotenv(config_path)
    else:
        load_dotenv()

    log_level = os.getenv("LOG_LEVEL", "DEBUG").upper()
    log_path = get_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # 로그 로테이션: 최대 1MB, 백업 3개 (총 ~4MB)
    handler = logging.handlers.RotatingFileHandler(
        str(log_path), maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logging.basicConfig(
        level=getattr(logging, log_level, logging.DEBUG),
        handlers=[handler],
    )

    CONFIG.clear()
    for key in CONFIG_KEYS:
        value = os.getenv(key)
        if value:
            CONFIG[key] = value

    logger.debug(
        "Environment loaded. Configured keys: %s",
        [key for key in CONFIG_KEYS if key in CONFIG],
    )


def to_relative_path(path: str) -> str:
    """절대경로를 홈 디렉토리 기준 상대경로(~)로 변환"""
    if path == DEFAULT_VALUE:
        return path
    home_dir = str(Path.home())
    if path.startswith(home_dir):
        return "~" + path[len(home_dir):]
    return path


def parse_stdin() -> dict:
    """stdin에서 Claude Code 훅의 JSON 데이터를 파싱"""
    try:
        stdin_data = sys.stdin.read()
        logger.debug("Raw stdin data: %s", stdin_data)
        return json.loads(stdin_data) if stdin_data.strip() else {}
    except json.JSONDecodeError as e:
        logger.exception("Failed to parse stdin JSON: %s", e)
        return {}


def build_context(status: str, payload: dict) -> NotificationContext:
    """상태와 훅 payload를 provider 중립 컨텍스트로 변환"""
    event_name = payload.get("hook_event_name", DEFAULT_VALUE)
    session_id = payload.get("session_id", DEFAULT_VALUE)
    cwd = to_relative_path(payload.get("cwd", DEFAULT_VALUE))
    transcript_path = to_relative_path(payload.get("transcript_path", DEFAULT_VALUE))
    notification_type = payload.get("notification_type", DEFAULT_VALUE)

    project_name = cwd.rsplit("/", 1)[-1] if cwd != DEFAULT_VALUE else ""

    # 상태별 제목/본문/필드 구성
    if status == STATUS_WAIT:
        header = f"🚨 Claude Code [{project_name}]: 입력 대기 중"
        msg = payload.get("message", "권한 승인이나 프롬프트 입력이 필요합니다.")
        fields = [
            ("이벤트 타입", event_name),
            ("알림 유형", notification_type),
            ("작업 경로", f"`{cwd}`"),
        ]
    else:
        header = f"✅ Claude Code [{project_name}]: 작업 완료"
        last_message = payload.get("last_assistant_message", "")
        if len(last_message) > MAX_MESSAGE_LENGTH:
            last_message = last_message[:MAX_MESSAGE_LENGTH] + "..."
        msg = last_message or "작업이 완료되었습니다."
        permission_mode = payload.get("permission_mode", DEFAULT_VALUE)
        fields = [
            ("이벤트 타입", event_name),
            ("작업 경로", f"`{cwd}`"),
            ("권한 모드", permission_mode),
        ]

    # 푸시 알림 미리보기 텍스트
    preview_msg = msg[:MAX_PREVIEW_LENGTH] + "..." if len(msg) > MAX_PREVIEW_LENGTH else msg
    status_emoji = "🚨" if status == STATUS_WAIT else "✅"
    status_label = "입력 대기 중" if status == STATUS_WAIT else "작업 완료"
    preview = f"*{status_emoji} [{project_name}] {status_label}*\n{preview_msg}"

    return NotificationContext(
        status=status,
        header=header,
        message=msg,
        preview=preview,
        fields=fields,
        session_id=session_id,
        transcript_path=transcript_path,
        timestamp=datetime.now(),
    )


def build_test_context() -> NotificationContext:
    """init 테스트 알림용 컨텍스트"""
    return NotificationContext(
        status="done",
        header="🎉 claude-code-notify 설정 완료",
        message="알림이 정상적으로 동작합니다.",
        preview="🎉 claude-code-notify 설정 완료! 알림이 정상적으로 동작합니다.",
        fields=[],
        session_id=DEFAULT_VALUE,
        transcript_path=DEFAULT_VALUE,
        timestamp=datetime.now(),
    )


def active_providers(config: dict) -> list[str]:
    """설정 키가 존재하는 활성 provider 이름 목록"""
    return [name for name, module in PROVIDERS.items() if module.is_configured(config)]


def send_notification(status: str) -> None:
    """메인 알림 함수: stdin 파싱 → 컨텍스트 구성 → 활성 provider 전부에 전송"""
    logger.info("send_notification called with status=%s", status)

    active = active_providers(CONFIG)
    if not active:
        logger.error("No notification provider configured. Keys checked: %s", CONFIG_KEYS)
        print(
            "설정된 알림 provider가 없습니다. `claude-code-notify init`을 실행해주세요.",
            file=sys.stderr,
        )
        return

    payload = parse_stdin()

    # idle_prompt는 이미 다른 알림이 발생한 후 사용자 미응답 시 발생하는 중복 알림이므로 무시
    notification_type = payload.get("notification_type", DEFAULT_VALUE)
    if notification_type == "idle_prompt":
        logger.info("idle_prompt 알림 무시 (중복 알림)")
        return

    logger.debug("Parsed payload: %s", json.dumps(payload, indent=2, ensure_ascii=False))
    logger.info(
        "Notification context - event_name=%s, session_id=%s, cwd=%s, providers=%s",
        payload.get("hook_event_name", DEFAULT_VALUE),
        payload.get("session_id", DEFAULT_VALUE),
        payload.get("cwd", DEFAULT_VALUE),
        active,
    )

    ctx = build_context(status, payload)
    for name in active:
        PROVIDERS[name].send(ctx, CONFIG)

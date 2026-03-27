# notifier.py — Claude Code 훅에서 호출되어 Slack DM으로 알림을 보내는 모듈

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

from claude_code_notify.config import get_config_path, get_log_path

# 상수
API_URL = "https://slack.com/api/chat.postMessage"
DEFAULT_VALUE = "N/A"
STATUS_WAIT = "wait"
COLOR_WARNING = "#FFA500"
COLOR_SUCCESS = "#36A64F"
MAX_MESSAGE_LENGTH = 300
MAX_PREVIEW_LENGTH = 100

# 모듈 레벨 설정 (setup()에서 초기화)
logger = logging.getLogger(__name__)
SLACK_BOT_TOKEN: str | None = None
USER_ID: str | None = None


def setup() -> None:
    """환경변수 로딩 및 로깅 설정"""
    global SLACK_BOT_TOKEN, USER_ID

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

    SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
    USER_ID = os.getenv("USER_ID")

    logger.debug(
        "Environment loaded. SLACK_BOT_TOKEN set: %s, USER_ID: %s",
        bool(SLACK_BOT_TOKEN),
        USER_ID,
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


def build_slack_payload(status: str, payload: dict) -> dict:
    """상태와 payload를 기반으로 Slack Block Kit 메시지를 구성"""
    event_name = payload.get("hook_event_name", DEFAULT_VALUE)
    session_id = payload.get("session_id", DEFAULT_VALUE)
    cwd = to_relative_path(payload.get("cwd", DEFAULT_VALUE))
    transcript_path = to_relative_path(payload.get("transcript_path", DEFAULT_VALUE))
    notification_type = payload.get("notification_type", DEFAULT_VALUE)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    project_name = cwd.rsplit("/", 1)[-1] if cwd != DEFAULT_VALUE else ""

    # 상태별 UI 테마 및 필드 구성
    if status == STATUS_WAIT:
        header_text = f"🚨 Claude Code [{project_name}]: 입력 대기 중"
        color = COLOR_WARNING
        msg = payload.get("message", "권한 승인이나 프롬프트 입력이 필요합니다.")
        fields = [
            {"type": "mrkdwn", "text": f"*이벤트 타입:*\n{event_name}"},
            {"type": "mrkdwn", "text": f"*알림 유형:*\n{notification_type}"},
            {"type": "mrkdwn", "text": f"*작업 경로:*\n`{cwd}`"},
        ]
    else:
        header_text = f"✅ Claude Code [{project_name}]: 작업 완료"
        color = COLOR_SUCCESS
        last_message = payload.get("last_assistant_message", "")
        if len(last_message) > MAX_MESSAGE_LENGTH:
            last_message = last_message[:MAX_MESSAGE_LENGTH] + "..."
        msg = last_message or "작업이 완료되었습니다."
        permission_mode = payload.get("permission_mode", DEFAULT_VALUE)
        fields = [
            {"type": "mrkdwn", "text": f"*이벤트 타입:*\n{event_name}"},
            {"type": "mrkdwn", "text": f"*작업 경로:*\n`{cwd}`"},
            {"type": "mrkdwn", "text": f"*권한 모드:*\n{permission_mode}"},
        ]

    # 푸시 알림 미리보기 텍스트
    preview_msg = msg[:MAX_PREVIEW_LENGTH] + "..." if len(msg) > MAX_PREVIEW_LENGTH else msg
    status_emoji = "🚨" if status == STATUS_WAIT else "✅"
    status_label = "입력 대기 중" if status == STATUS_WAIT else "작업 완료"
    preview_text = f"*{status_emoji} [{project_name}] {status_label}*\n{preview_msg}"

    return {
        "channel": USER_ID,
        "text": preview_text,
        "attachments": [
            {
                "color": color,
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": header_text, "emoji": True},
                    },
                    {"type": "section", "text": {"type": "mrkdwn", "text": f"*{msg}*"}},
                    {"type": "section", "fields": fields},
                    {"type": "divider"},
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"🕒 {current_time} | 🔑 세션: {session_id}\n📝 `{transcript_path}`",
                            }
                        ],
                    },
                ],
            }
        ],
    }


def send_to_slack(slack_data: dict) -> None:
    """Slack API로 메시지를 전송"""
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json",
    }

    logger.debug("Slack payload to send: %s", json.dumps(slack_data, ensure_ascii=False))

    try:
        response = requests.post(API_URL, headers=headers, json=slack_data, timeout=5)
        logger.info("Slack API response status: %s", response.status_code)
        logger.debug("Slack API raw response: %s", response.text)

        response.raise_for_status()

        result = response.json()
        if not result.get("ok"):
            error_msg = result.get("error")
            logger.error("Slack API logical error: %s", error_msg)
            print(f"Slack API Error: {error_msg}", file=sys.stderr)
        else:
            logger.info("Slack API call succeeded: ts=%s, channel=%s", result.get("ts"), result.get("channel"))

    except requests.exceptions.RequestException as e:
        logger.exception("Request to Slack failed: %s", e)
        print(f"Request Error: {e}", file=sys.stderr)


def send_slack_notification(status: str) -> None:
    """메인 알림 함수: stdin 파싱 → 메시지 구성 → Slack 전송"""
    logger.info("send_slack_notification called with status=%s", status)

    # 환경변수 검증
    if not SLACK_BOT_TOKEN or not USER_ID:
        logger.error(
            "Missing required environment variables. SLACK_BOT_TOKEN set: %s, USER_ID: %s",
            bool(SLACK_BOT_TOKEN),
            USER_ID,
        )
        print("Missing SLACK_BOT_TOKEN or USER_ID", file=sys.stderr)
        return

    payload = parse_stdin()

    # idle_prompt는 이미 다른 알림이 발생한 후 사용자 미응답 시 발생하는 중복 알림이므로 무시
    notification_type = payload.get("notification_type", DEFAULT_VALUE)
    if notification_type == "idle_prompt":
        logger.info("idle_prompt 알림 무시 (중복 알림)")
        return

    logger.debug("Parsed payload: %s", json.dumps(payload, indent=2, ensure_ascii=False))
    logger.info(
        "Notification context - event_name=%s, session_id=%s, cwd=%s",
        payload.get("hook_event_name", DEFAULT_VALUE),
        payload.get("session_id", DEFAULT_VALUE),
        payload.get("cwd", DEFAULT_VALUE),
    )

    slack_data = build_slack_payload(status, payload)
    send_to_slack(slack_data)

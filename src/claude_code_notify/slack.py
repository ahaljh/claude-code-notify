# slack.py — Slack Bot Token + DM 방식 알림 provider

import json
import logging
import sys
from getpass import getpass

import requests

logger = logging.getLogger(__name__)

API_URL = "https://slack.com/api/chat.postMessage"
COLOR_WAIT = "#FFA500"
COLOR_DONE = "#36A64F"


def is_configured(config: dict) -> bool:
    """Slack 전송에 필요한 설정 키가 모두 존재하는지 확인"""
    return bool(config.get("SLACK_BOT_TOKEN")) and bool(config.get("USER_ID"))


def build_payload(ctx, config: dict) -> dict:
    """NotificationContext → Slack Block Kit 메시지"""
    color = COLOR_WAIT if ctx.status == "wait" else COLOR_DONE
    current_time = ctx.timestamp.strftime("%Y-%m-%d %H:%M:%S")

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": ctx.header, "emoji": True},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{ctx.message}*"}},
    ]
    # Slack은 빈 fields 배열을 허용하지 않으므로 있을 때만 추가
    if ctx.fields:
        blocks.append(
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*{name}:*\n{value}"}
                    for name, value in ctx.fields
                ],
            }
        )
    blocks.extend(
        [
            {"type": "divider"},
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"🕒 {current_time} | 🔑 세션: {ctx.session_id}\n📝 `{ctx.transcript_path}`",
                    }
                ],
            },
        ]
    )

    return {
        "channel": config.get("USER_ID"),
        "text": ctx.preview,
        "attachments": [{"color": color, "blocks": blocks}],
    }


def send(ctx, config: dict) -> bool:
    """Slack API로 메시지를 전송. 성공 여부를 반환 (예외는 삼킴)"""
    slack_data = build_payload(ctx, config)
    headers = {
        "Authorization": f"Bearer {config.get('SLACK_BOT_TOKEN')}",
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
            return False

        logger.info(
            "Slack API call succeeded: ts=%s, channel=%s",
            result.get("ts"),
            result.get("channel"),
        )
        return True

    except requests.exceptions.RequestException as e:
        logger.exception("Request to Slack failed: %s", e)
        print(f"Request Error: {e}", file=sys.stderr)
        return False


def prompt_config(existing: dict) -> dict:
    """init용 인터랙티브 입력. 기존 값이 있으면 Enter로 유지 가능"""
    print("\n[Slack 설정]")

    existing_token = existing.get("SLACK_BOT_TOKEN")
    while True:
        prompt = "SLACK_BOT_TOKEN을 입력하세요 (xoxb-...)"
        if existing_token:
            prompt += " [Enter=기존 값 유지]"
        token = getpass(f"{prompt}: ")
        if not token and existing_token:
            token = existing_token
            print("  ✓ 기존 토큰 유지")
            break
        if token.startswith("xoxb-"):
            print(f"  ✓ 토큰 입력 완료 ({token[:8]}...{token[-4:]})")
            break
        print("  올바른 Bot Token을 입력해주세요 (xoxb-로 시작해야 합니다).")

    existing_user_id = existing.get("USER_ID")
    while True:
        prompt = "USER_ID를 입력하세요 (Slack 프로필 > 멤버 ID 복사, U로 시작)"
        if existing_user_id:
            prompt += f" [Enter={existing_user_id}]"
        user_id = input(f"{prompt}: ")
        if not user_id and existing_user_id:
            user_id = existing_user_id
            break
        if user_id.startswith("U"):
            break
        print("  올바른 User ID를 입력해주세요 (U로 시작해야 합니다).")

    return {"SLACK_BOT_TOKEN": token, "USER_ID": user_id}

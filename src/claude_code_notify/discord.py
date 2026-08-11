# discord.py — Discord Webhook 방식 알림 provider

import json
import logging
import re
import sys

import requests

logger = logging.getLogger(__name__)

WEBHOOK_URL_PATTERN = re.compile(
    r"^https://(discord|discordapp)\.com/api/webhooks/\d+/\S+$"
)
COLOR_WAIT = 0xFFA500
COLOR_DONE = 0x36A64F

# Discord embed 제약
MAX_FIELD_VALUE_LENGTH = 1024
MAX_DESCRIPTION_LENGTH = 4096


def is_configured(config: dict) -> bool:
    """Discord 전송에 필요한 설정 키가 존재하는지 확인"""
    return bool(config.get("DISCORD_WEBHOOK_URL"))


def _clamp(text: str, limit: int) -> str:
    """Discord 길이 제약을 넘는 텍스트를 자름"""
    return text if len(text) <= limit else text[: limit - 3] + "..."


def build_payload(ctx, config: dict) -> dict:
    """NotificationContext → Discord embed 메시지"""
    color = COLOR_WAIT if ctx.status == "wait" else COLOR_DONE

    embed = {
        "title": ctx.header,
        "description": _clamp(f"**{ctx.message}**", MAX_DESCRIPTION_LENGTH),
        "color": color,
        "footer": {"text": f"세션: {ctx.session_id}\n📝 {ctx.transcript_path}"},
        "timestamp": ctx.timestamp.astimezone().isoformat(),
    }
    if ctx.fields:
        # Discord는 빈 field value를 허용하지 않으므로 N/A로 대체
        embed["fields"] = [
            {
                "name": name,
                "value": _clamp(value, MAX_FIELD_VALUE_LENGTH) or "N/A",
                "inline": name != "작업 경로",
            }
            for name, value in ctx.fields
        ]

    return {"content": ctx.preview, "embeds": [embed]}


def send(ctx, config: dict) -> bool:
    """Discord Webhook으로 메시지를 전송. 성공 여부를 반환 (예외는 삼킴)"""
    payload = build_payload(ctx, config)
    url = config.get("DISCORD_WEBHOOK_URL")

    logger.debug("Discord payload to send: %s", json.dumps(payload, ensure_ascii=False))

    try:
        response = requests.post(url, json=payload, timeout=5)
        logger.info("Discord webhook response status: %s", response.status_code)
        logger.debug("Discord webhook raw response: %s", response.text)

        response.raise_for_status()
        logger.info("Discord webhook call succeeded")
        return True

    except requests.exceptions.RequestException as e:
        logger.exception("Request to Discord failed: %s", e)
        print(f"Discord Request Error: {e}", file=sys.stderr)
        return False


def _mask_url(url: str) -> str:
    """webhook URL의 토큰 부분을 마스킹해서 표시"""
    return re.sub(r"(/api/webhooks/\d+/)\S+", r"\1****", url)


def prompt_config(existing: dict) -> dict:
    """init용 인터랙티브 입력. 기존 값이 있으면 Enter로 유지 가능"""
    print("\n[Discord 설정]")
    print("  (Discord 채널 편집 > 연동 > 웹후크에서 URL을 복사하세요)")

    existing_url = existing.get("DISCORD_WEBHOOK_URL")
    while True:
        prompt = "DISCORD_WEBHOOK_URL을 입력하세요"
        if existing_url:
            prompt += f" [Enter={_mask_url(existing_url)}]"
        url = input(f"{prompt}: ").strip()
        if not url and existing_url:
            url = existing_url
            print("  ✓ 기존 Webhook URL 유지")
            break
        if WEBHOOK_URL_PATTERN.match(url):
            print(f"  ✓ Webhook URL 입력 완료 ({_mask_url(url)})")
            break
        print(
            "  올바른 Webhook URL을 입력해주세요"
            " (https://discord.com/api/webhooks/... 형식)."
        )

    return {"DISCORD_WEBHOOK_URL": url}

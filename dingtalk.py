"""钉钉 / 阿里钉 机器人通知：Webhook + 可选加签。

对外钉钉与阿里钉自定义机器人协议通常一致（POST JSON text），
Webhook 域名可能是 oapi.dingtalk.com 或阿里内网域名。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
import urllib.parse
from typing import Any

import requests

from config import Config

logger = logging.getLogger(__name__)

# 常见合法 Webhook 特征（满足其一即可）
_WEBHOOK_HINTS = (
    "access_token=",
    "oapi.dingtalk.com",
    "dingtalk.com",
    "alibaba-inc.com",
    "alibaba.com",
    "/robot/send",
)


def _sign_url(webhook: str, secret: str) -> str:
    """加签：timestamp + secret -> sign，拼到 URL（钉钉/阿里钉通用）。"""
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    sep = "&" if "?" in webhook else "?"
    return f"{webhook}{sep}timestamp={timestamp}&sign={sign}"


def _webhook_looks_valid(webhook: str) -> bool:
    lower = webhook.lower()
    return any(h in lower for h in _WEBHOOK_HINTS) or webhook.startswith("https://")


def send_dingtalk_text(cfg: Config, text: str) -> dict[str, Any] | None:
    """
    发送 text 消息到钉钉/阿里钉群机器人。
    正文会自动带上安全关键词；dry_run 时只打日志。
    """
    keyword = cfg.dingtalk_keyword
    if keyword and keyword not in text:
        text = f"{keyword}\n{text}"

    payload = {
        "msgtype": "text",
        "text": {"content": text},
    }

    if cfg.dry_run:
        logger.info("[DRY_RUN] 钉钉/阿里钉消息预览:\n%s", text)
        return {"dry_run": True}

    if not cfg.dingtalk_webhook:
        logger.error("未配置 DINGTALK_WEBHOOK，无法推送")
        return None
    if not _webhook_looks_valid(cfg.dingtalk_webhook):
        logger.error(
            "DINGTALK_WEBHOOK 格式异常。请粘贴群机器人完整 Webhook（通常含 access_token=）"
        )
        return None

    url = cfg.dingtalk_webhook
    if cfg.dingtalk_secret:
        url = _sign_url(url, cfg.dingtalk_secret)

    headers = {"Content-Type": "application/json; charset=utf-8"}
    try:
        with requests.Session() as session:
            session.trust_env = False
            resp = session.post(
                url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers=headers,
                timeout=cfg.request_timeout,
            )
        resp.raise_for_status()
        body = resp.json()
        if body.get("errcode", 0) != 0:
            logger.error("机器人返回错误: %s", body)
        else:
            logger.info("推送成功: %s", body)
        return body
    except requests.RequestException as exc:
        logger.exception("推送失败: %s", exc)
        return None

"""规避 Cursor/系统代理干扰行情与推送请求。"""

from __future__ import annotations

import os

import requests

_APPLIED = False


def disable_proxies() -> None:
    """清除代理环境变量，并让 requests 默认不信任系统代理（幂等）。"""
    global _APPLIED

    for key in list(os.environ):
        if "proxy" in key.lower():
            del os.environ[key]
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"

    if _APPLIED:
        return

    _orig_init = requests.Session.__init__

    def _init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        _orig_init(self, *args, **kwargs)
        self.trust_env = False

    requests.Session.__init__ = _init  # type: ignore[method-assign]
    _APPLIED = True

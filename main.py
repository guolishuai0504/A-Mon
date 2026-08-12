#!/usr/bin/env python3
"""尾盘策略入口。用法: python main.py [--dry-run]"""

from __future__ import annotations

import argparse
import logging
import sys

from network_fix import disable_proxies

# 必须在业务网络请求前执行，避免 Cursor/系统代理干扰东财
disable_proxies()

from config import load_config
from strategy import run_strategy


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A股尾盘选股 + 钉钉推送")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印结果，不调用钉钉 Webhook",
    )
    args = parser.parse_args(argv)
    setup_logging()

    cfg = load_config()
    if args.dry_run:
        from dataclasses import replace

        cfg = replace(cfg, dry_run=True)

    return run_strategy(cfg)


if __name__ == "__main__":
    sys.exit(main())

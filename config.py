"""策略与通知配置，可通过环境变量覆盖。"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value not in (None, "") else default


@dataclass(frozen=True)
class Config:
    dingtalk_webhook: str
    dingtalk_secret: str
    dingtalk_keyword: str
    dry_run: bool

    # 大盘：红盘家数低于阈值则放弃
    min_up_count: int = 1500

    # 股票池：创业板 300 / 科创板 688
    code_prefixes: tuple[str, ...] = ("300", "688")
    turnover_min: float = 5.0
    turnover_max: float = 15.0
    amount_min: float = 150_000_000  # 成交额（元）
    change_min: float = 2.0
    change_max: float = 6.0
    volume_ratio_min: float = 1.0
    # 距日内最高回撤上限（%）
    max_drawdown_from_high: float = 3.0
    # 预筛后最多取多少只做分时形态检查（控制请求量）
    pattern_check_limit: int = 15
    # 最终推送数量
    top_n: int = 5
    # 分时请求超时与重试
    request_timeout: float = 15.0
    minute_period: str = "1"


def load_config() -> Config:
    return Config(
        dingtalk_webhook=os.getenv("DINGTALK_WEBHOOK", "").strip(),
        dingtalk_secret=os.getenv("DINGTALK_SECRET", "").strip(),
        dingtalk_keyword=os.getenv("DINGTALK_KEYWORD", "尾盘").strip() or "尾盘",
        dry_run=_env_bool("DRY_RUN", False),
        min_up_count=_env_int("MIN_UP_COUNT", 1500),
        turnover_min=_env_float("TURNOVER_MIN", 5.0),
        turnover_max=_env_float("TURNOVER_MAX", 15.0),
        amount_min=_env_float("AMOUNT_MIN", 150_000_000),
        change_min=_env_float("CHANGE_MIN", 2.0),
        change_max=_env_float("CHANGE_MAX", 6.0),
        volume_ratio_min=_env_float("VOLUME_RATIO_MIN", 1.0),
        max_drawdown_from_high=_env_float("MAX_DRAWDOWN_FROM_HIGH", 3.0),
        pattern_check_limit=_env_int("PATTERN_CHECK_LIMIT", 15),
        top_n=_env_int("TOP_N", 5),
    )

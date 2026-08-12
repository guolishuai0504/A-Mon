"""分时形态判断：站上均价、尾盘不破位、非冲高回落。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import akshare as ak
import pandas as pd

logger = logging.getLogger(__name__)

MINUTE_REQUIRED = ("时间", "收盘", "成交量")


@dataclass
class PatternResult:
    ok: bool
    score: float
    reason: str


def code_to_sina_symbol(code: str) -> str:
    code = str(code).zfill(6)
    if code.startswith(("5", "6", "9")):
        return f"sh{code}"
    return f"sz{code}"


def _today_bars(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    times = pd.to_datetime(df["时间"], errors="coerce")
    today = datetime.now().date()
    mask = times.dt.date == today
    out = df.loc[mask].copy()
    out["_dt"] = times.loc[mask]
    return out.sort_values("_dt")


def _normalize_em_minute(df: pd.DataFrame) -> pd.DataFrame:
    return df


def _normalize_sina_minute(df: pd.DataFrame) -> pd.DataFrame:
    """新浪分钟列 day/open/high/low/close/volume -> 统一中文列。"""
    rename = {
        "day": "时间",
        "open": "开盘",
        "high": "最高",
        "low": "最低",
        "close": "收盘",
        "volume": "成交量",
        "amount": "成交额",
    }
    out = df.rename(columns=rename).copy()
    return out


def fetch_minute_bars(symbol: str, period: str = "1") -> pd.DataFrame:
    """东财分钟线优先，失败回退新浪。"""
    # 1) 东财
    try:
        df = ak.stock_zh_a_hist_min_em(symbol=symbol, period=period, adjust="")
        if df is not None and not df.empty:
            df = _normalize_em_minute(df)
            missing = [c for c in MINUTE_REQUIRED if c not in df.columns]
            if not missing:
                return df
            logger.warning("东财分钟线缺列 %s: %s", symbol, missing)
    except Exception as exc:  # noqa: BLE001
        logger.info("东财分钟线失败 %s: %s", symbol, exc)

    # 2) 新浪
    try:
        sina_symbol = code_to_sina_symbol(symbol)
        df = ak.stock_zh_a_minute(symbol=sina_symbol, period="1", adjust="")
        if df is None or df.empty:
            return pd.DataFrame()
        df = _normalize_sina_minute(df)
        missing = [c for c in MINUTE_REQUIRED if c not in df.columns]
        if missing:
            logger.warning("新浪分钟线缺列 %s: %s", symbol, missing)
            return pd.DataFrame()
        return df
    except Exception as exc:  # noqa: BLE001
        logger.warning("分钟线获取失败 %s: %s", symbol, exc)
        return pd.DataFrame()


def evaluate_intraday_pattern(symbol: str, period: str = "1") -> PatternResult:
    """
    尾盘形态规则（尽量轻量、可解释）：
    1. 现价站上当日分时均价（成交量加权）
    2. 最近 20 根 1 分钟线未破位走弱
    3. 尾盘段（14:00 后）相对午后高点回撤可控
    4. 最近 5 分钟不为大幅跳水
    """
    raw = fetch_minute_bars(symbol, period=period)
    if raw.empty:
        return PatternResult(False, 0.0, "无分时数据")

    bars = _today_bars(raw)
    if len(bars) < 30:
        return PatternResult(False, 0.0, f"今日分时过少({len(bars)})")

    close = bars["收盘"].astype(float)
    volume = bars["成交量"].astype(float).clip(lower=0)
    last = float(close.iloc[-1])

    if "均价" in bars.columns and pd.notna(bars["均价"].iloc[-1]):
        vwap = float(bars["均价"].iloc[-1])
    else:
        vol_sum = float(volume.sum())
        vwap = float((close * volume).sum() / vol_sum) if vol_sum > 0 else float(close.mean())

    if last < vwap * 0.998:
        return PatternResult(False, 0.0, f"跌破均价(现价{last:.2f}<均价{vwap:.2f})")

    recent = bars.tail(20)
    recent_low = float(recent["收盘"].astype(float).min())
    if last < recent_low * 1.002 and float(close.iloc[-1]) < float(close.iloc[-5]):
        return PatternResult(False, 0.0, "近20分钟走弱破位")

    afternoon = bars[bars["_dt"].dt.hour >= 14]
    if not afternoon.empty:
        if "最高" in afternoon.columns:
            afternoon_high = float(afternoon["最高"].astype(float).max())
        else:
            afternoon_high = float(afternoon["收盘"].astype(float).max())
        pullback = (afternoon_high - last) / afternoon_high * 100 if afternoon_high > 0 else 0.0
        if pullback > 2.5:
            return PatternResult(False, 0.0, f"午后冲高回落{pullback:.1f}%")

    last5 = close.tail(5)
    if len(last5) >= 5:
        chg5 = (float(last5.iloc[-1]) / float(last5.iloc[0]) - 1.0) * 100
        if chg5 < -1.2:
            return PatternResult(False, 0.0, f"近5分钟急跌{chg5:.1f}%")
    else:
        chg5 = 0.0

    premium = (last / vwap - 1.0) * 100
    score = max(0.0, premium) * 10 + max(0.0, chg5) * 5 + min(len(bars) / 240.0, 1.0) * 5
    return PatternResult(True, score, f"站上均价+{premium:.2f}%/近5分{chg5:+.2f}%")


def score_candidates(
    codes: list[str],
    period: str = "1",
    limit: int = 15,
) -> dict[str, PatternResult]:
    results: dict[str, PatternResult] = {}
    for code in codes[:limit]:
        try:
            results[code] = evaluate_intraday_pattern(code, period=period)
        except Exception as exc:  # noqa: BLE001
            logger.warning("形态评估异常 %s: %s", code, exc)
            results[code] = PatternResult(False, 0.0, f"评估异常: {exc}")
    return results

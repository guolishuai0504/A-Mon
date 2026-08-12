"""行情快照获取：东财优先，新浪回退。"""

from __future__ import annotations

import logging
import time

import akshare as ak
import pandas as pd

logger = logging.getLogger(__name__)

SPOT_REQUIRED_CORE = (
    "代码",
    "名称",
    "最新价",
    "涨跌幅",
    "成交额",
    "最高",
    "最低",
    "今开",
    "昨收",
)

NUMERIC_COLS = (
    "最新价",
    "涨跌幅",
    "成交额",
    "换手率",
    "最高",
    "最低",
    "今开",
    "昨收",
    "量比",
    "振幅",
    "5分钟涨跌",
)


def _normalize_numeric(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in NUMERIC_COLS:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    out["代码"] = out["代码"].astype(str).str.extract(r"(\d{6})", expand=False).fillna("")
    out = out[out["代码"].str.len() == 6]
    return out


def _from_eastmoney() -> pd.DataFrame:
    df = ak.stock_zh_a_spot_em()
    if df is None or df.empty:
        raise RuntimeError("stock_zh_a_spot_em 返回空数据")
    missing = [c for c in SPOT_REQUIRED_CORE + ("换手率",) if c not in df.columns]
    if missing:
        raise KeyError(f"东财行情缺列 {missing}")
    out = _normalize_numeric(df)
    out.attrs["source"] = "eastmoney"
    return out


def _from_sina() -> pd.DataFrame:
    df = ak.stock_zh_a_spot()
    if df is None or df.empty:
        raise RuntimeError("stock_zh_a_spot 返回空数据")
    missing = [c for c in SPOT_REQUIRED_CORE if c not in df.columns]
    if missing:
        raise KeyError(f"新浪行情缺列 {missing}；实际列: {list(df.columns)}")
    out = _normalize_numeric(df)
    # 新浪无换手率/量比，占位后由筛选逻辑自动跳过
    if "换手率" not in out.columns:
        out["换手率"] = pd.NA
    if "量比" not in out.columns:
        out["量比"] = pd.NA
    out.attrs["source"] = "sina"
    logger.warning("已回退新浪行情：无换手率/量比，将仅用成交额做流动性过滤")
    return out


def fetch_spot(retries: int = 2) -> pd.DataFrame:
    """先东财，失败后新浪。"""
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return _from_eastmoney()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("东财行情失败 (%d/%d): %s", attempt, retries, exc)
            if attempt < retries:
                time.sleep(1.2 * attempt)

    logger.warning("东财不可用，切换新浪: %s", last_exc)
    return _from_sina()

"""行情快照获取：东财优先；失败则新浪 + 腾讯补全换手率/量比。"""

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
    out = out[out["代码"].str.len() == 6].copy()
    return out


def _from_eastmoney() -> pd.DataFrame:
    df = ak.stock_zh_a_spot_em()
    if df is None or df.empty:
        raise RuntimeError("stock_zh_a_spot_em 返回空数据")
    missing = [c for c in SPOT_REQUIRED_CORE + ("换手率", "量比") if c not in df.columns]
    if missing:
        raise KeyError(f"东财行情缺列 {missing}")
    out = _normalize_numeric(df)
    out.attrs["source"] = "eastmoney"
    return out


def _fetch_tencent_hsl_lb() -> pd.DataFrame:
    """腾讯全市场快照：hsl=换手率, lb=量比。"""
    df = ak.stock_zh_a_spot_tx()
    if df is None or df.empty:
        raise RuntimeError("stock_zh_a_spot_tx 返回空数据")
    need = {"code", "hsl", "lb"}
    if not need.issubset(df.columns):
        raise KeyError(f"腾讯行情缺列 {need - set(df.columns)}")
    out = pd.DataFrame(
        {
            "代码": df["code"].astype(str).str.extract(r"(\d{6})", expand=False),
            "换手率": pd.to_numeric(df["hsl"], errors="coerce"),
            "量比": pd.to_numeric(df["lb"], errors="coerce"),
        }
    )
    out = out[out["代码"].str.len() == 6].drop_duplicates(subset=["代码"], keep="first")
    return out


def _enrich_turnover_volume_ratio(base: pd.DataFrame) -> pd.DataFrame:
    """为缺少换手率/量比的行情表补全指标。"""
    out = base.copy()
    source = str(base.attrs.get("source", "sina"))
    need_hsl = "换手率" not in out.columns or out["换手率"].isna().all()
    need_lb = "量比" not in out.columns or out["量比"].isna().all()
    if not need_hsl and not need_lb:
        out.attrs["source"] = source
        return out

    try:
        tx = _fetch_tencent_hsl_lb()
    except Exception as exc:  # noqa: BLE001
        logger.warning("腾讯换手率/量比补全失败: %s", exc)
        if "换手率" not in out.columns:
            out["换手率"] = pd.NA
        if "量比" not in out.columns:
            out["量比"] = pd.NA
        out.attrs["source"] = source
        return out

    out = out.drop(columns=[c for c in ("换手率", "量比") if c in out.columns], errors="ignore")
    out = out.merge(tx, on="代码", how="left")
    covered = int(out["换手率"].notna().sum())
    logger.info("已用腾讯行情补全换手率/量比：覆盖 %d/%d", covered, len(out))
    out.attrs["source"] = f"{source}+tencent"
    return out


def _from_sina() -> pd.DataFrame:
    df = ak.stock_zh_a_spot()
    if df is None or df.empty:
        raise RuntimeError("stock_zh_a_spot 返回空数据")
    missing = [c for c in SPOT_REQUIRED_CORE if c not in df.columns]
    if missing:
        raise KeyError(f"新浪行情缺列 {missing}；实际列: {list(df.columns)}")
    out = _normalize_numeric(df)
    out.attrs["source"] = "sina"
    out = _enrich_turnover_volume_ratio(out)
    return out


def fetch_spot(retries: int = 2) -> pd.DataFrame:
    """先东财，失败后新浪并补全换手率/量比。"""
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return _from_eastmoney()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("东财行情失败 (%d/%d): %s", attempt, retries, exc)
            if attempt < retries:
                time.sleep(1.2 * attempt)

    logger.warning("东财不可用，切换新浪+腾讯补全: %s", last_exc)
    return _from_sina()

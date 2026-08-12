"""尾盘选股主流程：快照初筛 + 分时形态 + 钉钉推送。"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from config import Config, load_config
from dingtalk import send_dingtalk_text
from pattern import score_candidates
from spot import fetch_spot

logger = logging.getLogger(__name__)


def _is_st(name: str) -> bool:
    return "ST" in str(name).upper()


def filter_market_risk(df: pd.DataFrame, cfg: Config) -> tuple[bool, int, str]:
    up_count = int((df["涨跌幅"] > 0).sum())
    if up_count < cfg.min_up_count:
        return False, up_count, f"今日全市场红盘仅 {up_count} 家，大盘风险过高，取消尾盘买入。"
    return True, up_count, ""


def screen_universe(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """流动性 + 涨幅 + 换手率 + 量比 + 形态粗滤。"""
    required_metrics = ("换手率", "量比")
    missing_cols = [c for c in required_metrics if c not in df.columns]
    if missing_cols:
        raise KeyError(f"策略需要字段 {missing_cols}，当前行情未提供")

    before = len(df)
    df = df.dropna(subset=["换手率", "量比"]).copy()
    dropped = before - len(df)
    if dropped:
        logger.info("因缺少换手率/量比剔除 %d 只", dropped)

    prefixes = cfg.code_prefixes
    mask = (
        df["代码"].str.startswith(prefixes)
        & ~df["名称"].map(_is_st)
        & (df["成交额"] >= cfg.amount_min)
        & (df["涨跌幅"] >= cfg.change_min)
        & (df["涨跌幅"] <= cfg.change_max)
        & (df["换手率"] >= cfg.turnover_min)
        & (df["换手率"] <= cfg.turnover_max)
        & (df["量比"] >= cfg.volume_ratio_min)
        & (df["最新价"] > df["今开"])
        & (df["最新价"] > 0)
        & (df["最高"] > 0)
    )

    out = df.loc[mask].copy()
    out["高点回撤"] = (out["最高"] - out["最新价"]) / out["最高"] * 100
    out = out[out["高点回撤"] <= cfg.max_drawdown_from_high]
    out = out[out["涨跌幅"] < 18]
    # 量比高 + 换手适中的优先：后续形态分之外的二级排序键
    out = out.sort_values(by=["涨跌幅", "量比"], ascending=False)
    logger.info(
        "初筛条件: 换手[%.1f, %.1f]%% 量比>=%.2f 成交额>=%.0f",
        cfg.turnover_min,
        cfg.turnover_max,
        cfg.volume_ratio_min,
        cfg.amount_min,
    )
    return out


def apply_pattern_filter(candidates: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    if candidates.empty:
        return candidates

    codes = candidates["代码"].tolist()
    pattern_map = score_candidates(
        codes,
        period=cfg.minute_period,
        limit=cfg.pattern_check_limit,
    )

    rows = []
    for _, row in candidates.iterrows():
        code = row["代码"]
        result = pattern_map.get(code)
        if result is None or not result.ok:
            if result is not None:
                logger.info("剔除 %s %s: %s", code, row["名称"], result.reason)
            continue
        item = row.to_dict()
        item["形态分"] = result.score
        item["形态说明"] = result.reason
        rows.append(item)

    if not rows:
        return pd.DataFrame()

    ranked = pd.DataFrame(rows)
    # 形态分优先，其次涨幅、量比
    ranked = ranked.sort_values(by=["形态分", "涨跌幅", "量比"], ascending=False)
    return ranked.head(cfg.top_n)


def format_report(up_count: int, picks: pd.DataFrame, source: str = "") -> str:
    src = f"（数据源: {source}）" if source else ""
    lines = [
        "【量化通知】尾盘策略筛选结果",
        f"大盘安全（红盘 {up_count} 家）{src}。",
        "今日精选股票池如下，请于 14:50 后观察分时图择机买入：",
        "",
    ]
    for i, row in enumerate(picks.itertuples(index=False), start=1):
        pattern_note = getattr(row, "形态说明", "")
        drawdown = getattr(row, "高点回撤", None)
        turnover = getattr(row, "换手率", None)
        vol_ratio = getattr(row, "量比", None)
        dd_txt = f" | 高回撤: {drawdown:.2f}%" if drawdown is not None and pd.notna(drawdown) else ""
        to_txt = f" | 换手: {float(turnover):.2f}%" if turnover is not None and pd.notna(turnover) else ""
        lb_txt = f" | 量比: {float(vol_ratio):.2f}" if vol_ratio is not None and pd.notna(vol_ratio) else ""
        lines.append(
            f"{i}. {row.代码} {row.名称} | 现价: {row.最新价} | "
            f"涨幅: {row.涨跌幅}%{to_txt}{lb_txt}{dd_txt}"
        )
        if pattern_note:
            lines.append(f"   形态: {pattern_note}")
    lines.append("")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(lines)


def run_strategy(cfg: Config | None = None) -> int:
    """执行策略。返回进程退出码：0 成功，1 业务取消/无标的，2 异常。"""
    cfg = cfg or load_config()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("开始执行策略选股... 当前时间: %s", now_str)

    try:
        market = fetch_spot()
    except Exception as exc:  # noqa: BLE001
        logger.exception("数据获取失败")
        send_dingtalk_text(cfg, f"【量化通知】尾盘数据获取失败：{exc}")
        return 2

    source = str(market.attrs.get("source", "unknown"))
    logger.info("行情来源=%s, 行数=%d", source, len(market))

    ok, up_count, risk_msg = filter_market_risk(market, cfg)
    if not ok:
        send_dingtalk_text(cfg, f"【量化通知】{risk_msg}")
        return 1

    qualified = screen_universe(market, cfg)
    logger.info("初筛通过 %d 只", len(qualified))

    if qualified.empty:
        send_dingtalk_text(
            cfg,
            "【量化通知】尾盘：大盘安全，但未筛选出符合流动性与涨幅要求的候选股。",
        )
        return 1

    picks = apply_pattern_filter(qualified, cfg)
    if picks.empty:
        send_dingtalk_text(
            cfg,
            "【量化通知】尾盘：初筛有候选，但分时形态均未通过（破均价/冲高回落/急跌）。",
        )
        return 1

    content = format_report(up_count, picks, source=source)
    send_dingtalk_text(cfg, content)
    logger.info("推送完成，标的数=%d", len(picks))
    return 0

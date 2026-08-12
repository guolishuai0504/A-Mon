# A股尾盘选股 + 钉钉/阿里钉推送

本地用 `akshare` 拉全市场快照，按流动性/涨幅初筛，再拉 1 分钟分时做形态过滤，最后推送到钉钉或阿里钉群机器人。

## 快速开始

```bash
cd /Users/shuai/code/A
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，填入 DINGTALK_WEBHOOK
python main.py --dry-run
```

## 筛选逻辑

1. **大盘熔断**：红盘家数 `< MIN_UP_COUNT`（默认 1500）则放弃
2. **初筛**：代码 `300`/`688`，非 ST，换手 5%–15%（有该字段时），成交额 ≥ 1.5 亿，涨幅 2%–6%，现价 > 今开，量比 ≥ 1（有该字段时），距日内高点回撤 ≤ 3%
3. **分时形态**（最多检查前 15 只）：站上分时均价、近 20 分钟不破位、午后回撤可控、近 5 分钟不急跌
4. **推送**：按形态分 + 涨幅取 Top 5

行情优先东财；不可用时自动回退新浪（新浪无换手率/量比时会跳过对应过滤）。

## 钉钉 / 阿里钉配置

1. 群 → 智能群助手 → 自定义机器人
2. 安全设置勾选「自定义关键词」，关键词设为 `尾盘`（或与 `DINGTALK_KEYWORD` 一致）
3. 可选「加签」，把密钥写入 `DINGTALK_SECRET`
4. Webhook 写入 `.env` 的 `DINGTALK_WEBHOOK`（勿提交仓库）

阿里钉与对外钉钉协议通常一致，把群里复制的完整 Webhook 填入即可。

GitHub Actions 请在仓库 **Settings → Secrets** 添加：

- `DINGTALK_WEBHOOK`（必填）
- `DINGTALK_SECRET`（可选）

## 定时任务

### 本机 crontab

```bash
chmod +x scripts/install_crontab.sh
./scripts/install_crontab.sh
```

或手动参考 `scripts/crontab.example`（交易日 **14:45**）。

### GitHub Actions

工作流：`.github/workflows/tail-strategy.yml`

- 定时：UTC `06:45`（北京时间 14:45），周一到周五
- 会尽量用交易日历跳过休市日
- 也可在 Actions 页手动 **Run workflow**

注意：GitHub hosted runner 在海外，访问行情接口偶发超时；若不稳定，优先用本机 crontab。

若本机出现 `ProxyError`，先检查环境变量 `HTTP_PROXY`/`HTTPS_PROXY`，或直接：

```bash
python main.py --dry-run
```

（程序启动时会尝试清除代理干扰。）

## 目录

| 文件 | 说明 |
| --- | --- |
| `main.py` | 入口 |
| `strategy.py` | 选股主流程 |
| `spot.py` | 东财/新浪行情 |
| `pattern.py` | 分时形态 |
| `dingtalk.py` | 钉钉/阿里钉推送（关键词 / 加签） |
| `network_fix.py` | 代理规避 |
| `config.py` | 环境变量配置 |

## 代码审查要点（已处理）

- Webhook 走环境变量，不硬编码；兼容阿里钉域名
- 消息自动带上安全关键词，避免机器人拒收
- 校验行情核心列名；数值列强制转换；代码规范化为 6 位
- 单票分时失败不影响整批；推送与请求带 timeout
- 支持 `--dry-run` / `DRY_RUN=true` 本地演练

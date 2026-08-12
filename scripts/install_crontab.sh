#!/usr/bin/env bash
# 安装本机 crontab（会追加一条，不覆盖其他任务）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${ROOT}/.venv/bin/python"
LOG_DIR="${ROOT}/logs"
CRON_LINE="45 14 * * 1-5 cd ${ROOT} && ${PYTHON} main.py >> ${LOG_DIR}/cron.log 2>&1"

mkdir -p "${LOG_DIR}"

if [[ ! -x "${PYTHON}" ]]; then
  echo "未找到 ${PYTHON}，请先: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

if [[ ! -f "${ROOT}/.env" ]]; then
  echo "缺少 ${ROOT}/.env，请先: cp .env.example .env 并填写 DINGTALK_WEBHOOK"
  exit 1
fi

# 已存在则跳过
if crontab -l 2>/dev/null | grep -F "${ROOT}" | grep -q "main.py"; then
  echo "已存在指向本项目的 crontab，跳过安装"
  crontab -l
  exit 0
fi

(crontab -l 2>/dev/null || true; echo "${CRON_LINE}") | crontab -
echo "已安装:"
echo "  ${CRON_LINE}"
echo
crontab -l

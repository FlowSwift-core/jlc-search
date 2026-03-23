#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="$PROJECT_DIR/data"
DB_LIVE="$DATA_DIR/jlc_search.db"
BOT_TOKEN="${TELEGRAM_BOT_TOKEN}"
CHAT_ID="${TELEGRAM_CHAT_ID}"

send_telegram() {
    if [ -n "$BOT_TOKEN" ] && [ -n "$CHAT_ID" ]; then
        curl -s "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
            -d "chat_id=${CHAT_ID}&text=$1&parse_mode=Markdown" > /dev/null 2>&1
    fi
}

cd "$PROJECT_DIR"

# 加载环境变量
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# 激活虚拟环境
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

echo "=== JLC Search 更新开始 $(date) ==="
send_telegram "🔄 *JLC Search* 开始每日更新..."

# 运行原子更新（不指定 --output，使用默认路径）
if python -m jlc_search.update_pipeline --atomic --skip-verify 2>&1; then
    echo "=== 更新完成 $(date) ==="
    send_telegram "✅ *JLC Search* 更新完成！"
else
    echo "=== 更新失败 $(date) ==="
    send_telegram "❌ *JLC Search* 更新失败！请检查日志。"
    exit 1
fi

#!/bin/bash
API_URL="${JLC_API_URL:-http://localhost:8000/health}"
BOT_TOKEN="${TELEGRAM_BOT_TOKEN}"
CHAT_ID="${TELEGRAM_CHAT_ID}"

response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$API_URL")

if [ "$response" != "200" ]; then
    curl -s "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d "chat_id=${CHAT_ID}&text=⚠️ *JLC API* 停止响应 (HTTP ${response})&parse_mode=Markdown"
    echo "$(date): API 健康检查失败 (HTTP $response)"
else
    echo "$(date): API 正常"
fi

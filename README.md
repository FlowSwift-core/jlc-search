# JLC Search

嘉立创元件库搜索 API，支持 FTS5 全文搜索 + BM25 排序 + Regexp。

## 数据源

- [jlcparts](https://github.com/yaqwsx/jlcparts) - 11GB SQLite 数据库，每天自动更新
- [JLCPCB API](https://cart.jlcpcb.com) - Datasheet URL 采集

## 功能

- FTS5 全文搜索 + BM25 排序
- Regexp 正则表达式查询
- 只读 SQL 查询 API（带超时保护）
- Telegram 监控报警
- 零停机更新（原子替换）

## 快速开始

```bash
# 安装依赖
uv venv && source .venv/bin/activate
uv pip install -e .

# 初始化数据库（首次，需较长时间）
python -m jlc_search.update_pipeline --output data/jlc_search.db

# 启动 API
pm2 start ecosystem.config.js

# 安装 Telegram 通知
pm2 install pm2-telegram
pm2 set pm2-telegram:bot_token YOUR_TOKEN
pm2 set pm2-telegram:chat_id YOUR_CHAT_ID
```

## API 文档

启动后访问 http://localhost:8000/docs

### 查询接口

- `GET /health` - 健康检查
- `GET /search?q=STM32&limit=20` - 简易搜索
- `POST /query` - SQL 查询

### SQL 查询示例

```json
{
  "sql": "SELECT lcsc, mfr, package, bm25(components_fts) as rank FROM components_fts WHERE components_fts MATCH 'STM32 ARM' ORDER BY rank LIMIT 20",
  "timeout": 5000
}
```

### Regexp 查询

```json
{
  "sql": "SELECT * FROM components WHERE mfr REGEXP '^RC0603.*1K0' AND is_basic = 1 LIMIT 20"
}
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DB_PATH` | 数据库路径 | `data/jlc_search.db` |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | - |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID | - |
| `JLC_API_URL` | API 健康检查地址 | `http://localhost:8000/health` |

## 监控

- PM2 进程管理 + pm2-telegram 模块
- 健康检查脚本（crontab 每分钟运行）

```bash
# 添加健康检查 crontab
crontab -e
# 添加：
* * * * * /root/work/jlc-pcb-components/scripts/healthcheck.sh >> /var/log/jlc-healthcheck.log 2>&1
```

## License

MIT

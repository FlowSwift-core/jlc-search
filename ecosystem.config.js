module.exports = {
  apps: [
    {
      name: 'jlc-api',
      script: 'uvicorn',
      args: 'jlc_search.api:app --host 0.0.0.0 --port 8003',
      interpreter: '/root/work/jlc-pcb-components/.venv/bin/python3',
      cwd: '/root/work/jlc-pcb-components',
      env: {
        DB_PATH: '/root/work/jlc-pcb-components/data/jlc_search.db',
        PYTHONPATH: '/root/work/jlc-pcb-components/src',
      },
      max_memory_restart: '500M',
      error_file: '/root/.pm2/logs/jlc-api-error.log',
      out_file: '/root/.pm2/logs/jlc-api-out.log',
    },
    {
      name: 'jlc-update',
      script: '/root/work/jlc-pcb-components/scripts/update.sh',
      interpreter: 'bash',
      cron_restart: '0 4 * * *',
      autorestart: false,
      watch: false,
      env: {
        TELEGRAM_BOT_TOKEN: '6113313921:AAFjz_-FDprxiYZM_wuehJrCZOmXcCPtVXQ',
        TELEGRAM_CHAT_ID: '1029979132',
      },
      error_file: '/root/.pm2/logs/jlc-update-error.log',
      out_file: '/root/.pm2/logs/jlc-update-out.log',
    },
  ],
};

uvicorn user_registry_service:app --host 0.0.0.0 --port 8000 &
# бот
python simple_telegram_bot.py &
# Pi-скрипт
REGISTRY_URL=http://<ip>:8000 python meter_watcher.py
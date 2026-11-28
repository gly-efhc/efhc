from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_process_update_passes_db_into_dispatcher_feed_update():
    src = read("backend/app/bot/bot.py")
    fn = src.split("async def process_update", 1)[1]
    fn = fn.split("async def require_subscription_text", 1)[0]
    assert "dp.feed_update(bot, update, db=db)" in fn
    assert "feed_raw_update" not in fn


def test_telegram_webhook_uses_process_update_with_route_db():
    src = read("backend/app/routes/system_routes.py")
    fn = src.split("async def telegram_webhook", 1)[1]
    assert "process_update" in fn
    assert "await process_update(db=db, payload=payload)" in fn
    assert "feed_raw_update" not in fn
    assert "dp.bot" not in fn


def test_dispatcher_registers_middlewares():
    src = read("backend/app/bot/bot.py")
    fn = src.split("def get_dispatcher", 1)[1]
    fn = fn.split("async def process_update", 1)[0]
    assert "DBSessionMiddleware()" in fn
    assert "UpdateIdempotencyMiddleware()" in fn
    assert "SubscriptionProbeMiddleware()" in fn

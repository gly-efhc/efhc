from pathlib import Path

root = Path(__file__).resolve().parents[2]
svc = (root / "backend/app/services/orders_service.py").read_text()
admin = (root / "backend/app/routes/admin_shop_routes.py").read_text()
assert "legacy shop write path is disabled" in svc
assert "/order/legacy/" in admin
assert "/orders/user/legacy/" in admin
print(
    "ok: legacy shop write paths blocked; legacy reads remain visible"
)

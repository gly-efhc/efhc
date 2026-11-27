import json
from pathlib import Path

root = Path(__file__).resolve().parents[3] / "main"
pi = (
    root / "backend/app/services/payment_intents_service.py"
).read_text()
spec = json.loads((root / "backend/openapi/openapi.json").read_text())
assert "PENDING_INTENT_LIMIT = 5" in pi
assert "_assert_pending_intent_limit" in pi
assert "/shopfront/create-intent" in spec.get("paths", {})
print("ok: openapi snapshot present and pending-intent guard exists")

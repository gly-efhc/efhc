from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_late_referral_binding_surface_is_removed() -> None:
    routes = (ROOT / "backend/app/routes/referrals_routes.py").read_text(
        encoding="utf-8"
    )
    frontend = (
        ROOT / "frontend/src/services/referrals.service.ts"
    ).read_text(encoding="utf-8")
    assert '"/bind"' not in routes
    assert '"/attach"' not in routes
    assert "/referrals/bind" not in frontend
    assert "/referrals/attach" not in frontend

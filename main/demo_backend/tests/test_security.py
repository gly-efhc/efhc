from demo_backend.security import is_external_blocked


def test_tonconnect_and_provider_endpoints_are_routed():
    # Proof checks happen in the genuine backend, never as mock success.
    for method, path in [
        ("POST", "/api/auth/ton/challenge"),
        ("POST", "/api/auth/ton/proof"),
        ("GET", "/api/wallets/tonconnect/proof-payload"),
        ("POST", "/api/wallets/tonconnect/check-proof"),
        ("POST", "/api/wallets/connect"),
        ("POST", "/api/deposit/direct-open"),
        ("POST", "/api/shopfront/create-intent"),
        ("GET", "/api/ads/postback/monetag"),
        ("POST", "/api/admin/ton/reconcile"),
        ("POST", "/api/admin/withdrawals/42/mark-paid"),
    ]:
        assert not is_external_blocked(method, path)


def test_core_economic_routes_are_preserved():
    for method, path in [
        ("POST", "/api/sync/me"),
        ("POST", "/api/panels/activate"),
        ("POST", "/api/exchange/convert"),
        ("GET", "/api/admin/reports/overview"),
        ("POST", "/api/staging/topup"),
    ]:
        assert not is_external_blocked(method, path)

from app.routes import referrals_routes


def test_referral_bind_route_is_not_exposed() -> None:
    paths = {
        getattr(route, "path", "")
        for route in referrals_routes.router.routes
    }
    assert "/bind" not in paths
    assert "/attach" not in paths
    assert not hasattr(referrals_routes, "bind_referral_code")
    assert not hasattr(referrals_routes, "attach_referral_code")


def test_referral_routes_are_read_only_for_existing_users() -> None:
    methods_by_path = {
        getattr(route, "path", ""): set(getattr(route, "methods", set()))
        for route in referrals_routes.router.routes
    }
    assert methods_by_path
    assert all("POST" not in methods for methods in methods_by_path.values())

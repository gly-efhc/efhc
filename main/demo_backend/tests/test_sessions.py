from __future__ import annotations
from demo_backend.session_store import DemoSessionStore


def test_switch_invalidates_old_identity():
    sessions = DemoSessionStore()
    first = sessions.issue("0000000002")
    assert sessions.get(first.token).global_id == "0000000002"
    next_ = sessions.replace(first.token, "0000000088")
    assert next_.global_id == "0000000088"
    assert next_.csrf != first.csrf
    assert sessions.get(first.token) is None
    assert sessions.get(next_.token) == next_
    assert sessions.revoke(next_.token)
    assert sessions.get(next_.token) is None


def test_unknown_session_is_denied():
    sessions = DemoSessionStore()
    assert sessions.get("real-production-token") is None
    assert sessions.replace("real-production-token", "0000000088") is None

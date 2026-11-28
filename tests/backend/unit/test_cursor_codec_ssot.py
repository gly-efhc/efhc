from app.utils.cursor_codec import decode_cursor, encode_cursor


def test_cursor_codec_roundtrip__dict__payload():
    payload = {
        "id": 123,
        "created_at": "2026-02-18T00:00:00",
        "ticket_id": 999,
    }
    s = encode_cursor(payload)
    out = decode_cursor(s)
    # codec добавляет версию; полезная нагрузка должна сохраняться
    for k, v in payload.items():
        assert out.get(k) == v
    assert out.get("v") == 1

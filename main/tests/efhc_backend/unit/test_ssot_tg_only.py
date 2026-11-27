import json
from pathlib import Path


def test_public_layer_forbids_tg_id():
    snapshot = json.loads(
        (Path(__file__).resolve().parents[3] / "backend/openapi/openapi.json")
        .read_text(encoding="utf-8")
    )
    paths = snapshot["paths"]
    schemas = snapshot["components"]["schemas"]
    assert paths and schemas
    forbidden = {"tg_id", "user_id"}
    for path, operations in paths.items():
        assert not any("{" + field + "}" in path for field in forbidden), path
        for method, operation in operations.items():
            if not isinstance(operation, dict):
                continue
            parameters = {p.get("name") for p in operation.get("parameters", [])}
            assert not (parameters & forbidden), (path, method, parameters)
    for name, schema in schemas.items():
        assert not (set(schema.get("properties", {})) & forbidden), name

    assert "/profile/history" in paths
    assert "/admin/users/{global_id}" in paths

from app.integrations.ton_memo import (
    MemoBuyEFHCPack,
    MemoBuyEFHCPackGlobal,
    MemoDepositEFHC,
    MemoDepositEFHCGlobal,
    MemoSkuNFT,
    MemoSkuNFTGlobal,
    build_buy_pack_global_memo,
    build_buy_pack_memo,
    build_deposit_global_memo,
    build_deposit_memo,
    parse_memo,
    parse_memo_for_watcher,
)


def test_deposit_memo_проходит_roundtrip_через_watcher_adapter() -> None:
    memo = build_deposit_memo(123456789)

    parsed = parse_memo(memo)
    kind, params = parse_memo_for_watcher(memo)

    assert memo == "EFHC:123456789"
    assert isinstance(parsed, MemoDepositEFHC)
    assert parsed.tg_id == 123456789
    assert parsed.legacy is False
    assert kind == "simple_efhc"
    assert params == {"tg_id": 123456789}


def test_legacy_direct_deposit_без_colon_разбирается() -> None:
    parsed = parse_memo("EFHC123456789")
    kind, params = parse_memo_for_watcher("EFHC123456789")

    assert isinstance(parsed, MemoDepositEFHC)
    assert parsed.tg_id == 123456789
    assert parsed.legacy is True
    assert kind == "simple_efhc"
    assert params == {"tg_id": 123456789}


def test_buy_pack_memo_проходит_roundtrip_через_builder() -> None:
    memo = build_buy_pack_memo(123456789, 250, "ORD-123")
    parsed = parse_memo(memo)
    kind, params = parse_memo_for_watcher(memo)

    assert isinstance(parsed, MemoBuyEFHCPack)
    assert parsed.tg_id == 123456789
    assert parsed.qty_efhc == 250
    assert parsed.order_id == "ORD-123"
    assert parsed.legacy is False
    assert kind == "sku_efhc"
    assert params == {"tg_id": 123456789, "qty": 250}


def test_legacy_sku_форматы_поддерживаются_watcher() -> None:
    parsed = parse_memo("SKU:EFHC|Q:100|TG:123456789")
    nft = parse_memo("SKU:NFT_VIP|Q:1|TG:123456789")

    assert isinstance(parsed, MemoBuyEFHCPack)
    assert parsed.legacy is True
    assert parse_memo_for_watcher("SKU:EFHC|Q:100|TG:123456789") == (
        "sku_efhc",
        {"tg_id": 123456789, "qty": 100},
    )
    assert isinstance(nft, MemoSkuNFT)
    assert parse_memo_for_watcher("SKU:NFT_VIP|Q:1|TG:123456789") == (
        "sku_nft",
        {"tg_id": 123456789, "qty": 1},
    )


def test_global_deposit_memo_содержит_ровно_десять_ascii_цифр() -> None:
    memo = build_deposit_global_memo("0123456789")
    parsed = parse_memo(memo)

    assert memo == "EFHC:GID:0123456789"
    assert isinstance(parsed, MemoDepositEFHCGlobal)
    assert parsed.global_id == "0123456789"
    assert parse_memo_for_watcher(memo) == (
        "simple_efhc",
        {"global_id": "0123456789"},
    )


def test_global_pack_и_nft_memo_provider_neutral() -> None:
    pack = build_buy_pack_global_memo("0123456789", 250, "ORD-123")
    parsed_pack = parse_memo(pack)
    parsed_nft = parse_memo("SKU:NFT_VIP|Q:1|GID:0123456789")

    assert isinstance(parsed_pack, MemoBuyEFHCPackGlobal)
    assert parsed_pack.global_id == "0123456789"
    assert parsed_pack.qty_efhc == 250
    assert parsed_pack.order_id == "ORD-123"
    assert isinstance(parsed_nft, MemoSkuNFTGlobal)
    assert parsed_nft.global_id == "0123456789"
    assert parse_memo_for_watcher(pack) == (
        "sku_efhc",
        {"global_id": "0123456789", "qty": 250},
    )


def test_global_id_memo_отклоняет_zero_unicode_bool_и_wrong_width() -> None:
    for bad in ("0000000000", "１２３４５６７８９０", "123", "12345678901"):
        assert parse_memo(f"EFHC:GID:{bad}") is None

    for bad in (True, "0000000000", "１２３４５６７８９０"):
        try:
            build_deposit_global_memo(bad)  # type: ignore[arg-type]
        except ValueError:
            pass
        else:
            raise AssertionError(f"global_id must be rejected: {bad!r}")

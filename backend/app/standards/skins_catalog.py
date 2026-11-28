"""backend/app/standards/skins_catalog.py

SSOT каталог скинов (картинок) для главной страницы.

Канон:
- Файлы картинок лежат в frontend/public/skins/<id>.webp
- Каталог строится автоматически по факту наличия файлов.
  Никаких ручных списков/констант MAX_SKIN_ID.
- Публичное имя: skins / skin_id.
- Денежная логика: покупка списывает EFHC по правилу
  «сначала bonus, затем main» (реализовано в сервисе skins).

Важно:
- Каталог читается с файловой системы при каждом вызове build_catalog().
  Это позволяет "докидывать" файлы без перезапуска логики.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkinCatalogItem:
    skin_id: int
    title: str
    price_efhc: str  # Decimal as string
    asset_path: str


def _skins_dir() -> Path:
    # Каноничный путь в монорепозитории.
    # В проде может быть смонтирован иначе — тогда задайте SKINS_DIR.
    import os

    raw = (os.getenv("SKINS_DIR") or "").strip()
    if raw:
        return Path(raw)

    # repo_root/backend/app/standards -> repo_root/frontend/public/skins
    here = Path(__file__).resolve()
    repo_root = here.parents[3]
    return repo_root / "frontend" / "public" / "skins"


def _iter_skin_ids_from_dir(dir_path: Path) -> Iterable[int]:
    if not dir_path.exists() or not dir_path.is_dir():
        return []

    ids: list[int] = []
    for p in dir_path.iterdir():
        if not p.is_file():
            continue
        # Skip empty/broken files (zero bytes)
        # to avoid dead catalog entries.
        st = None
        try:
            st = p.stat()
        except OSError:
            st = None
        if st is None:
            continue
        if st.st_size <= 0:
            continue
        name = p.name
        # only <n>.webp
        if not name.lower().endswith(".webp"):
            continue
        stem = name[:-5]
        if not stem.isdigit():
            continue
        sid = int(stem)
        if sid >= 1:
            ids.append(sid)

    return sorted(set(ids))


def price_for_skin_id(skin_id: int) -> str:
    # SSOT-формула по умолчанию:
    # 1: 0 (базовый бесплатный), 2..: 100 * id EFHC
    if int(skin_id) <= 1:
        return "0"
    return str(100 * int(skin_id))


def build_catalog() -> list[SkinCatalogItem]:
    dir_path = _skins_dir()
    ids = list(_iter_skin_ids_from_dir(dir_path))

    # Канон: skin_id=1 считается базовым.
    # Если файла нет — всё равно оставляем позицию, чтобы UI не ломался.
    if 1 not in ids:
        ids = [1] + ids

    items: list[SkinCatalogItem] = []
    for sid in ids:
        items.append(
            SkinCatalogItem(
                skin_id=int(sid),
                title=f"Skin #{int(sid)}",
                price_efhc=price_for_skin_id(int(sid)),
                asset_path=f"/skins/{int(sid)}.webp",
            )
        )
    return items

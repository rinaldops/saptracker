"""Algoritmo independente da API COM para capturar GuiTableControl paginado."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any


def capture_table_pages(
    read_page: Callable[[int], Iterable[dict[str, Any]]],
    *,
    row_count: int,
    visible_row_count: int,
    maximum: int | None = None,
    set_position: Callable[[int], None] | None = None,
    row_key: Callable[[dict[str, Any]], Any] | None = None,
    page_counts: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Captura p√°ginas completas e acumula a quantidade de cada p√°gina."""
    if row_count <= 0:
        return []
    step = max(1, visible_row_count)
    last = max(0, maximum if maximum is not None else row_count - 1)
    rows: list[dict[str, Any]] = []
    keys: list[Any] = []
    position = 0
    seen_positions: set[int] = set()

    while position <= last and len(rows) < row_count:
        if position in seen_positions:
            break
        seen_positions.add(position)
        if set_position is not None:
            set_position(position)
        page = list(read_page(position))
        if page_counts is not None:
            page_counts.append(len(page))
        if not page:
            break
        for candidate in page:
            key = row_key(candidate) if row_key else tuple(sorted(candidate.items()))
            # O ˙ltimo deslocamento do SAP pode sobrepor a viewport anterior.
            # N„o conte a mesma linha duas vezes, mas mantenha page_counts com
            # a quantidade fÌsica lida para diagnÛstico.
            if key in keys:
                continue
            rows.append(candidate)
            keys.append(key)
        next_position = min(last, position + step)
        if next_position == position:
            break
        position = next_position

    return rows[:row_count]

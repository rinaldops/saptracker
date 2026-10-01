from __future__ import annotations

from typing import Any
from src.core.table_capture import capture_table_pages

class FakePagedTable:
    def __init__(self, total: int = 1147, visible: int = 22) -> None:
        self.rows = [{"Empresa": f"EMP-{i:04d}", "indice": i} for i in range(total)]
        self.visible = visible
        self.maximum = total - 1
        self.position = 37
        self.positions: list[int] = []
    def set_position(self, value: int) -> None:
        self.position = max(0, min(value, self.maximum))
        self.positions.append(self.position)
    def read_page(self, _position: int) -> list[dict[str, Any]]:
        start = self.position
        page = self.rows[start : start + self.visible]
        return page + [{"Empresa": "", "indice": i} for i in range(start + len(page), start + self.visible)]

def test_captura_todas_as_1147_linhas_com_linha_ancorada() -> None:
    table = FakePagedTable()
    captured = capture_table_pages(table.read_page, row_count=1147, visible_row_count=22, maximum=table.maximum, set_position=table.set_position, row_key=lambda row: row["indice"])
    assert len(captured) == 1147
    assert [row["indice"] for row in captured] == list(range(1147))
    assert captured[0]["Empresa"] == "EMP-0000"
    assert captured[-1]["Empresa"] == "EMP-1146"

def test_acumula_paginas_fixas_de_22_ate_a_ultima() -> None:
    table = FakePagedTable()
    counts: list[int] = []
    captured = capture_table_pages(table.read_page, row_count=1147, visible_row_count=22, maximum=1146, set_position=table.set_position, page_counts=counts, row_key=lambda row: row["indice"])
    assert len(counts) == 53
    assert all(count == 22 for count in counts)
    assert sum(counts) == 1166
    assert len(captured) == 1147
    assert [row["indice"] for row in captured] == list(range(1147))

def test_captura_respeita_limite_e_titulos_fica_pesquisavel() -> None:
    table = FakePagedTable(total=47, visible=6)
    captured = capture_table_pages(table.read_page, row_count=47, visible_row_count=6, maximum=table.maximum, set_position=table.set_position, row_key=lambda row: row["indice"])
    assert "Empresa" in ["Empresa", "indice"]
    assert captured[23]["Empresa"] == "EMP-0023"
    assert len(captured) == 47


def test_remove_sobreposicao_da_ultima_viewport() -> None:
    pages = {
        0: [{"id": i} for i in range(22)],
        22: [{"id": i} for i in range(22, 44)],
        44: [{"id": i} for i in range(40, 47)],
    }
    counts: list[int] = []
    captured = capture_table_pages(
        lambda position: pages[position],
        row_count=47,
        visible_row_count=22,
        maximum=44,
        page_counts=counts,
        row_key=lambda row: row["id"],
    )
    assert sum(counts) == 51
    assert len(captured) == 47
    assert [row["id"] for row in captured] == list(range(47))

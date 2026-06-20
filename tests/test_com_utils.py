"""Testes dos helpers de coleção COM (``com_len`` / ``com_item``).

Cobrem a diferença real do SAP GUI: ``GuiComponentCollection`` usa ``Count`` e
``GuiCollection`` (retornada por ``GetAllNodeKeys`` etc.) usa ``Length``.
"""

from __future__ import annotations

from typing import Any

from src.core.com_utils import com_item, com_len


class ColCount:
    """Coleção estilo ``GuiComponentCollection`` (``Count`` + ``ElementAt``)."""

    def __init__(self, items: list[Any]) -> None:
        self._items = list(items)
        self.Count = len(self._items)

    def ElementAt(self, i: int) -> Any:
        return self._items[i]


class ColLength:
    """Coleção estilo ``GuiCollection`` (``Length`` + ``ElementAt``)."""

    def __init__(self, items: list[Any]) -> None:
        self._items = list(items)
        self.Length = len(self._items)

    def ElementAt(self, i: int) -> Any:
        return self._items[i]


class ColItem:
    """Coleção que só expõe ``Length`` e ``Item`` (sem ``ElementAt``)."""

    def __init__(self, items: list[Any]) -> None:
        self._items = list(items)
        self.Length = len(self._items)

    def Item(self, i: int) -> Any:
        return self._items[i]


def test_com_len_conta_via_count_e_length() -> None:
    assert com_len(ColCount(["a", "b"])) == 2
    assert com_len(ColLength(["a", "b", "c"])) == 3
    assert com_len(None) == 0
    assert com_len(object()) == 0  # nenhum dos atributos
    assert com_len(("A", "B")) == 2  # SAFEARRAY convertido pelo pywin32


def test_com_item_via_elementat_e_item() -> None:
    assert com_item(ColCount(["x", "y"]), 1) == "y"
    assert com_item(ColLength(["x", "y"]), 0) == "x"
    assert com_item(ColItem(["p", "q"]), 1) == "q"  # fallback para Item
    assert com_item(("A", "B"), 1) == "B"


def test_com_item_default_quando_indisponivel() -> None:
    assert com_item(None, 0, default="def") == "def"

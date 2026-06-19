"""Testes do Analyser: percurso da árvore, serialização, inspeção e highlight.

Usa *fakes* COM (sem pywin32/SAP). ``FakeColl`` imita uma
``GuiComponentCollection`` (``Count`` + ``ElementAt``).
"""

from __future__ import annotations

from typing import Any

from src.core.analyser import Analyser, ObjectNode
from tests.conftest import FakeComponent


class FakeColl:
    """``GuiComponentCollection`` falsa."""

    def __init__(self, items: list[Any]) -> None:
        self._items = list(items)
        self.Count = len(self._items)

    def ElementAt(self, i: int) -> Any:
        return self._items[i]


class FakeTextEditObj:
    """``GuiTextEdit`` mínimo para exercitar a inspeção delegada."""

    Type = "GuiTextEdit"
    Id = "wnd[0]/usr/edit"
    Name = "EDIT"
    Text = ""
    NumberOfLines = 1

    def GetLineText(self, i: int) -> str:
        return "conteudo"

    def Visualize(self, on: bool) -> bool:
        return True


# --------------------------------------------------------------------------- #
# build_tree / ObjectNode
# --------------------------------------------------------------------------- #
def _session_com_arvore() -> Any:
    grid = FakeComponent(
        Id="wnd[0]/usr/cntlGRID1/shellcont/shell",
        Type="GuiGridView",
        Name="GRID1",
        Text="Resultado",
        Top=50,
        Left=0,
        Width=800,
        Height=400,
    )
    janela = FakeComponent(
        Id="wnd[0]", Type="GuiFrameWindow", Name="wnd[0]", Children=FakeColl([grid])
    )
    return FakeComponent(
        Id="ses[0]", Type="GuiSession", Name="ses", Children=FakeColl([janela])
    )


def test_build_tree_estrutura_e_posicao() -> None:
    analyser = Analyser(_session_com_arvore())
    root = analyser.build_tree()

    assert root.type == "GuiSession"
    assert len(root.children) == 1
    janela = root.children[0]
    assert janela.id == "wnd[0]"
    grid = janela.children[0]
    assert grid.type == "GuiGridView"
    assert (grid.top, grid.left, grid.width, grid.height) == (50, 0, 800, 400)
    assert grid.is_shell is True
    assert grid.shell_supported is True


def test_flatten_e_to_dict() -> None:
    root = Analyser(_session_com_arvore()).build_tree()
    nos = root.flatten()
    assert [n.type for n in nos] == ["GuiSession", "GuiFrameWindow", "GuiGridView"]

    d = root.to_dict()
    assert d["type"] == "GuiSession"
    assert d["children"][0]["children"][0]["type"] == "GuiGridView"


def test_node_from_obj_guishell_usa_subtype() -> None:
    analyser = Analyser(object())
    shell = FakeComponent(Id="wnd[0]/usr/pic", Type="GuiShell", SubType="GuiPicture")
    node = analyser._node_from_obj(shell)
    assert node.type == "GuiPicture"  # SubType vira o tipo efetivo
    assert node.is_shell is True
    assert node.shell_supported is False  # sem handler dedicado


def test_build_tree_tolera_session_vazia() -> None:
    vazia = FakeComponent(Id="ses[0]", Type="GuiSession")  # sem Children
    root = Analyser(vazia).build_tree()
    assert root.children == []


def test_object_node_defaults() -> None:
    node = ObjectNode(id="x", type="GuiLabel")
    assert node.children == []
    assert node.to_dict()["is_shell"] is False


# --------------------------------------------------------------------------- #
# inspect / find_by_id
# --------------------------------------------------------------------------- #
class FakeSessionFind:
    """Sessão falsa cujo ``FindById`` resolve um mapa de IDs.

    Imita ``FindById(id, False)`` do SAP GUI: retorna ``None`` em vez de lançar
    quando o objeto não existe.
    """

    def __init__(self, mapping: dict[str, Any]) -> None:
        self._m = mapping

    def FindById(self, oid: str, *args: Any) -> Any:
        return self._m.get(oid)


def test_inspect_delega_ao_handler() -> None:
    ed = FakeTextEditObj()
    analyser = Analyser(FakeSessionFind({ed.Id: ed}))
    details = analyser.inspect(ed.Id)
    assert details["type"] == "GuiTextEdit"
    assert details["shell"]["tipo"] == "GuiTextEdit"
    assert details["shell"]["conteudo"] == "conteudo"


def test_inspect_objeto_inexistente() -> None:
    analyser = Analyser(FakeSessionFind({}))
    assert "erro" in analyser.inspect("wnd[0]/usr/nope")


def test_find_by_id_retorna_none_quando_ausente() -> None:
    analyser = Analyser(FakeSessionFind({}))
    assert analyser.find_by_id("x") is None


# --------------------------------------------------------------------------- #
# highlight
# --------------------------------------------------------------------------- #
def test_highlight_sucesso() -> None:
    ed = FakeTextEditObj()
    analyser = Analyser(FakeSessionFind({ed.Id: ed}))
    assert analyser.highlight(ed.Id) is True


def test_highlight_objeto_inexistente() -> None:
    analyser = Analyser(FakeSessionFind({}))
    assert analyser.highlight("x") is False

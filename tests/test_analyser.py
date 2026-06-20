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


class FakeGridObj:
    """``GuiGridView`` introspectável, usado como folha de uma árvore."""

    Id = "wnd[0]/usr/cntlGRID1/shellcont/shell"
    Name = "GRID1"
    Text = "Resultado"

    def __init__(self, type_: str = "GuiGridView", subtype: str = "") -> None:
        self.Type = type_
        if subtype:
            self.SubType = subtype
        self._cols = ["MATNR", "MENGE"]
        self._rows = [{"MATNR": "MAT001", "MENGE": "10"}, {"MATNR": "MAT002", "MENGE": "5"}]
        self.RowCount = len(self._rows)
        self.CurrentCellRow = -1
        self.CurrentCellColumn = ""
        self.SelectedRows = ""
        self.FirstVisibleRow = 0

    def GetColumnOrder(self) -> FakeColl:
        return FakeColl(self._cols)

    def GetCellValue(self, r: int, col: str) -> str:
        return self._rows[r].get(col, "")


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


def test_build_tree_reporta_progresso() -> None:
    progresso: list[tuple[int, int]] = []
    Analyser(_session_com_arvore()).build_tree(
        lambda atual, total: progresso.append((atual, total))
    )
    assert progresso[0] == (0, 3)
    assert progresso[-1] == (3, 3)
    assert [atual for atual, _ in progresso] == sorted(atual for atual, _ in progresso)


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


# --------------------------------------------------------------------------- #
# Conteúdo interno de GuiShell listado na árvore (requisito-diferencial)
# --------------------------------------------------------------------------- #
def _session_com_grid(grid: Any) -> Any:
    janela = FakeComponent(Id="wnd[0]", Type="GuiFrameWindow", Children=FakeColl([grid]))
    return FakeComponent(Id="ses[0]", Type="GuiSession", Children=FakeColl([janela]))


def test_arvore_lista_conteudo_do_grid() -> None:
    grid = FakeGridObj()
    root = Analyser(_session_com_grid(grid)).build_tree()
    grid_node = root.children[0].children[0]
    assert grid_node.type == "GuiGridView"
    # O conteúdo interno (colunas e linhas) vira filho do nó do shell.
    tipos = {c.type for c in grid_node.children}
    assert tipos == {"GuiGridColumns", "GuiGridRows"}

    colunas = next(c for c in grid_node.children if c.type == "GuiGridColumns")
    assert [c.text for c in colunas.children] == ["MATNR", "MENGE"]

    linhas = next(c for c in grid_node.children if c.type == "GuiGridRows")
    assert linhas.children[0].text == "[0] MAT001 | 10"
    # Nós sintéticos herdam o id do shell (selecionar mostra detalhes do controle).
    assert colunas.children[0].id == grid.Id


def test_arvore_resolve_grid_reportado_como_guishell() -> None:
    # Controle que reporta Type genérico "GuiShell" e tipo real em SubType.
    grid = FakeGridObj(type_="GuiShell", subtype="GuiGridView")
    root = Analyser(_session_com_grid(grid)).build_tree()
    grid_node = root.children[0].children[0]
    assert grid_node.type == "GuiGridView"
    assert grid_node.shell_supported is True
    assert any(c.type == "GuiGridColumns" for c in grid_node.children)


def test_shell_content_nodes_tree_reconstroi_hierarquia() -> None:
    analyser = Analyser(object())
    data = {
        "nos": [
            {"chave": "r", "texto": "Raiz", "filhos": ["a", "b"]},
            {"chave": "a", "texto": "A", "filhos": []},
            {"chave": "b", "texto": "B", "filhos": []},
        ]
    }
    roots = analyser._shell_content_nodes("GuiTree", data, "shellid")
    assert len(roots) == 1  # só a raiz no topo
    raiz = roots[0]
    assert raiz.text == "r: Raiz"
    assert [c.name for c in raiz.children] == ["a", "b"]


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

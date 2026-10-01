"""Testes do Analyser: percurso da árvore, serialização, inspeção e highlight.

Usa *fakes* COM (sem pywin32/SAP). ``FakeColl`` imita uma
``GuiComponentCollection`` (``Count`` + ``ElementAt``).
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core import analyser as analyser_module
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




class FakeTableCell:
    def __init__(self, cell_id: str, text: str = "", selected: bool = False) -> None:
        self.Id = cell_id
        self.Type = "GuiCheckBox" if "/chk" in cell_id else "GuiTextField"
        self.Text = text
        self.Selected = selected


class FakeTableObj:
    Type = "GuiTableControl"
    Id = "/app/con[0]/ses[0]/wnd[0]/usr/tblT"

    def __init__(self) -> None:
        prefix = self.Id + "/"
        cells = [
            FakeTableCell(prefix + "txtTI_REGRAS-BUKRS[0,0]", "1000"),
            FakeTableCell(prefix + "txtTI_REGRAS-COD[1,0]", "ABC"),
        ]
        self.Children = FakeColl(cells)


def test_arvore_lista_conteudo_do_table_control_e_valores_pesquisaveis() -> None:
    root = Analyser(_session_com_grid(FakeTableObj())).build_tree()
    table_node = root.children[0].children[0]

    assert table_node.type == "GuiTableControl"
    assert table_node.shell_supported is True
    flattened = table_node.flatten()
    assert any(n.text == "TI_REGRAS-BUKRS" for n in flattened)
    assert any("1000" in n.text for n in flattened)

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


def test_arvore_table_control_lista_colunas_e_celulas_reais() -> None:
    analyser = Analyser(object())
    cell_id = "/app/con[0]/ses[0]/wnd[0]/usr/tblT/txtTI_REGRAS-BUKRS[0,0]"
    data = {
        "colunas": ["TI_REGRAS-BUKRS"],
        "titulos": ["Empresa"],
        "celulas": [{"id": cell_id, "tipo": "GuiTextField", "coluna": 0,
                     "linha": 0, "nome": "TI_REGRAS-BUKRS", "texto": "1000"}],
    }
    nodes = analyser._table_nodes(data, "table")
    columns = next(node for node in nodes if node.type == "GuiTableColumns")
    cells = next(node for node in nodes if node.type == "GuiTableCells")

    assert columns.children[0].text == "Empresa (TI_REGRAS-BUKRS)"
    assert [node.type for node in cells.children] == ["GuiTextField"]
    assert cells.children[0].id == cell_id
    assert "1000" in cells.children[0].text
    assert not any(node.type in {"GuiTableRows", "GuiTableRow"} for node in nodes + cells.children)

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
    # name = índice da linha (usado por select_row); "1" na segunda linha.
    assert [c.name for c in linhas.children] == ["0", "1"]
    # Nós sintéticos herdam o id do shell (selecionar mostra detalhes do controle).
    assert colunas.children[0].id == grid.Id


def test_grid_nodes_sinaliza_colunas_incompletas() -> None:
    # Grid cuja API de Scripting não expõe todas as colunas (ver
    # GuiGridViewHandler.inspecionar): sem o aviso, os dados ausentes ficam
    # invisíveis na árvore/busca, como se o grid só tivesse 1 coluna.
    analyser = Analyser(object())
    data = {
        "colunas": ["AUFNR"],
        "total_colunas": 10,
        "colunas_completas": False,
        "linhas": [{"AUFNR": "4000001"}],
        "total": 1,
    }
    nodes = analyser._grid_nodes(data, "shellid")
    colunas_node = next(n for n in nodes if n.type == "GuiGridColumns")
    avisos = [c for c in colunas_node.children if c.type == "GuiGridColumnsAviso"]
    assert len(avisos) == 1
    assert "1 de 10" in avisos[0].text


def test_grid_nodes_sem_aviso_quando_colunas_completas() -> None:
    analyser = Analyser(object())
    data = {
        "colunas": ["MATNR", "MENGE"],
        "total_colunas": 2,
        "colunas_completas": True,
        "linhas": [],
        "total": 0,
    }
    nodes = analyser._grid_nodes(data, "shellid")
    colunas_node = next(n for n in nodes if n.type == "GuiGridColumns")
    assert all(c.type != "GuiGridColumnsAviso" for c in colunas_node.children)


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


def test_shell_content_nodes_tree_inclui_colunas_ocultas_no_rotulo() -> None:
    # Em árvores de projeto SAP PS, o código real (rede/atividade/elemento de
    # tarefa) fica numa coluna oculta (ex.: TECH_KEY), não no texto visível —
    # sem incluí-lo no rótulo, o código não aparece em nenhum campo
    # pesquisável (nem na árvore da UI, nem no snapshot da CLI).
    analyser = Analyser(object())
    data = {
        "nos": [
            {
                "chave": "000013",
                "texto": "Ferragem",
                "filhos": [],
                "colunas": {"          1": "Ferragem", "TECH_KEY": "4000028 0030 0080"},
            },
        ]
    }
    roots = analyser._shell_content_nodes("GuiTree", data, "shellid")
    assert roots[0].text == "000013: Ferragem | Ferragem | 4000028 0030 0080"


def test_shell_content_nodes_tree_sem_texto_usa_so_colunas() -> None:
    analyser = Analyser(object())
    data = {"nos": [{"chave": "c1", "texto": "", "filhos": [], "colunas": {"X": "valor"}}]}
    roots = analyser._shell_content_nodes("GuiTree", data, "shellid")
    assert roots[0].text == "c1: valor"


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


# --------------------------------------------------------------------------- #
# select_node
# --------------------------------------------------------------------------- #
class FakeSelectedNodes:
    """``GetSelectedNodes()`` falso: coleção COM com uma única chave."""

    def __init__(self, keys: list[str]) -> None:
        self._keys = keys
        self.Count = len(keys)

    def ElementAt(self, i: int) -> str:
        return self._keys[i]


class FakeTreeObj:
    """``GuiTree`` falso: ``SelectNode`` muda o que ``GetSelectedNodes`` devolve.

    Chaves fora de ``valid_keys`` são ignoradas (simula o SAP recusando uma
    chave inexistente sem levantar erro).
    """

    Id = "wnd[0]/usr/cntlTREE1/shellcont/shell"

    def __init__(self, valid_keys: frozenset[str] = frozenset({"000013"})) -> None:
        self._valid_keys = valid_keys
        self._selected: list[str] = []

    def SelectNode(self, key: str) -> None:
        if key in self._valid_keys:
            self._selected = [key]

    def GetSelectedNodes(self) -> FakeSelectedNodes:
        return FakeSelectedNodes(self._selected)


def test_select_node_sucesso() -> None:
    tree = FakeTreeObj()
    analyser = Analyser(FakeSessionFind({tree.Id: tree}))
    assert analyser.select_node(tree.Id, "000013") is True


def test_select_node_objeto_inexistente() -> None:
    analyser = Analyser(FakeSessionFind({}))
    assert analyser.select_node("x", "000013") is False


def test_select_node_nao_confirma_chave_inexistente() -> None:
    # Chave pedida não está entre as válidas do tree falso: SelectNode não
    # tem efeito e a confirmação via GetSelectedNodes falha.
    tree = FakeTreeObj(valid_keys=frozenset({"000099"}))
    analyser = Analyser(FakeSessionFind({tree.Id: tree}))
    assert analyser.select_node(tree.Id, "000013") is False


# --------------------------------------------------------------------------- #
# select_row
# --------------------------------------------------------------------------- #
class FakeGridSelectable:
    """``GuiGridView`` falso: ``SetCurrentCell`` muda ``CurrentCellRow``.

    ``row_count`` simula uma grade com poucas linhas: ``SetCurrentCell`` fora
    do intervalo não tem efeito (imita o SAP recusando uma linha inexistente).
    """

    Id = "wnd[0]/usr/cntlGRID1/shellcont/shell"

    def __init__(self, row_count: int = 5) -> None:
        self._row_count = row_count
        self.CurrentCellRow = -1
        self.SelectedRows = ""

    def SetCurrentCell(self, row: int, _column: str) -> None:
        if 0 <= row < self._row_count:
            self.CurrentCellRow = row


def test_select_row_sucesso() -> None:
    grid = FakeGridSelectable()
    analyser = Analyser(FakeSessionFind({grid.Id: grid}))
    assert analyser.select_row(grid.Id, 2) is True
    assert grid.SelectedRows == "2"


def test_select_row_objeto_inexistente() -> None:
    analyser = Analyser(FakeSessionFind({}))
    assert analyser.select_row("x", 2) is False


def test_select_row_nao_confirma_linha_fora_do_intervalo() -> None:
    grid = FakeGridSelectable(row_count=5)
    analyser = Analyser(FakeSessionFind({grid.Id: grid}))
    assert analyser.select_row(grid.Id, 99) is False


# --------------------------------------------------------------------------- #
# copy_grid_table
# --------------------------------------------------------------------------- #
class FakeGridCopiavel:
    """``GuiGridView`` falso: ``SelectContextMenuItemByPosition`` é o que
    efetivamente "copia" (deposita o texto simulado no clipboard falso).

    ``row_count``/``visible_row_count`` > 0 simulam paginação real (ver
    :func:`ensure_grid_rows_loaded`), registrando as chamadas de
    ``FirstVisibleRow`` em ``chamadas`` junto com as demais.
    """

    Id = "wnd[0]/usr/cntlGRID1/shellcont/shell"

    def __init__(
        self,
        texto_copiado: str,
        clipboard: dict[str, str | None],
        *,
        row_count: int = 0,
        visible_row_count: int = 0,
    ) -> None:
        self.chamadas: list[str] = []
        self._texto = texto_copiado
        self._clipboard = clipboard
        self.RowCount = row_count
        self.VisibleRowCount = visible_row_count
        self._first_visible_row = 0

    @property
    def FirstVisibleRow(self) -> int:
        return self._first_visible_row

    @FirstVisibleRow.setter
    def FirstVisibleRow(self, valor: int) -> None:
        self._first_visible_row = valor
        self.chamadas.append(f"FirstVisibleRow({valor})")

    def SelectAll(self) -> None:
        self.chamadas.append("SelectAll")

    def ContextMenu(self) -> None:
        self.chamadas.append("ContextMenu")

    def SelectContextMenuItemByPosition(self, pos: str) -> None:
        self.chamadas.append(f"SelectContextMenuItemByPosition({pos})")
        self._clipboard["texto"] = self._texto


def _patch_clipboard(
    monkeypatch: pytest.MonkeyPatch, clipboard: dict[str, str | None]
) -> None:
    monkeypatch.setattr(analyser_module, "get_clipboard_text", lambda: clipboard["texto"])

    def fake_set(texto: str | None) -> None:
        clipboard["texto"] = texto

    monkeypatch.setattr(analyser_module, "set_clipboard_text", fake_set)


def test_copy_grid_table_sucesso(monkeypatch: pytest.MonkeyPatch) -> None:
    clipboard: dict[str, str | None] = {"texto": "conteúdo anterior do usuário"}
    _patch_clipboard(monkeypatch, clipboard)
    texto_copiado = "4000028\t0030\t0080\tFerragem\r\n4000028\t0030\t0090\tConcretagem\r\n"
    grid = FakeGridCopiavel(texto_copiado, clipboard)
    analyser = Analyser(FakeSessionFind({grid.Id: grid}))

    linhas = analyser.copy_grid_table(grid.Id)

    assert linhas == [
        ["4000028", "0030", "0080", "Ferragem"],
        ["4000028", "0030", "0090", "Concretagem"],
    ]
    assert grid.chamadas == [
        "SelectAll", "ContextMenu", "SelectContextMenuItemByPosition(0)",
    ]
    # Clipboard restaurado ao conteúdo anterior do usuário.
    assert clipboard["texto"] == "conteúdo anterior do usuário"


def test_copy_grid_table_carrega_todas_as_paginas_antes_de_copiar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Grid com mais linhas do que cabem na tela de uma vez (RowCount >
    # VisibleRowCount): sem forçar o carregamento de todas as páginas antes
    # de copiar, linhas além da primeira viriam vazias em grids grandes.
    clipboard: dict[str, str | None] = {"texto": None}
    _patch_clipboard(monkeypatch, clipboard)
    grid = FakeGridCopiavel("linha\r\n", clipboard, row_count=23, visible_row_count=5)
    analyser = Analyser(FakeSessionFind({grid.Id: grid}))

    analyser.copy_grid_table(grid.Id)

    # FirstVisibleRow foi percorrido (aquecimento) ANTES de SelectAll/copiar.
    indice_select_all = grid.chamadas.index("SelectAll")
    assert indice_select_all > 0
    assert all(c.startswith("FirstVisibleRow(") for c in grid.chamadas[:indice_select_all])
    ultima_pagina = grid.chamadas[indice_select_all - 1]
    ultimo_valor = int(ultima_pagina.removeprefix("FirstVisibleRow(").removesuffix(")"))
    assert ultimo_valor + grid.VisibleRowCount - 1 >= grid.RowCount - 1


def test_copy_grid_table_objeto_inexistente(monkeypatch: pytest.MonkeyPatch) -> None:
    clipboard: dict[str, str | None] = {"texto": None}
    _patch_clipboard(monkeypatch, clipboard)
    analyser = Analyser(FakeSessionFind({}))
    assert analyser.copy_grid_table("x") is None


def test_copy_grid_table_retorna_none_se_nada_copiado(monkeypatch: pytest.MonkeyPatch) -> None:
    clipboard: dict[str, str | None] = {"texto": None}
    _patch_clipboard(monkeypatch, clipboard)
    grid = FakeGridCopiavel("", clipboard)  # SelectContextMenuItemByPosition não muda nada
    analyser = Analyser(FakeSessionFind({grid.Id: grid}))
    assert analyser.copy_grid_table(grid.Id) is None


# --------------------------------------------------------------------------- #
# build_tree(full_grid_data=True) — recupera colunas incompletas na árvore/busca
# --------------------------------------------------------------------------- #
class FakeGridIncompletoRecuperavel:
    """``GuiGridView`` sem ``GetColumnOrder``/``GetColumnNames`` (colunas
    incompletas — cai no fallback de 1 coluna), mas com
    ``SelectAll``/``ContextMenu``/``SelectContextMenuItemByPosition``
    (recuperável via clipboard, como o grid real do Project Builder).
    """

    Id = "wnd[0]/usr/cntlGRID1/shellcont/shell"
    Type = "GuiGridView"

    def __init__(self, texto_copiado: str, clipboard: dict[str, str | None]) -> None:
        self.RowCount = 1
        self.ColumnCount = 4
        self.CurrentCellRow = -1
        self.CurrentCellColumn = "AUFNR"
        self.SelectedRows = ""
        self.FirstVisibleRow = 0
        self._texto = texto_copiado
        self._clipboard = clipboard

    def GetCellValue(self, r: int, col: str) -> str:
        return "4000028" if col == "AUFNR" else ""

    def SelectAll(self) -> None:
        pass

    def ContextMenu(self) -> None:
        pass

    def SelectContextMenuItemByPosition(self, pos: str) -> None:
        self._clipboard["texto"] = self._texto


def _avisos_de_colunas(grid_node: ObjectNode) -> list[ObjectNode]:
    return [
        c
        for grupo in grid_node.children
        if grupo.type == "GuiGridColumns"
        for c in grupo.children
        if c.type == "GuiGridColumnsAviso"
    ]


def test_build_tree_full_grid_data_recupera_colunas_incompletas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clipboard: dict[str, str | None] = {"texto": None}
    _patch_clipboard(monkeypatch, clipboard)
    grid = FakeGridIncompletoRecuperavel(
        "4000028\t0030\t0080\tFerragem\r\n", clipboard
    )
    root = Analyser(_session_com_grid(grid)).build_tree(full_grid_data=True)

    grid_node = root.children[0].children[0]
    assert _avisos_de_colunas(grid_node) == []
    linhas_node = next(c for c in grid_node.children if c.type == "GuiGridRows")
    assert "Ferragem" in linhas_node.children[0].text
    assert "0080" in linhas_node.children[0].text


def test_build_tree_sem_full_grid_data_mantem_aviso_e_nao_toca_clipboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Padrão (full_grid_data=False): usado pelo PollingRecorder a cada ~250ms
    # durante gravação ao vivo — não pode rolar a tela nem tocar o clipboard.
    clipboard: dict[str, str | None] = {"texto": None}
    _patch_clipboard(monkeypatch, clipboard)
    grid = FakeGridIncompletoRecuperavel(
        "4000028\t0030\t0080\tFerragem\r\n", clipboard
    )
    root = Analyser(_session_com_grid(grid)).build_tree()

    grid_node = root.children[0].children[0]
    assert len(_avisos_de_colunas(grid_node)) == 1
    assert clipboard["texto"] is None  # nada foi copiado

class FakeSelectableTable:
    Type = "GuiTableControl"
    Id = "table"
    VisibleRowCount = 22

    def __init__(self) -> None:
        self.VerticalScrollbar = type("Scrollbar", (), {"Position": 10})()
        self.rows = [type("TableRow", (), {"Selected": False})() for _ in range(40)]

    def GetAbsoluteRow(self, index: int) -> Any:
        return self.rows[index]


def test_select_table_column_usa_coluna_por_indice() -> None:
    from tests.test_shell_handlers import FakeCol

    table = FakeTableObj()
    table.Columns = FakeCol([type("Column", (), {"Selected": False})() for _ in range(3)])
    analyser = Analyser(FakeSessionFind({table.Id: table}))

    assert analyser.select_table_column(table.Id, 1) is True
    assert table.Columns.ElementAt(0).Selected is False
    assert table.Columns.ElementAt(1).Selected is True
    assert table.Columns.ElementAt(2).Selected is False


def test_build_tree_table_control_nao_pagina_com_full_grid_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = FakeTableObj()
    def nao_deve_ser_chamado(obj: Any) -> dict[str, Any]:
        raise AssertionError("GuiTableControl não deve ser paginado na análise")
    monkeypatch.setattr(
        "src.core.shell_handlers.table_control.GuiTableControlHandler.inspecionar_completo",
        nao_deve_ser_chamado,
    )

    root = Analyser(_session_com_grid(table)).build_tree(full_grid_data=True)
    assert any("1000" in node.text for node in root.flatten())

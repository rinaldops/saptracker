"""Testes de introspecção e geração de código dos handlers de GuiShell.

Os objetos COM do SAP são substituídos por *fakes* que expõem apenas os
métodos/propriedades lidos por cada handler. Cobrem ``inspecionar``,
``tirar_snapshot`` e ``gerar_codigo`` (seção 2.4 da spec), além do registry.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.shell_handlers import (
    GENERIC_HANDLER,
    HANDLERS,
    get_handler,
    get_handler_for_type,
    is_supported_shell,
    normalize_shell_type,
)
from src.core.shell_handlers.calendar import GuiCalendarHandler
from src.core.shell_handlers.generic import GuiShellGenerico
from src.core.shell_handlers.grid_view import GuiGridViewHandler
from src.core.shell_handlers.text_edit import GuiTextEditHandler
from src.core.shell_handlers.toolbar import GuiToolbarHandler
from src.core.shell_handlers.tree import GuiTreeHandler
from tests.conftest import FakeComponent


# --------------------------------------------------------------------------- #
# Fakes de objetos COM
# --------------------------------------------------------------------------- #
class FakeCol:
    """Coleção COM falsa com ``Count`` e ``ElementAt(i)``."""

    def __init__(self, items: list[Any]) -> None:
        self._items = list(items)
        self.Count = len(self._items)

    def ElementAt(self, i: int) -> Any:
        return self._items[i]


class FakeGrid:
    """``GuiGridView`` falso (ALV Grid)."""

    Type = "GuiGridView"
    Id = "wnd[0]/usr/cntlGRID1/shellcont/shell"
    Name = "GRID1"
    Text = "Resultado"

    def __init__(
        self,
        columns: list[str],
        rows: list[dict[str, str]],
        *,
        order: list[str] | None = None,
        current: tuple[int, str] = (-1, ""),
        selected: str = "",
        first: int = 0,
        column_count: int | None = None,
    ) -> None:
        self._order = columns if order is None else order
        self._names = columns
        self._rows = rows
        self.RowCount = len(rows)
        self.CurrentCellRow, self.CurrentCellColumn = current
        self.SelectedRows = selected
        self.FirstVisibleRow = first
        if column_count is not None:
            self.ColumnCount = column_count

    def GetColumnOrder(self) -> FakeCol:
        return FakeCol(self._order)

    def GetColumnNames(self) -> FakeCol:
        return FakeCol(self._names)

    def GetCellValue(self, r: int, col: str) -> str:
        return self._rows[r].get(col, "")

    def Visualize(self, on: bool) -> bool:  # usado pelo analyser
        return True


class FakeColLength:
    """Coleção estilo ``GuiCollection`` real do SAP: usa ``Length``, não ``Count``."""

    def __init__(self, items: list[Any]) -> None:
        self._items = list(items)
        self.Length = len(self._items)

    def ElementAt(self, i: int) -> Any:
        return self._items[i]


class FakeTree:
    """``GuiTree`` falso. Coleções usam ``Length`` (como o SAP real)."""

    Type = "GuiTree"

    def __init__(
        self,
        nodes: dict[str, dict[str, Any]],
        *,
        columns: list[str] | None = None,
        selected: list[str] | None = None,
    ) -> None:
        self._nodes = nodes
        self._columns = columns or []
        self._selected = selected or []

    def GetAllNodeKeys(self) -> FakeColLength:
        return FakeColLength(list(self._nodes))

    def GetColumnNames(self) -> FakeColLength:
        return FakeColLength(self._columns)

    def GetNodeTextByKey(self, key: str) -> str:
        return self._nodes[key].get("texto", "")

    def GetSubNodesCol(self, key: str) -> FakeColLength | None:
        filhos = self._nodes[key].get("filhos")
        return FakeColLength(filhos) if filhos else None

    def GetItemText(self, key: str, col: str) -> str:
        return self._nodes[key].get("cols", {}).get(col, "")

    def GetSelectedNodes(self) -> FakeColLength:
        return FakeColLength(self._selected)


class FakeTextEdit:
    """``GuiTextEdit`` falso."""

    Type = "GuiTextEdit"

    def __init__(
        self,
        lines: list[str],
        *,
        first: int = 0,
        current: int = 0,
        selected: str = "",
    ) -> None:
        self._lines = lines
        self.NumberOfLines = len(lines)
        self.FirstVisibleLine = first
        self.CurrentLine = current
        self.SelectedText = selected

    def GetLineText(self, i: int) -> str:
        return self._lines[i]


class FakeToolbar:
    """``GuiToolbarControl`` falso."""

    Type = "GuiToolbarControl"

    def __init__(self, buttons: list[dict[str, Any]]) -> None:
        self._b = buttons
        self.ButtonCount = len(buttons)

    def GetButtonId(self, i: int) -> str:
        return self._b[i]["id"]

    def GetButtonTooltip(self, i: int) -> str:
        return self._b[i]["tooltip"]

    def GetButtonText(self, i: int) -> str:
        return self._b[i]["texto"]

    def GetButtonEnabled(self, i: int) -> bool:
        return self._b[i]["habilitado"]

    def GetButtonType(self, i: int) -> str:
        return self._b[i]["tipo"]


# --------------------------------------------------------------------------- #
# GuiGridView
# --------------------------------------------------------------------------- #
def test_grid_inspecionar_colunas_e_linhas() -> None:
    grid = FakeGrid(
        columns=["MATNR", "MENGE"],
        rows=[{"MATNR": "MAT001", "MENGE": "10"}, {"MATNR": "MAT002", "MENGE": "5"}],
        current=(1, "MENGE"),
        selected="0-1",
        first=0,
    )
    res = GuiGridViewHandler().inspecionar(grid)
    assert res["tipo"] == "GuiGridView"
    assert res["colunas"] == ["MATNR", "MENGE"]
    assert res["total"] == 2
    assert res["exibidas"] == 2
    assert res["linhas"][0]["MATNR"] == "MAT001"
    assert res["celula_atual"] == {"linha": 1, "coluna": "MENGE"}
    assert res["linhas_selecionadas"] == "0-1"


def test_grid_colunas_via_fallback_getcolumnnames() -> None:
    # GetColumnOrder vazio força o uso de GetColumnNames.
    grid = FakeGrid(columns=["A", "B"], rows=[], order=[])
    assert GuiGridViewHandler()._column_names(grid) == ["A", "B"]


def test_grid_colunas_via_safearray_python() -> None:
    grid = FakeGrid(columns=["PSPID", "POST1"], rows=[{"PSPID": "P-1", "POST1": "Projeto"}])
    grid.GetColumnOrder = lambda: ("PSPID", "POST1")  # type: ignore[method-assign]
    resultado = GuiGridViewHandler().inspecionar(grid)
    assert resultado["colunas"] == ["PSPID", "POST1"]
    assert resultado["linhas"] == [{"PSPID": "P-1", "POST1": "Projeto"}]


def test_grid_usa_coluna_atual_quando_colecoes_indisponiveis() -> None:
    grid = FakeGrid(columns=["PSPID"], rows=[{"PSPID": "P-1"}], current=(-1, "PSPID"))
    grid.GetColumnOrder = lambda: None  # type: ignore[method-assign]
    grid.GetColumnNames = lambda: None  # type: ignore[method-assign]
    resultado = GuiGridViewHandler().inspecionar(grid)
    assert resultado["colunas"] == ["PSPID"]
    assert resultado["linhas"] == [{"PSPID": "P-1"}]


def test_grid_sinaliza_colunas_incompletas_quando_api_de_colunas_indisponivel() -> None:
    # Reproduz um grid ALV real (ex.: worklist do Project Builder) cuja API de
    # Scripting não implementa GetColumnOrder/GetColumnNames: cai no fallback
    # de 1 coluna (a atual), mas ColumnCount revela que há mais — sem
    # sinalizar isso, os outros campos somem do snapshot/busca em silêncio.
    grid = FakeGrid(
        columns=["AUFNR"], rows=[{"AUFNR": "4000001"}],
        current=(-1, "AUFNR"), column_count=10,
    )
    grid.GetColumnOrder = lambda: None  # type: ignore[method-assign]
    grid.GetColumnNames = lambda: None  # type: ignore[method-assign]
    resultado = GuiGridViewHandler().inspecionar(grid)
    assert resultado["colunas"] == ["AUFNR"]
    assert resultado["total_colunas"] == 10
    assert resultado["colunas_completas"] is False


def test_grid_colunas_completas_quando_todas_capturadas() -> None:
    grid = FakeGrid(
        columns=["MATNR", "MENGE"], rows=[], column_count=2,
    )
    resultado = GuiGridViewHandler().inspecionar(grid)
    assert resultado["colunas_completas"] is True


def test_grid_respeita_max_rows() -> None:
    grid = FakeGrid(columns=["A"], rows=[{"A": str(i)} for i in range(10)])
    handler = GuiGridViewHandler(max_rows=3)
    res = handler.inspecionar(grid)
    assert res["total"] == 10
    assert res["exibidas"] == 3
    assert len(res["linhas"]) == 3


def test_grid_snapshot_e_codigo() -> None:
    handler = GuiGridViewHandler()
    antes = {"celula_atual_linha": 0, "celula_atual_coluna": "A", "linhas_selecionadas": ""}
    depois = {"celula_atual_linha": 2, "celula_atual_coluna": "MATNR", "linhas_selecionadas": "2"}
    linhas = handler.gerar_codigo("grid", antes, depois, "python")
    assert any("SetCurrentCell(2, \"MATNR\")" in ln for ln in linhas)
    assert any("SelectedRows = \"2\"" in ln for ln in linhas)


def test_grid_codigo_java_usa_terminador_e_lowercase() -> None:
    handler = GuiGridViewHandler()
    antes = {"celula_atual_linha": -1, "celula_atual_coluna": "", "linhas_selecionadas": ""}
    depois = {"celula_atual_linha": -1, "celula_atual_coluna": "", "linhas_selecionadas": "1"}
    linhas = handler.gerar_codigo("grid", antes, depois, "java")
    assert linhas == ['session.FindById("grid").selectedRows = "1";']


def test_grid_tirar_snapshot_estrutura() -> None:
    grid = FakeGrid(columns=["A"], rows=[], current=(4, "A"), selected="4", first=2)
    snap = GuiGridViewHandler().tirar_snapshot(grid)
    assert snap["celula_atual_linha"] == 4
    assert snap["celula_atual_coluna"] == "A"
    assert snap["linhas_selecionadas"] == "4"
    assert snap["primeira_visivel"] == 2


# --------------------------------------------------------------------------- #
# GuiTree
# --------------------------------------------------------------------------- #
def test_tree_inspecionar_hierarquia() -> None:
    tree = FakeTree(
        nodes={
            "root": {"texto": "Raiz", "filhos": ["c1"], "cols": {"COL1": "x"}},
            "c1": {"texto": "Filho", "filhos": []},
        },
        columns=["COL1"],
        selected=["c1"],
    )
    res = GuiTreeHandler().inspecionar(tree)
    assert res["tipo"] == "GuiTree"
    assert res["total"] == 2
    assert res["colunas"] == ["COL1"]
    raiz = next(n for n in res["nos"] if n["chave"] == "root")
    assert raiz["texto"] == "Raiz"
    assert raiz["filhos"] == ["c1"]
    assert raiz["colunas"] == {"COL1": "x"}
    assert res["no_selecionado"] == "c1"


def test_tree_snapshot_selecionado_e_fallback_sem_selecao() -> None:
    handler = GuiTreeHandler()
    sem_selecao = FakeTree(nodes={"a": {"texto": "A"}}, selected=[])
    snap = handler.tirar_snapshot(sem_selecao)
    # GetSelectedNodes vazio → fallback selectedNode ausente → "".
    assert snap["no_selecionado"] == ""


@pytest.mark.parametrize(
    ("lang", "esperado"),
    [
        ("python", 'session.FindById("tree").SelectNode("0001")'),
        ("vba", 'session.FindById("tree").SelectNode("0001")'),
        ("vbscript", 'session.FindById("tree").SelectNode("0001")'),
        ("powershell", '$Session.FindById("tree").SelectNode("0001")'),
        ("autoit", '$oSession.FindById("tree").SelectNode("0001")'),
        ("java", 'session.FindById("tree").SelectNode("0001");'),
    ],
)
def test_tree_codigo_por_linguagem(lang: str, esperado: str) -> None:
    handler = GuiTreeHandler()
    linhas = handler.gerar_codigo("tree", {"no_selecionado": ""}, {"no_selecionado": "0001"}, lang)
    assert linhas == [esperado]


def test_tree_sem_mudanca_nao_gera_codigo() -> None:
    handler = GuiTreeHandler()
    igual = {"no_selecionado": "x"}
    assert handler.gerar_codigo("t", igual, dict(igual), "python") == []


# --------------------------------------------------------------------------- #
# GuiTextEdit
# --------------------------------------------------------------------------- #
def test_textedit_inspecionar_conteudo() -> None:
    ed = FakeTextEdit(["linha1", "linha2"], first=0, current=1, selected="lin")
    res = GuiTextEditHandler().inspecionar(ed)
    assert res["numero_linhas"] == 2
    assert res["conteudo"] == "linha1\nlinha2"
    assert res["linhas"] == ["linha1", "linha2"]
    assert res["texto_selecionado"] == "lin"


def test_textedit_codigo_escapa_quebra_de_linha() -> None:
    handler = GuiTextEditHandler()
    linhas = handler.gerar_codigo(
        "ed", {"conteudo": "a"}, {"conteudo": "a\nb"}, "python"
    )
    assert linhas == ['session.FindById("ed").text = "a\\nb"']


def test_textedit_sem_mudanca_nao_gera_codigo() -> None:
    handler = GuiTextEditHandler()
    assert handler.gerar_codigo("ed", {"conteudo": "x"}, {"conteudo": "x"}, "python") == []


# --------------------------------------------------------------------------- #
# GuiCalendar
# --------------------------------------------------------------------------- #
def test_calendar_inspecionar_e_snapshot() -> None:
    cal = FakeComponent(
        focusDate="20260101",
        selectionInterval="20260101,20260131",
        firstVisibleDate="20251229",
        lastVisibleDate="20260201",
    )
    handler = GuiCalendarHandler()
    insp = handler.inspecionar(cal)
    assert insp["data_foco"] == "20260101"
    assert insp["selecao_inicio"] == "20260101,20260131"
    snap = handler.tirar_snapshot(cal)
    assert snap["selecao"] == "20260101,20260131"


def test_calendar_codigo_selection_interval() -> None:
    handler = GuiCalendarHandler()
    linhas = handler.gerar_codigo(
        "cal", {"selecao": ""}, {"selecao": "20260101,20260131"}, "vba"
    )
    assert linhas == ['session.FindById("cal").selectionInterval = "20260101,20260131"']


# --------------------------------------------------------------------------- #
# GuiToolbarControl
# --------------------------------------------------------------------------- #
def test_toolbar_inspecionar_botoes() -> None:
    tb = FakeToolbar(
        [
            {"id": "BTN1", "tooltip": "Salvar", "texto": "", "habilitado": True, "tipo": "Button"},
            {"id": "BTN2", "tooltip": "Sair", "texto": "", "habilitado": False, "tipo": "Button"},
        ]
    )
    res = GuiToolbarHandler().inspecionar(tb)
    assert res["total_botoes"] == 2
    assert res["botoes"][0]["id"] == "BTN1"
    assert res["botoes"][0]["habilitado"] is True
    assert res["botoes"][1]["habilitado"] is False


def test_toolbar_snapshot_e_codigo_vazio() -> None:
    handler = GuiToolbarHandler()
    tb = FakeToolbar([{"id": "B", "tooltip": "", "texto": "", "habilitado": True, "tipo": "x"}])
    assert handler.tirar_snapshot(tb)["total_botoes"] == 1
    # Cliques vêm de eventos COM, não de diff.
    assert handler.gerar_codigo("tb", {}, {}, "python") == []


# --------------------------------------------------------------------------- #
# Genérico (fallback)
# --------------------------------------------------------------------------- #
def test_generico_inspecionar_basico() -> None:
    obj = FakeComponent(Type="GuiPicture", SubType="X", Id="wnd[0]/usr/pic")
    res = GuiShellGenerico().inspecionar(obj)
    assert res["tipo"] == "GuiPicture"
    assert res["subtype"] == "X"
    assert res["introspeccao"] is False
    assert GuiShellGenerico().tirar_snapshot(obj) == {"tipo": "GuiShellGenerico"}
    assert GuiShellGenerico().gerar_codigo("x", {}, {}, "python") == []


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def test_get_handler_por_tipo() -> None:
    assert isinstance(get_handler(FakeComponent(Type="GuiGridView")), GuiGridViewHandler)
    assert isinstance(get_handler(FakeComponent(Type="GuiTree")), GuiTreeHandler)


def test_get_handler_desconhecido_retorna_generico() -> None:
    assert get_handler(FakeComponent(Type="GuiPicture")) is GENERIC_HANDLER
    assert get_handler_for_type("Inexistente") is GENERIC_HANDLER


def test_get_handler_resolve_guishell_por_subtype() -> None:
    # Controle reporta Type genérico "GuiShell" e o tipo real em SubType.
    obj = FakeComponent(Type="GuiShell", SubType="GuiGridView")
    assert isinstance(get_handler(obj), GuiGridViewHandler)


def test_get_handler_resolve_subtype_sem_prefixo_gui() -> None:
    # SAP real reporta SubType SEM o prefixo "Gui" (ex.: "Tree", "GridView").
    assert isinstance(get_handler(FakeComponent(Type="GuiShell", SubType="Tree")), GuiTreeHandler)
    assert isinstance(
        get_handler(FakeComponent(Type="GuiShell", SubType="GridView")), GuiGridViewHandler
    )


@pytest.mark.parametrize(
    ("sap_type", "subtype", "esperado"),
    [
        ("GuiShell", "Tree", "GuiTree"),
        ("GuiShell", "GridView", "GuiGridView"),
        ("GuiShell", "TextEdit", "GuiTextEdit"),
        ("GuiShell", "Calendar", "GuiCalendar"),
        ("GuiShell", "GuiGridView", "GuiGridView"),  # já é chave do registry
        ("GuiShell", "Picture", "GuiPicture"),  # desconhecido: prefixa "Gui"
        ("GuiShell", "", "GuiShell"),  # sem subtype: mantém
        ("GuiTextField", "", "GuiTextField"),  # não-shell: inalterado
    ],
)
def test_normalize_shell_type(sap_type: str, subtype: str, esperado: str) -> None:
    assert normalize_shell_type(sap_type, subtype) == esperado


def test_is_supported_shell() -> None:
    assert is_supported_shell("GuiGridView") is True
    assert is_supported_shell("GuiPicture") is False
    assert set(HANDLERS) >= {"GuiGridView", "GuiTree", "GuiTextEdit", "GuiCalendar"}

"""Testes do motor de polling (diff de snapshots → ações) e do ciclo poll_once."""

from __future__ import annotations

from typing import Any

import src.core.recorder_polling as rp
from src.core.recorder_polling import PollingRecorder, collect_shells, diff_to_acoes
from tests.conftest import FakeComponent


# --------------------------------------------------------------------------- #
# diff_to_acoes — função pura
# --------------------------------------------------------------------------- #
def test_grid_cell_change() -> None:
    antes = {"tipo": "GuiGridView", "celula_atual_linha": 0, "celula_atual_coluna": "A"}
    depois = {"tipo": "GuiGridView", "celula_atual_linha": 3, "celula_atual_coluna": "EBELN"}
    acoes = diff_to_acoes("grid", antes, depois)
    assert len(acoes) == 1
    assert acoes[0].tipo == "set_current_cell"
    assert acoes[0].args == {"row": 3, "column": "EBELN"}
    assert acoes[0].origem == "polling"


def test_grid_selection_change() -> None:
    antes = {"tipo": "GuiGridView", "linhas_selecionadas": ""}
    depois = {"tipo": "GuiGridView", "linhas_selecionadas": "0-2"}
    acoes = diff_to_acoes("grid", antes, depois)
    assert [a.tipo for a in acoes] == ["set_selected_rows"]
    assert acoes[0].args == {"rows": "0-2"}


def test_grid_sem_mudanca_nao_gera_acao() -> None:
    snap = {"tipo": "GuiGridView", "celula_atual_linha": 1, "celula_atual_coluna": "A",
            "linhas_selecionadas": "0"}
    assert diff_to_acoes("grid", snap, dict(snap)) == []


def test_tree_select_node() -> None:
    antes = {"tipo": "GuiTree", "no_selecionado": ""}
    depois = {"tipo": "GuiTree", "no_selecionado": "0001"}
    acoes = diff_to_acoes("tree", antes, depois)
    assert acoes[0].tipo == "select_node"
    assert acoes[0].args == {"key": "0001"}


def test_textedit_set_text() -> None:
    antes = {"tipo": "GuiTextEdit", "conteudo": "linha1"}
    depois = {"tipo": "GuiTextEdit", "conteudo": "linha1\nlinha2"}
    acoes = diff_to_acoes("ed", antes, depois)
    assert acoes[0].tipo == "set_text"
    assert acoes[0].args == {"text": "linha1\nlinha2"}


def test_calendar_selection_interval() -> None:
    antes = {"tipo": "GuiCalendar", "selecao": ""}
    depois = {"tipo": "GuiCalendar", "selecao": "20260101,20260131"}
    acoes = diff_to_acoes("cal", antes, depois)
    assert acoes[0].tipo == "selection_interval"
    assert acoes[0].args == {"value": "20260101,20260131"}


def test_tipo_desconhecido_sem_acao() -> None:
    assert diff_to_acoes("x", {"tipo": "GuiShellGenerico"}, {"tipo": "GuiShellGenerico"}) == []


# --------------------------------------------------------------------------- #
# PollingRecorder.poll_once — usa fakes injetados via monkeypatch
# --------------------------------------------------------------------------- #
class _FakeHandler:
    """Handler falso: devolve o snapshot que lhe for atribuído."""

    def __init__(self, snap: dict[str, Any]) -> None:
        self.snap = snap

    def tirar_snapshot(self, _obj: Any) -> dict[str, Any]:
        return self.snap


def test_poll_once_baseline_depois_mudanca(monkeypatch: Any) -> None:
    capturadas: list[Any] = []
    estado = {"tipo": "GuiTextEdit", "conteudo": "v1"}
    handler = _FakeHandler(estado)

    monkeypatch.setattr(rp, "collect_shells", lambda _s: [("ed", object())])
    monkeypatch.setattr(rp, "get_handler", lambda _o: handler)

    rec = PollingRecorder(session=object(), sink=capturadas.append)

    # 1º ciclo: linha de base, não emite.
    assert rec.poll_once(emit=False) == []
    assert capturadas == []

    # Estado muda → próximo ciclo emite uma ação set_text.
    handler.snap = {"tipo": "GuiTextEdit", "conteudo": "v2"}
    detectadas = rec.poll_once(emit=True)
    assert len(detectadas) == 1
    assert detectadas[0].tipo == "set_text"
    assert capturadas and capturadas[0].args == {"text": "v2"}


def test_poll_once_sem_mudanca_nao_emite(monkeypatch: Any) -> None:
    capturadas: list[Any] = []
    handler = _FakeHandler({"tipo": "GuiTextEdit", "conteudo": "igual"})
    monkeypatch.setattr(rp, "collect_shells", lambda _s: [("ed", object())])
    monkeypatch.setattr(rp, "get_handler", lambda _o: handler)

    rec = PollingRecorder(session=object(), sink=capturadas.append)
    rec.poll_once(emit=False)
    assert rec.poll_once(emit=True) == []
    assert capturadas == []


# --------------------------------------------------------------------------- #
# collect_shells — descoberta de GuiShell na árvore
# --------------------------------------------------------------------------- #
class _Coll:
    def __init__(self, items: list[Any]) -> None:
        self._items = list(items)
        self.Count = len(self._items)

    def ElementAt(self, i: int) -> Any:
        return self._items[i]


def test_collect_shells_encontra_grid() -> None:
    grid = FakeComponent(Id="wnd[0]/usr/cntlGRID1/shellcont/shell", Type="GuiGridView")
    session = FakeComponent(Id="ses[0]", Type="GuiSession", Children=_Coll([grid]))
    # find_by_id é chamado pelo Analyser interno; resolvemos o próprio grid.
    session.FindById = lambda oid, *a: grid if oid == grid.Id else None  # type: ignore[attr-defined]
    pares = collect_shells(session)
    assert pares == [(grid.Id, grid)]


def test_collect_shells_sessao_sem_shell() -> None:
    # Objeto sem árvore navegável → nenhum shell, sem exceção.
    assert collect_shells(object()) == []


# --------------------------------------------------------------------------- #
# PollingRecorder — ciclo de vida da thread
# --------------------------------------------------------------------------- #
def test_start_stop_thread() -> None:
    rec = PollingRecorder(session=object(), sink=lambda _a: None, poll_interval=0.01)
    assert rec.is_running is False
    rec.start()
    assert rec.is_running is True
    rec.start()  # no-op quando já rodando
    rec.stop()
    assert rec.is_running is False
    rec.stop()  # idempotente

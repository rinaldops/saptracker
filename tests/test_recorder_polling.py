"""Testes do motor de polling (diff de snapshots → ações) e do ciclo poll_once."""

from __future__ import annotations

from typing import Any

import src.core.recorder_polling as rp
from src.core.recorder_polling import (
    PollingRecorder,
    collect_shells,
    diff_field,
    diff_to_acoes,
    snapshot_field,
)
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


def test_poll_once_nao_captura_shells_quando_desabilitado(monkeypatch: Any) -> None:
    """Com COM ativo (capture_shells=False) o polling ignora GuiShell por completo."""
    capturadas: list[Any] = []
    handler = _FakeHandler({"tipo": "GuiTextEdit", "conteudo": "v1"})
    chamadas: list[int] = []

    def _fake_collect(_s: Any) -> list[Any]:
        chamadas.append(1)
        return [("ed", object())]

    monkeypatch.setattr(rp, "collect_shells", _fake_collect)
    monkeypatch.setattr(rp, "get_handler", lambda _o: handler)

    rec = PollingRecorder(
        session=object(), sink=capturadas.append,
        capture_fields=False, capture_shells=False,
    )
    rec.poll_once(emit=False)
    handler.snap = {"tipo": "GuiTextEdit", "conteudo": "v2"}  # mudaria, se observado
    assert rec.poll_once(emit=True) == []
    assert capturadas == []
    assert chamadas == []  # collect_shells nunca chamado


def test_scan_windows_inclui_active_window_mesmo_sem_modal() -> None:
    """Popup de sistema (Children.Count=1) ainda expõe o título via ActiveWindow."""
    rec = PollingRecorder(object(), lambda _a: None)
    session = FakeComponent(
        ActiveWindow=FakeComponent(Text="Exibir logs"),
        Children=[FakeComponent(Text="Transferência MIGO")],
    )
    modal, titles = rec._scan_windows(session)
    assert modal is False  # só 1 janela filha → sem modal contado
    assert "Exibir logs" in titles
    assert "Transferência MIGO" in titles


def test_scan_windows_detecta_modal_por_contagem() -> None:
    rec = PollingRecorder(object(), lambda _a: None)
    session = FakeComponent(
        ActiveWindow=FakeComponent(Text="Popup"),
        Children=[FakeComponent(Text="Principal"), FakeComponent(Text="Popup")],
    )
    modal, titles = rec._scan_windows(session)
    assert modal is True
    assert titles == frozenset({"Popup", "Principal"})


def test_sap_window_titles_property_default_vazio() -> None:
    rec = PollingRecorder(object(), lambda _a: None)
    assert rec.sap_window_titles == frozenset()


def test_set_capture_shells_alterna_flag() -> None:
    rec = PollingRecorder(object(), lambda _a: None, capture_shells=False)
    assert rec._capture_shells is False
    rec.set_capture_shells(True)
    assert rec._capture_shells is True


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
# --------------------------------------------------------------------------- #
# snapshot_field e diff_field — GuiTabStrip
# --------------------------------------------------------------------------- #
def test_snapshot_field_tabstrip() -> None:
    tab = FakeComponent(Id="wnd[0]/usr/tabsTS/tabpABA1")
    strip = FakeComponent(Type="GuiTabStrip", SelectedTab=tab)
    snap = snapshot_field(strip, "GuiTabStrip")
    assert snap == {"tipo": "GuiTabStrip", "selected_tab_id": "wnd[0]/usr/tabsTS/tabpABA1"}


def test_snapshot_field_tabstrip_sem_tab() -> None:
    strip = FakeComponent(Type="GuiTabStrip", SelectedTab=None)
    snap = snapshot_field(strip, "GuiTabStrip")
    assert snap["selected_tab_id"] == ""


def test_diff_field_tabstrip_emite_select() -> None:
    antes = {"tipo": "GuiTabStrip", "selected_tab_id": "wnd[0]/usr/tabsTS/tabpABA1"}
    depois = {"tipo": "GuiTabStrip", "selected_tab_id": "wnd[0]/usr/tabsTS/tabpABA2"}
    acoes = diff_field("wnd[0]/usr/tabsTS", "GuiTabStrip", antes, depois)
    assert len(acoes) == 1
    assert acoes[0].tipo == "select"
    assert acoes[0].obj_id == "wnd[0]/usr/tabsTS/tabpABA2"
    assert acoes[0].origem == "campo"


def test_diff_field_tabstrip_mesma_aba_sem_acao() -> None:
    snap = {"tipo": "GuiTabStrip", "selected_tab_id": "wnd[0]/usr/tabsTS/tabpABA1"}
    assert diff_field("strip", "GuiTabStrip", snap, dict(snap)) == []


def test_polling_pode_restringir_captura_a_shells() -> None:
    recorder = rp.PollingRecorder(object(), lambda _action: None, capture_fields=False)
    assert recorder._capture_fields is False
    recorder.set_capture_fields(True)
    assert recorder._capture_fields is True


def test_diff_field_tabstrip_tab_vazio_sem_acao() -> None:
    antes = {"tipo": "GuiTabStrip", "selected_tab_id": ""}
    depois = {"tipo": "GuiTabStrip", "selected_tab_id": ""}
    assert diff_field("strip", "GuiTabStrip", antes, depois) == []


# --------------------------------------------------------------------------- #
# collect_fields — filtro Changeable
# --------------------------------------------------------------------------- #
def test_collect_fields_pula_readonly(monkeypatch: Any) -> None:
    """Campos com Changeable=False não devem entrar na lista."""
    editavel = FakeComponent(
        Id="wnd[0]/usr/fld1", Type="GuiTextField", Text="abc",
        Changeable=True, ContainerType=False,
    )
    readonly = FakeComponent(
        Id="wnd[0]/usr/fld2", Type="GuiTextField", Text="xyz",
        Changeable=False, ContainerType=False,
    )
    from tests.conftest import FakeComponent as FC

    class _Coll2:
        Count = 2
        def ElementAt(self, i: int):
            return [editavel, readonly][i]

    session = FC(Id="ses[0]", Type="GuiSession", Children=_Coll2())
    pares = rp.collect_fields(session)
    ids = [oid for oid, _, _ in pares]
    assert "wnd[0]/usr/fld1" in ids
    assert "wnd[0]/usr/fld2" not in ids


def test_collect_fields_pula_guitab_inativo(monkeypatch: Any) -> None:
    """GuiTab com Changeable=False (aba inativa) não deve ser traversado."""
    campo_na_aba_inativa = FakeComponent(
        Id="wnd[0]/usr/tabs/tabpINATIVA/ssubCONTENT/fld",
        Type="GuiTextField", Text="hidden",
        Changeable=True,
    )

    class _CollInner:
        Count = 1
        def ElementAt(self, i: int):
            return campo_na_aba_inativa

    aba_inativa = FakeComponent(
        Id="wnd[0]/usr/tabs/tabpINATIVA",
        Type="GuiTab",
        Changeable=False,
        Children=_CollInner(),
    )

    class _CollOuter:
        Count = 1
        def ElementAt(self, i: int):
            return aba_inativa

    session = FakeComponent(Id="ses[0]", Type="GuiSession", Children=_CollOuter())
    pares = rp.collect_fields(session)
    ids = [oid for oid, _, _ in pares]
    assert campo_na_aba_inativa.Id not in ids, "campo de GuiTab inativo não deve ser coletado"


def test_collect_fields_inclui_guitab_ativo(monkeypatch: Any) -> None:
    """GuiTab com Changeable=True (aba ativa) DEVE ser traversado."""
    campo_na_aba_ativa = FakeComponent(
        Id="wnd[0]/usr/tabs/tabpATIVA/ssubCONTENT/fld",
        Type="GuiTextField", Text="visible",
        Changeable=True,
    )

    class _CollInner:
        Count = 1
        def ElementAt(self, i: int):
            return campo_na_aba_ativa

    aba_ativa = FakeComponent(
        Id="wnd[0]/usr/tabs/tabpATIVA",
        Type="GuiTab",
        Changeable=True,
        Children=_CollInner(),
    )

    class _CollOuter:
        Count = 1
        def ElementAt(self, i: int):
            return aba_ativa

    session = FakeComponent(Id="ses[0]", Type="GuiSession", Children=_CollOuter())
    pares = rp.collect_fields(session)
    ids = [oid for oid, _, _ in pares]
    assert campo_na_aba_ativa.Id in ids, "campo de GuiTab ativo deve ser coletado"


def test_start_stop_thread(monkeypatch: Any) -> None:
    # Sem isso, a thread chamaria win32com.client.GetObject("SAPGUI") de
    # verdade em _acquire_thread_session — inofensivo quando não há SAP GUI
    # aberto, mas se houver, o teste passa a varrer uma sessão real e pode
    # ultrapassar o timeout do stop(), deixando a thread órfã (ver stop()).
    monkeypatch.setattr(PollingRecorder, "_acquire_thread_session", lambda self: None)
    rec = PollingRecorder(session=object(), sink=lambda _a: None, poll_interval=0.01)
    assert rec.is_running is False
    rec.start()
    assert rec.is_running is True
    rec.start()  # no-op quando já rodando
    rec.stop()
    assert rec.is_running is False
    rec.stop()  # idempotente

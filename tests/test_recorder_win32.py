"""Testes do motor Win32 (ClassNN, construção da ação e detecção de diálogos)."""

from __future__ import annotations

import sys
from typing import Any

from src.core.recorder_win32 import Win32Recorder, classnn_map, dialog_to_acao
from tests.conftest import FakeComponent


def test_classnn_map_numera_por_classe() -> None:
    classes = ["Static", "Edit", "Edit", "Button", "Static", "Button"]
    assert classnn_map(classes) == [
        "Static1",
        "Edit1",
        "Edit2",
        "Button1",
        "Static2",
        "Button2",
    ]


def test_dialog_to_acao_estrutura() -> None:
    acao = dialog_to_acao(
        "Salvar como",
        controls=[("Edit1", "C:\\saida.txt")],
        button="Button1",
        timeout=15,
    )
    assert acao.tipo == "win32_dialog"
    assert acao.origem == "win32"
    assert acao.args["title"] == "Salvar como"
    assert acao.args["class"] == "#32770"
    assert acao.args["timeout"] == 15
    assert acao.args["controls"] == [{"control": "Edit1", "text": "C:\\saida.txt"}]
    assert acao.args["button"] == "Button1"


def test_scan_once_captura_uma_vez(monkeypatch: Any) -> None:
    """Um diálogo novo é adiado 1 ciclo, capturado uma vez; rescans não duplicam."""
    capturadas: list[Any] = []
    rec = Win32Recorder(sink=capturadas.append)

    # Simula um diálogo de handle 42 presente em varreduras seguidas.
    monkeypatch.setattr(rec, "_enumerate_dialogs", lambda: [42])
    monkeypatch.setattr(
        rec,
        "_capture",
        lambda hwnd: dialog_to_acao("Imprimir", [("Edit1", "1")], "Button1"),
    )

    primeira = rec.scan_once()   # adia (1ª aparição)
    segunda = rec.scan_once()    # captura (2ª aparição)
    terceira = rec.scan_once()   # já visto → não recaptura
    assert primeira == []
    assert len(segunda) == 1
    assert terceira == []
    assert len(capturadas) == 1
    assert capturadas[0].args["title"] == "Imprimir"


def test_dialogo_fechado_e_reaberto_recaptura(monkeypatch: Any) -> None:
    capturadas: list[Any] = []
    rec = Win32Recorder(sink=capturadas.append)
    monkeypatch.setattr(
        rec, "_capture", lambda hwnd: dialog_to_acao("D", [], "")
    )

    monkeypatch.setattr(rec, "_enumerate_dialogs", lambda: [7])
    rec.scan_once()  # adia
    rec.scan_once()  # captura
    monkeypatch.setattr(rec, "_enumerate_dialogs", lambda: [])  # fechou
    rec.scan_once()
    monkeypatch.setattr(rec, "_enumerate_dialogs", lambda: [7])  # reabriu (handle reciclado)
    rec.scan_once()  # adia de novo
    rec.scan_once()  # captura de novo
    assert len(capturadas) == 2


# --------------------------------------------------------------------------- #
# Distinção SAP modal × diálogo do SO
# --------------------------------------------------------------------------- #
def _sessao_com_n_janelas(n: int) -> FakeComponent:
    """Sessão falsa cujo ``Children`` tem ``n`` janelas (com_len lê ``Count``)."""
    return FakeComponent(Id="/app/con[0]/ses[0]", Children=FakeComponent(Count=n))


def test_scan_ignora_modal_do_proprio_sap(monkeypatch: Any) -> None:
    """#32770 que é janela modal SAP (wnd[1]) não é capturado pelo AutoItX."""
    capturadas: list[Any] = []
    rec = Win32Recorder(sink=capturadas.append)
    rec._thread_session = _sessao_com_n_janelas(2)  # wnd[0] + wnd[1] (modal SAP)
    monkeypatch.setattr(rec, "_enumerate_dialogs", lambda: [55])
    monkeypatch.setattr(rec, "_title_safe", lambda h: "Informação")
    monkeypatch.setattr(
        rec, "_capture", lambda h: dialog_to_acao("Informação", [], "Button1")
    )
    assert rec.scan_once() == []  # adia
    assert rec.scan_once() == []  # decide: modal SAP → ignora
    assert capturadas == []


def test_scan_usa_predicado_externo_de_modal(monkeypatch: Any) -> None:
    """O predicado injetado (ex.: flag do polling) tem prioridade sobre o COM próprio."""
    capturadas: list[Any] = []
    modal = {"aberto": True}
    rec = Win32Recorder(sink=capturadas.append, is_sap_modal_open=lambda: modal["aberto"])
    monkeypatch.setattr(rec, "_enumerate_dialogs", lambda: [55])
    monkeypatch.setattr(rec, "_title_safe", lambda h: "Informação")
    monkeypatch.setattr(rec, "_capture", lambda h: dialog_to_acao("Informação", [], "B1"))
    rec.scan_once()  # adia
    assert rec.scan_once() == []  # predicado True → ignora
    assert capturadas == []


def test_scan_captura_dialogo_do_so_sem_modal_sap(monkeypatch: Any) -> None:
    """#32770 sem modal SAP correspondente (só wnd[0]) é um diálogo do SO real."""
    capturadas: list[Any] = []
    rec = Win32Recorder(sink=capturadas.append)
    rec._thread_session = _sessao_com_n_janelas(1)  # apenas wnd[0]
    monkeypatch.setattr(rec, "_enumerate_dialogs", lambda: [55])
    monkeypatch.setattr(rec, "_title_safe", lambda h: "Salvar como")
    monkeypatch.setattr(
        rec, "_capture", lambda h: dialog_to_acao("Salvar como", [], "Button1")
    )
    assert rec.scan_once() == []      # adia
    assert len(rec.scan_once()) == 1  # decide: sem modal SAP → captura
    assert capturadas[0].args["title"] == "Salvar como"


def test_sap_modal_open_sem_sessao_e_false() -> None:
    rec = Win32Recorder(sink=lambda _a: None)  # session=None → _thread_session None
    assert rec._sap_modal_open() is False


def test_extract_indices_da_sessao() -> None:
    assert Win32Recorder._extract_indices(FakeComponent(Id="/app/con[2]/ses[3]")) == (2, 3)
    assert Win32Recorder._extract_indices(None) == (0, 0)


# --------------------------------------------------------------------------- #
# Ciclo de vida da thread
# --------------------------------------------------------------------------- #
def test_start_no_op_sem_win32(monkeypatch: Any) -> None:
    rec = Win32Recorder(sink=lambda _a: None)
    monkeypatch.setattr(rec, "_win32_available", lambda: False)
    rec.start()
    assert rec.is_running is False


def test_start_stop_thread(monkeypatch: Any) -> None:
    rec = Win32Recorder(sink=lambda _a: None, scan_interval=0.01)
    monkeypatch.setattr(rec, "_win32_available", lambda: True)
    monkeypatch.setattr(rec, "_enumerate_dialogs", lambda: [])  # nenhuma janela
    rec.start()
    assert rec.is_running is True
    rec.start()  # no-op quando já rodando
    rec.stop()
    assert rec.is_running is False


# --------------------------------------------------------------------------- #
# Camada win32gui (módulo falso injetado em sys.modules)
# --------------------------------------------------------------------------- #
class _FakeWin32Gui:
    """``win32gui`` falso com um diálogo ``#32770`` e seus filhos."""

    def __init__(self) -> None:
        # hwnd -> classe (janelas de topo + filhos)
        self._classes = {100: "#32770", 200: "Notepad", 1: "Static", 2: "Edit", 3: "Button"}
        self._titles = {100: "Salvar como", 1: "", 2: "C:\\saida.txt", 3: "Salvar"}
        self._children = {100: [1, 2, 3]}

    def IsWindowVisible(self, hwnd: int) -> bool:
        return True

    def GetClassName(self, hwnd: int) -> str:
        return self._classes.get(hwnd, "")

    def GetWindowText(self, hwnd: int) -> str:
        return self._titles.get(hwnd, "")

    def EnumWindows(self, cb: Any, extra: Any) -> None:
        for hwnd in (100, 200):
            cb(hwnd, extra)

    def EnumChildWindows(self, hwnd: int, cb: Any, extra: Any) -> None:
        for child in self._children.get(hwnd, []):
            cb(child, extra)


def test_enumerate_dialogs_filtra_classe_32770(monkeypatch: Any) -> None:
    monkeypatch.setitem(sys.modules, "win32gui", _FakeWin32Gui())
    rec = Win32Recorder(sink=lambda _a: None)
    assert rec._enumerate_dialogs() == [100]  # ignora a janela Notepad


def test_capture_extrai_titulo_edits_e_botao(monkeypatch: Any) -> None:
    monkeypatch.setitem(sys.modules, "win32gui", _FakeWin32Gui())
    rec = Win32Recorder(sink=lambda _a: None)
    acao = rec._capture(100)
    assert acao is not None
    assert acao.args["title"] == "Salvar como"
    assert acao.args["controls"] == [{"control": "Edit1", "text": "C:\\saida.txt"}]
    assert acao.args["button"] == "Button1"


def test_win32_available_retorna_bool() -> None:
    rec = Win32Recorder(sink=lambda _a: None)
    assert isinstance(rec._win32_available(), bool)

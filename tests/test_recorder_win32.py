"""Testes do motor Win32 (ClassNN, construção da ação e detecção de diálogos)."""

from __future__ import annotations

import sys
from typing import Any

from src.core.recorder_win32 import Win32Recorder, classnn_map, dialog_to_acao


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
    """Um diálogo novo é capturado uma vez; rescans não duplicam."""
    capturadas: list[Any] = []
    rec = Win32Recorder(sink=capturadas.append)

    # Simula um diálogo de handle 42 presente em duas varreduras seguidas.
    monkeypatch.setattr(rec, "_enumerate_dialogs", lambda: [42])
    monkeypatch.setattr(
        rec,
        "_capture",
        lambda hwnd: dialog_to_acao("Imprimir", [("Edit1", "1")], "Button1"),
    )

    primeira = rec.scan_once()
    segunda = rec.scan_once()
    assert len(primeira) == 1
    assert segunda == []  # já visto → não recaptura
    assert len(capturadas) == 1
    assert capturadas[0].args["title"] == "Imprimir"


def test_dialogo_fechado_e_reaberto_recaptura(monkeypatch: Any) -> None:
    capturadas: list[Any] = []
    rec = Win32Recorder(sink=capturadas.append)
    monkeypatch.setattr(
        rec, "_capture", lambda hwnd: dialog_to_acao("D", [], "")
    )

    monkeypatch.setattr(rec, "_enumerate_dialogs", lambda: [7])
    rec.scan_once()
    monkeypatch.setattr(rec, "_enumerate_dialogs", lambda: [])  # fechou
    rec.scan_once()
    monkeypatch.setattr(rec, "_enumerate_dialogs", lambda: [7])  # reabriu (handle reciclado)
    rec.scan_once()
    assert len(capturadas) == 2


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

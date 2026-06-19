"""Testes do motor Win32 (ClassNN, construção da ação e detecção de diálogos)."""

from __future__ import annotations

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

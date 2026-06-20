"""Testes do orquestrador (buffer thread-safe, ciclo de vida e geração híbrida)."""

from __future__ import annotations

import threading
from typing import Any

from src.codegen import Acao
from src.core.recorder import ActionBuffer, Recorder
from tests.conftest import FakeSession


# --------------------------------------------------------------------------- #
# ActionBuffer
# --------------------------------------------------------------------------- #
def test_buffer_add_snapshot_clear() -> None:
    buf = ActionBuffer()
    buf.add(Acao(tipo="press", obj_id="b"))
    assert len(buf) == 1
    snap = buf.snapshot()
    assert snap[0].obj_id == "b"
    # snapshot é cópia: limpar o buffer não afeta a cópia já obtida.
    buf.clear()
    assert len(buf) == 0
    assert len(snap) == 1


def test_buffer_thread_safe() -> None:
    buf = ActionBuffer()

    def worker() -> None:
        for _ in range(1000):
            buf.add(Acao(tipo="press", obj_id="b"))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(buf) == 8000


# --------------------------------------------------------------------------- #
# Recorder — ciclo de vida sem motores (evita threads/COM nos testes)
# --------------------------------------------------------------------------- #
def _recorder_sem_motores() -> Recorder:
    return Recorder(
        FakeSession(),
        capture_com=False,
        capture_polling=False,
        capture_win32=False,
    )


def test_start_stop_alterna_estado() -> None:
    rec = _recorder_sem_motores()
    assert not rec.is_recording
    rec.start()
    assert rec.is_recording
    rec.stop()
    assert not rec.is_recording


def test_session_info_extraido_da_sessao() -> None:
    rec = _recorder_sem_motores()
    info = rec.session_info()
    assert info.system == "PRD"
    assert info.client == "100"
    assert info.user == "TESTER"
    assert info.transaction == "SE16"


def test_start_limpa_buffer() -> None:
    rec = _recorder_sem_motores()
    rec.add_action(Acao(tipo="press", obj_id="b"))
    assert len(rec.actions) == 1
    rec.start()  # start deve limpar a gravação anterior
    assert rec.actions == []
    rec.stop()


# --------------------------------------------------------------------------- #
# Geração híbrida (SAP + Win32 intercalados)
# --------------------------------------------------------------------------- #
def test_geracao_hibrida_preserva_ordem_e_linguagem() -> None:
    rec = _recorder_sem_motores()
    # Ordem cronológica: COM → polling (GuiShell) → Win32 nativo.
    rec.add_action(Acao(tipo="set_text", obj_id="wnd[0]/usr/txt", args={"text": "ME23N"}))
    rec.add_action(
        Acao(tipo="select_node", obj_id="wnd[0]/usr/shell", args={"key": "K1"},
             origem="polling")
    )
    rec.add_action(
        Acao(
            tipo="win32_dialog",
            origem="win32",
            args={
                "title": "Salvar como",
                "class": "#32770",
                "controls": [{"control": "Edit1", "text": "C:\\x.txt"}],
                "button": "Button1",
                "timeout": 10,
            },
        )
    )

    py = rec.generate_code("python")
    assert "import win32com.client" in py
    assert '.Text = "ME23N"' in py
    assert 'SelectNode("K1")' in py
    assert "import autoit" in py
    # ordem preservada: set_text antes de SelectNode antes do diálogo
    assert py.index("ME23N") < py.index("SelectNode") < py.index("Salvar como")


def test_generate_code_usa_session_info_quando_omitido() -> None:
    rec = _recorder_sem_motores()
    rec.add_action(Acao(tipo="press", obj_id="b"))
    vba = rec.generate_code("vba")
    assert "PRD" in vba and "SE16" in vba
    assert "Sub SAP_Macro()" in vba


def test_start_desativa_polling_de_campos_quando_com_esta_ativo(monkeypatch: Any) -> None:
    recorder = Recorder(
        FakeSession(),
        capture_com=True,
        capture_polling=True,
        capture_win32=False,
    )
    states: list[bool] = []
    assert recorder._com is not None
    assert recorder._polling is not None

    def start_com() -> None:
        recorder._com._active = True  # type: ignore[union-attr]

    monkeypatch.setattr(recorder._com, "start", start_com)
    monkeypatch.setattr(recorder._com, "stop", lambda: None)
    monkeypatch.setattr(recorder._polling, "set_capture_fields", states.append)
    monkeypatch.setattr(recorder._polling, "start", lambda: None)
    monkeypatch.setattr(recorder._polling, "stop", lambda: None)
    recorder.start()
    recorder.stop()
    assert states == [False]

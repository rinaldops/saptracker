"""Testes de UI (PyQt6) executados headless via plataforma offscreen.

Não exigem SAP real: a conexão é substituída por um *fake* e a sessão é injetada
diretamente no :class:`AppContext`. Focam na fiação entre abas (sinais, geração
de código, editor) — não na renderização.
"""

from __future__ import annotations

import os

import pytest

# Garante backend sem display antes de importar Qt.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6")

from src.codegen import Acao  # noqa: E402
from src.ui.code_editor import CodeEditor  # noqa: E402
from src.ui.context import AppContext  # noqa: E402
from src.ui.main_window import MainWindow  # noqa: E402
from tests.conftest import FakeSession  # noqa: E402


@pytest.fixture
def janela(qtbot):  # type: ignore[no-untyped-def]
    win = MainWindow()
    qtbot.addWidget(win)
    return win


def test_quatro_abas(janela) -> None:  # type: ignore[no-untyped-def]
    titulos = [janela.tabs.tabText(i) for i in range(janela.tabs.count())]
    assert titulos == ["Conexão", "Analyser", "Recorder", "Código"]


def test_combo_linguagens_vba_primeiro(janela) -> None:  # type: ignore[no-untyped-def]
    combo = janela.recorder_tab.combo
    assert combo.count() >= 6
    assert combo.itemData(0) == "vba"


def test_code_editor_roundtrip(qtbot) -> None:  # type: ignore[no-untyped-def]
    ed = CodeEditor()
    qtbot.addWidget(ed)
    ed.set_language("python")
    ed.set_text("print('oi')\n")
    assert "print('oi')" in ed.text()
    ed.set_language("vba")  # sem lexer dedicado: não deve quebrar
    assert ed.language == "vba"


def test_fluxo_gravacao_gera_codigo_na_aba_codigo(janela) -> None:  # type: ignore[no-untyped-def]
    ctx = janela.ctx
    ctx.set_session(FakeSession())

    # Inicia gravação sem motores reais: desabilita as capturas substituindo
    # o recorder por um cujos motores estão desligados.
    from src.core.recorder import Recorder

    ctx.recorder = Recorder(
        ctx.session, capture_com=False, capture_polling=False, capture_win32=False
    )
    ctx.recorder.start()
    ctx.recordingChanged.emit(True)

    ctx.recorder.add_action(Acao(tipo="set_text", obj_id="wnd[0]/usr/txt", args={"text": "ME23N"}))
    ctx.stop_recording()

    # Seleciona Python e gera.
    combo = janela.recorder_tab.combo
    combo.setCurrentIndex(combo.findData("python"))
    janela.recorder_tab.generate()

    texto = janela.code_tab.editor.text()
    assert "import win32com.client" in texto
    assert 'ME23N' in texto
    # A aba Código deve ter vindo para frente.
    assert janela.tabs.currentWidget() is janela.code_tab


def test_context_start_recording_sem_sessao_falha() -> None:
    ctx = AppContext()
    assert ctx.start_recording() is False
    assert not ctx.is_recording

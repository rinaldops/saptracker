"""Testes do motor de eventos COM (mapeamento componente → ação)."""

from __future__ import annotations

from typing import Any

from src.core.recorder_com import ComRecorder, _SessionEventSink, acao_from_component
from tests.conftest import FakeComponent


def test_textfield_vira_set_text() -> None:
    comp = FakeComponent(Id="wnd[0]/usr/txtX", Type="GuiTextField", Text="ME23N")
    acao = acao_from_component(comp)
    assert acao is not None
    assert acao.tipo == "set_text"
    assert acao.obj_id == "wnd[0]/usr/txtX"
    assert acao.args == {"text": "ME23N"}
    assert acao.origem == "com_event"


def test_okcode_vira_set_text() -> None:
    comp = FakeComponent(Id="wnd[0]/tbar[0]/okcd", Type="GuiOkCodeField", Text="/nVA01")
    acao = acao_from_component(comp)
    assert acao is not None and acao.args["text"] == "/nVA01"


def test_checkbox_vira_set_checkbox_bool() -> None:
    comp = FakeComponent(Id="wnd[0]/usr/chk", Type="GuiCheckBox", Selected=True)
    acao = acao_from_component(comp)
    assert acao is not None
    assert acao.tipo == "set_checkbox"
    assert acao.args == {"selected": True}


def test_combobox_vira_set_combo_key() -> None:
    comp = FakeComponent(Id="wnd[0]/usr/cmb", Type="GuiComboBox", Key="0002")
    acao = acao_from_component(comp)
    assert acao is not None
    assert acao.tipo == "set_combo_key"
    assert acao.args == {"key": "0002"}


def test_button_vira_press_sem_args() -> None:
    comp = FakeComponent(Id="wnd[0]/tbar[0]/btn[0]", Type="GuiButton")
    acao = acao_from_component(comp)
    assert acao is not None
    assert acao.tipo == "press"
    assert acao.args == {}


def test_radio_vira_select() -> None:
    comp = FakeComponent(Id="wnd[0]/usr/rad", Type="GuiRadioButton")
    acao = acao_from_component(comp)
    assert acao is not None and acao.tipo == "select"


def test_guishell_nao_e_capturado_por_com() -> None:
    """GuiShell é responsabilidade do motor de polling, não dos eventos COM."""
    comp = FakeComponent(Id="wnd[0]/usr/cntlGRID/shell", Type="GuiShell")
    assert acao_from_component(comp) is None


def test_tipo_desconhecido_retorna_none() -> None:
    comp = FakeComponent(Id="x", Type="GuiFooBar")
    assert acao_from_component(comp) is None


def test_sem_id_retorna_none() -> None:
    comp = FakeComponent(Id="", Type="GuiTextField", Text="x")
    assert acao_from_component(comp) is None


def test_timestamp_e_origem_propagados() -> None:
    comp = FakeComponent(Id="x", Type="GuiButton")
    acao = acao_from_component(comp, origem="com_event", timestamp="10:00:00")
    assert acao is not None
    assert acao.timestamp == "10:00:00"


# --------------------------------------------------------------------------- #
# _SessionEventSink — despacho de eventos COM
# --------------------------------------------------------------------------- #
def test_sink_change_emite_acao() -> None:
    capturadas: list[Any] = []
    sink = _SessionEventSink()
    sink._sink = capturadas.append
    comp = FakeComponent(Id="wnd[0]/usr/txt", Type="GuiTextField", Text="abc")
    sink.Change(object(), comp)
    sink.OnChange(object(), comp)  # variante de nome de evento
    assert [a.tipo for a in capturadas] == ["set_text", "set_text"]


def test_sink_sem_callback_e_noop() -> None:
    sink = _SessionEventSink()  # _sink None por padrão
    sink.Change(object(), FakeComponent(Id="x", Type="GuiButton"))  # não deve lançar


def test_sink_ignora_componente_sem_acao() -> None:
    capturadas: list[Any] = []
    sink = _SessionEventSink()
    sink._sink = capturadas.append
    sink.Change(object(), FakeComponent(Id="x", Type="GuiShell"))  # shell → None
    assert capturadas == []


# --------------------------------------------------------------------------- #
# ComRecorder — ciclo de vida (sem COM real)
# --------------------------------------------------------------------------- #
def test_comrecorder_degrada_sem_eventos_com() -> None:
    # Uma sessão falsa não expõe typelib de eventos: WithEvents falha e o
    # recorder fica inativo, sem lançar.
    rec = ComRecorder(FakeComponent(Type="GuiSession"), sink=lambda _a: None)
    rec.start()
    assert rec.is_running is False
    rec.stop()  # idempotente mesmo sem handler
    assert rec.is_running is False

"""Testes do motor de eventos COM (mapeamento componente → ação)."""

from __future__ import annotations

from src.core.recorder_com import acao_from_component
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

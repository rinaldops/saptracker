"""Testes do motor de eventos COM (mapeamento componente → ação)."""

from __future__ import annotations

from typing import Any

import pytest

from src.core.recorder_com import (
    _EVENT_DISPIDS,
    SAP_SESSION_EVENTS_IID,
    ComRecorder,
    _command_lines,
    _DirectSessionEventSink,
    _SessionEventSink,
    acao_from_component,
    acao_from_hit,
    acoes_from_command_array,
)
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


def test_iid_e_dispids_correspondem_a_typelib_sap() -> None:
    assert SAP_SESSION_EVENTS_IID == "{67A71FA4-9381-4061-B3BB-74A545C75874}"
    assert _EVENT_DISPIDS[1280] == "Change"
    assert _EVENT_DISPIDS[1281] == "Hit"
    assert _EVENT_DISPIDS[514] == "StartRequest"


def test_command_array_linha_unica_vira_property_set() -> None:
    comp = FakeComponent(Id="wnd[0]/usr/txtX", Type="GuiTextField")
    actions = acoes_from_command_array(comp, ("SP", "Text", ""))
    assert len(actions) == 1
    assert actions[0].tipo == "property_set"
    assert actions[0].args == {"property": "Text", "value": ""}


def test_command_array_preserva_texto_completo_de_varios_caracteres() -> None:
    """Regressão: o valor string não pode ser quebrado caractere a caractere.

    O ``CommandArray`` do SAP entrega ``("SP", "text", "4900000618")`` — o valor
    é uma string escalar. Tratá-la como coleção COM (com_len/com_item) a
    iterava letra a letra e o gerador pegava só ``"4"``. Veja _as_sequence.
    """
    comp = FakeComponent(Id="wnd[0]/usr/txtMAT_DOC", Type="GuiTextField")
    actions = acoes_from_command_array(comp, ("SP", "text", "4900000618"))
    assert len(actions) == 1
    assert actions[0].tipo == "property_set"
    assert actions[0].args == {"property": "text", "value": "4900000618"}


def test_command_array_descarta_caret_position() -> None:
    """caretPosition é só posição do cursor — inútil para automação, descartado."""
    comp = FakeComponent(Id="wnd[0]/usr/txtX", Type="GuiTextField")
    actions = acoes_from_command_array(comp, ("SP", "caretPosition", "5"))
    assert actions == []


def test_command_array_descarta_caret_position_entre_comandos_validos() -> None:
    comp = FakeComponent(Id="wnd[0]/usr/txtX", Type="GuiTextField")
    commands = (
        ("SP", "text", "ABCDE"),
        ("SP", "caretPosition", "3"),
    )
    actions = acoes_from_command_array(comp, commands)
    assert [a.args.get("property") for a in actions] == ["text"]
    assert actions[0].args["value"] == "ABCDE"


def test_command_array_texto_com_espacos_e_acentos() -> None:
    """Valores textuais com espaços/acentos chegam íntegros (ex.: nome de parceiro)."""
    comp = FakeComponent(Id="wnd[0]/usr/ctxtNAME1", Type="GuiCTextField")
    actions = acoes_from_command_array(comp, ("SP", "text", "BF UTILIDADES DOMESTICAS LTDA"))
    assert len(actions) == 1
    assert actions[0].args["value"] == "BF UTILIDADES DOMESTICAS LTDA"


def test_command_array_multiplas_linhas_preserva_ordem_e_tipos() -> None:
    comp = FakeComponent(Id="wnd[0]/usr/grid", Type="GuiShell")
    commands = (
        ("M", "SetCurrentCell", (4, "PSPID")),
        ("M", "DoubleClickCurrentCell", ()),
    )
    actions = acoes_from_command_array(comp, commands)
    assert [action.tipo for action in actions] == ["method_call", "method_call"]
    assert actions[0].args == {
        "method": "SetCurrentCell",
        "args": [4, "PSPID"],
    }
    assert actions[1].args == {"method": "DoubleClickCurrentCell", "args": []}


def test_command_array_sap_real_usa_argumentos_espalhados_na_linha() -> None:
    comp = FakeComponent(Id="wnd[0]", Type="GuiMainWindow")
    actions = acoes_from_command_array(
        comp,
        (("M", "resizeWorkingPane", 200, 27, False),),
    )
    assert len(actions) == 1
    assert actions[0].args == {
        "method": "resizeWorkingPane",
        "args": [200, 27, False],
    }


def test_command_lines_ignora_formato_desconhecido() -> None:
    assert _command_lines(("x", "y")) == []


def test_command_array_metodo_sem_argumento_e_capturado() -> None:
    """Regressão: ``doubleClickCurrentCell`` (sem args) não pode ser descartado.

    A linha do CommandArray tem 2 elementos ``("M", "nome")``; exigir len>=3
    fazia o duplo-clique em célula de grid sumir do script.
    """
    comp = FakeComponent(Id="wnd[0]/usr/cntlALV/shellcont/shell", Type="GuiShell")
    actions = acoes_from_command_array(comp, ("M", "doubleClickCurrentCell"))
    assert len(actions) == 1
    assert actions[0].tipo == "method_call"
    assert actions[0].args == {"method": "doubleClickCurrentCell", "args": []}


def test_command_array_set_cell_e_double_click_juntos() -> None:
    comp = FakeComponent(Id="wnd[0]/usr/cntlALV/shellcont/shell", Type="GuiShell")
    actions = acoes_from_command_array(
        comp,
        (("M", "setCurrentCell", (2, "POSID")), ("M", "doubleClickCurrentCell")),
    )
    assert [a.args["method"] for a in actions] == ["setCurrentCell", "doubleClickCurrentCell"]
    assert actions[0].args["args"] == [2, "POSID"]
    assert actions[1].args["args"] == []


def test_direct_sink_usa_command_array_sem_duplicar_estado() -> None:
    captured: list[Any] = []
    sink = _DirectSessionEventSink(captured.append)
    comp = FakeComponent(Id="wnd[0]/usr/btn", Type="GuiButton")
    sink.Change(object(), comp, ("M", "Press", ()))
    assert len(captured) == 1
    assert captured[0].tipo == "method_call"
    assert captured[0].args["method"] == "Press"


def test_hit_mapeia_botao_e_celula_grid() -> None:
    button = FakeComponent(Id="wnd[0]/btn", Type="GuiButton")
    assert acao_from_hit(button).tipo == "press"  # type: ignore[union-attr]
    grid = FakeComponent(
        Id="wnd[0]/grid",
        Type="GuiGridView",
        CurrentCellRow=2,
        CurrentCellColumn="MATNR",
    )
    action = acao_from_hit(grid)
    assert action is not None
    assert action.args["row"] == 2
    assert action.args["column"] == "MATNR"


def test_extract_indices_aceita_id_absoluto_e_parent() -> None:
    absolute = FakeComponent(Id="/app/con[3]/ses[2]")
    assert ComRecorder._extract_indices(absolute) == (3, 2)
    relative = FakeComponent(Id="ses[4]", Parent=FakeComponent(Id="con[1]"))
    assert ComRecorder._extract_indices(relative) == (1, 4)


def test_connection_point_direto_aceita_iid_sap() -> None:
    pythoncom = pytest.importorskip("pythoncom")
    pywintypes = pytest.importorskip("pywintypes")
    client_connect = pytest.importorskip("win32com.client.connect")
    client_dynamic = pytest.importorskip("win32com.client.dynamic")
    server_connect = pytest.importorskip("win32com.server.connect")
    server_util = pytest.importorskip("win32com.server.util")
    event_iid = pywintypes.IID(SAP_SESSION_EVENTS_IID)
    received: list[str] = []

    class EventServer(server_connect.ConnectableServer):
        _public_methods_ = ["Fire"] + server_connect.ConnectableServer._public_methods_
        _connect_interfaces_ = [event_iid]

        def Fire(self) -> None:  # noqa: N802 - método COM
            self._BroadcastNotify(
                lambda interface: interface.Invoke(
                    514, 0, pythoncom.DISPATCH_METHOD, 1, None
                ),
                (),
            )

    class EventSink(_DirectSessionEventSink):
        def StartRequest(self, *_args: Any) -> None:  # noqa: N802
            received.append("StartRequest")

    pythoncom.CoInitialize()
    connection = None
    try:
        server = client_dynamic.Dispatch(server_util.wrap(EventServer()))
        sink = EventSink(lambda _action: None)
        connection = client_connect.SimpleConnection(server, sink, event_iid)
        server.Fire()
    finally:
        if connection is not None:
            connection.Disconnect()
        pythoncom.CoUninitialize()
    assert received == ["StartRequest"]


# --------------------------------------------------------------------------- #
# ComRecorder — ciclo de vida (sem COM real)
# --------------------------------------------------------------------------- #
def test_comrecorder_degrada_sem_eventos_com(monkeypatch: Any) -> None:
    # Uma sessão falsa não expõe typelib de eventos: WithEvents falha e o
    # recorder fica inativo, sem lançar.
    def unavailable(recorder: ComRecorder) -> None:
        recorder._ready.set()

    monkeypatch.setattr(ComRecorder, "_run_event_loop", unavailable)
    rec = ComRecorder(FakeComponent(Type="GuiSession"), sink=lambda _a: None)
    rec.start()
    assert rec.is_running is False
    rec.stop()  # idempotente mesmo sem handler
    assert rec.is_running is False

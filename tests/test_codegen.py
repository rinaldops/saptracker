"""Testes dos geradores de código (todas as linguagens registradas)."""

from __future__ import annotations

import pytest

from src.codegen import (
    Acao,
    SessionInfoLite,
    available_generators,
    get_generator,
)

LANGUAGES = [lang for lang, _ in available_generators()]

INFO = SessionInfoLite(
    system="PRD",
    client="100",
    user="TESTUSER",
    transaction="ME23N",
    connection_index=0,
    session_index=0,
)


def _acoes_basicas() -> list[Acao]:
    """Conjunto representativo cobrindo método, propriedade e args."""
    return [
        Acao(tipo="set_text", obj_id="wnd[0]/usr/ctxtRM06E-EVRTN", args={"text": "ME23N"}),
        Acao(tipo="press", obj_id="wnd[0]/tbar[0]/btn[0]"),
        Acao(tipo="send_vkey", obj_id="wnd[0]", args={"vkey": 0}),
        Acao(tipo="set_checkbox", obj_id="wnd[0]/usr/chkX", args={"selected": True}),
    ]


# --------------------------------------------------------------------------- #
# Factory / registry
# --------------------------------------------------------------------------- #
def test_registry_contem_vba_obrigatorio() -> None:
    """VBA é requisito obrigatório de produto: deve estar registrado."""
    assert "vba" in LANGUAGES


def test_vba_aparece_primeiro() -> None:
    """VBA é público prioritário → primeiro no ComboBox."""
    assert LANGUAGES[0] == "vba"


def test_get_generator_desconhecido_levanta() -> None:
    with pytest.raises(KeyError):
        get_generator("cobol")


@pytest.mark.parametrize("lang", LANGUAGES)
def test_metadados_basicos(lang: str) -> None:
    gen = get_generator(lang)
    assert gen.language == lang
    assert gen.display_name
    assert gen.file_extension.startswith(".")


# --------------------------------------------------------------------------- #
# Geração de script completo
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("lang", LANGUAGES)
def test_script_completo_nao_vazio(lang: str) -> None:
    script = get_generator(lang).gerar_script_completo(_acoes_basicas(), INFO)
    assert script.strip()
    assert script.endswith("\n")
    # o id do objeto deve aparecer em alguma referência
    assert "wnd[0]/tbar[0]/btn[0]" in script


@pytest.mark.parametrize("lang", LANGUAGES)
def test_cabecalho_referencia_session(lang: str) -> None:
    cab = get_generator(lang).gerar_cabecalho(INFO)
    assert "SAPGUI" in cab
    assert INFO.transaction in cab


# --------------------------------------------------------------------------- #
# Especificidades por linguagem
# --------------------------------------------------------------------------- #
def test_python_usa_win32com() -> None:
    script = get_generator("python").gerar_script_completo(_acoes_basicas(), INFO)
    assert "import win32com.client" in script
    assert 'session.FindById("wnd[0]/tbar[0]/btn[0]").Press()' in script
    assert '.Text = "ME23N"' in script


def test_vba_envolve_em_sub() -> None:
    script = get_generator("vba").gerar_script_completo(_acoes_basicas(), INFO)
    assert "Sub SAP_Macro()" in script
    assert "End Sub" in script
    assert "GetObject(\"SAPGUI\")" in script
    # família VB: chamada de método SEM parênteses
    assert 'session.FindById("wnd[0]/tbar[0]/btn[0]").Press' in script
    assert ".Press()" not in script
    # send_vkey com argumento, sem parênteses
    assert '.SendVKey 0' in script


def test_vbscript_usa_set() -> None:
    script = get_generator("vbscript").gerar_script_completo(_acoes_basicas(), INFO)
    assert "Set session = connection.Children(0)" in script
    assert ".Press()" not in script


def test_powershell_dollar_session_e_bool() -> None:
    acoes = [Acao(tipo="set_checkbox", obj_id="wnd[0]/usr/chkX", args={"selected": True})]
    script = get_generator("powershell").gerar_script_completo(acoes, INFO)
    assert "$session" in script
    assert "$true" in script
    assert "GetActiveObject" in script


def test_autoit_objget_e_comentario() -> None:
    script = get_generator("autoit").gerar_script_completo(_acoes_basicas(), INFO)
    assert 'ObjGet("SAPGUI")' in script
    assert script.splitlines()[0].startswith(";")
    assert '.Press()' in script  # AutoIt usa parênteses


def test_java_usa_dispatch() -> None:
    script = get_generator("java").gerar_script_completo(_acoes_basicas(), INFO)
    assert "import com.jacob" in script
    assert "Dispatch.call(" in script
    assert "Dispatch.put(" in script
    assert script.rstrip().endswith("}")
    # método em camelCase no Jacob
    assert '"press"' in script


# --------------------------------------------------------------------------- #
# Escape de strings
# --------------------------------------------------------------------------- #
def test_escape_aspas_vb() -> None:
    acoes = [Acao(tipo="set_text", obj_id="f", args={"text": 'a"b'})]
    script = get_generator("vba").gerar_script_completo(acoes, INFO)
    assert '"a""b"' in script  # VB dobra a aspa


def test_escape_aspas_python() -> None:
    acoes = [Acao(tipo="set_text", obj_id="f", args={"text": 'a"b'})]
    script = get_generator("python").gerar_script_completo(acoes, INFO)
    assert '"a\\"b"' in script  # Python escapa com barra


def test_escape_aspa_simples_powershell() -> None:
    acoes = [Acao(tipo="set_text", obj_id="f", args={"text": "a'b"})]
    script = get_generator("powershell").gerar_script_completo(acoes, INFO)
    assert "'a''b'" in script  # PS dobra a aspa simples


# --------------------------------------------------------------------------- #
# Win32 dialog
# --------------------------------------------------------------------------- #
WIN32_ACAO = Acao(
    tipo="win32_dialog",
    origem="win32",
    args={
        "title": "Salvar como",
        "class": "#32770",
        "controls": [{"control": "Edit1", "text": "C:\\saida.txt"}],
        "button": "Button2",
        "timeout": 15,
    },
)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_win32_dialog_gera_algo(lang: str) -> None:
    """Cada linguagem deve produzir alguma linha para o diálogo (nunca crash)."""
    script = get_generator(lang).gerar_script_completo([WIN32_ACAO], INFO)
    assert "Salvar como" in script


def test_win32_autoit_nativo() -> None:
    script = get_generator("autoit").gerar_script_completo([WIN32_ACAO], INFO)
    assert 'WinWait("Salvar como", "", 15)' in script
    assert "ControlSetText" in script
    assert "ControlClick" in script


def test_win32_python_pyautoit() -> None:
    script = get_generator("python").gerar_script_completo([WIN32_ACAO], INFO)
    assert "import autoit" in script
    assert "win_wait" in script

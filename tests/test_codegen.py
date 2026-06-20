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


# --------------------------------------------------------------------------- #
# Dedup de ações redundantes adjacentes (artefato do duplo evento Change)
# --------------------------------------------------------------------------- #
def test_dedupe_colapsa_property_set_e_set_combo_key_equivalentes() -> None:
    from src.codegen.instructions import dedupe_consecutive

    oid = "wnd[0]/usr/cmbACTION"
    acoes = [
        Acao(tipo="set_combo_key", obj_id=oid, args={"key": "A08"}),  # fallback
        # property_set vindo do CommandArray (mesmo efeito)
        Acao(tipo="property_set", obj_id=oid, args={"property": "key", "value": "A08"}),
    ]
    out = dedupe_consecutive(acoes)
    assert len(out) == 1
    assert out[0].tipo == "set_combo_key"


def test_dedupe_colapsa_text_e_checkbox_equivalentes() -> None:
    from src.codegen.instructions import dedupe_consecutive

    txt = "wnd[0]/usr/txtX"
    chk = "wnd[0]/usr/chkY"
    acoes = [
        Acao(tipo="property_set", obj_id=txt, args={"property": "text", "value": "4900000618"}),
        Acao(tipo="set_text", obj_id=txt, args={"text": "4900000618"}),
        Acao(tipo="set_checkbox", obj_id=chk, args={"selected": True}),
        Acao(tipo="property_set", obj_id=chk, args={"property": "selected", "value": True}),
    ]
    out = dedupe_consecutive(acoes)
    assert [a.obj_id for a in out] == [txt, chk]


def test_dedupe_preserva_valores_diferentes() -> None:
    from src.codegen.instructions import dedupe_consecutive

    oid = "wnd[0]/usr/txtX"
    acoes = [
        Acao(tipo="set_text", obj_id=oid, args={"text": "A"}),
        Acao(tipo="set_text", obj_id=oid, args={"text": "AB"}),
    ]
    assert len(dedupe_consecutive(acoes)) == 2


def test_dedupe_nao_colapsa_reedicao_separada_por_outra_acao() -> None:
    from src.codegen.instructions import dedupe_consecutive

    oid = "wnd[0]/usr/txtX"
    acoes = [
        Acao(tipo="set_text", obj_id=oid, args={"text": "X"}),
        Acao(tipo="send_vkey", obj_id="wnd[0]", args={"vkey": 0}),
        Acao(tipo="set_text", obj_id=oid, args={"text": "X"}),
    ]
    assert len(dedupe_consecutive(acoes)) == 3


def test_dedupe_nao_colapsa_press_repetido() -> None:
    from src.codegen.instructions import dedupe_consecutive

    oid = "wnd[0]/tbar[0]/btn[0]"
    acoes = [Acao(tipo="press", obj_id=oid), Acao(tipo="press", obj_id=oid)]
    assert len(dedupe_consecutive(acoes)) == 2


def test_script_completo_aplica_dedup_no_vba() -> None:
    oid = "wnd[0]/usr/cmbACTION"
    acoes = [
        Acao(tipo="set_combo_key", obj_id=oid, args={"key": "A08"}),
        Acao(tipo="property_set", obj_id=oid, args={"property": "key", "value": "A08"}),
    ]
    script = get_generator("vba").gerar_script_completo(acoes, INFO)
    assert script.count('cmbACTION") = "A08"') + script.count('cmbACTION").Key = "A08"') == 1


# --------------------------------------------------------------------------- #
# Comentários de contexto (navegação de transação, aba, menu)
# --------------------------------------------------------------------------- #
def test_comentario_navegacao_transacao_via_property_set() -> None:
    from src.codegen.instructions import _context_comment

    acao = Acao(tipo="property_set", obj_id="wnd[0]/tbar[0]/okcd",
                args={"property": "text", "value": "/nMIGO"})
    c = _context_comment(acao)
    assert c is not None and c.text == "NAVEGANDO para a transação: MIGO"


def test_comentario_navegacao_transacao_via_set_text_e_bare() -> None:
    from src.codegen.instructions import _context_comment, _parse_transaction

    acao = Acao(tipo="set_text", obj_id="wnd[0]/tbar[0]/okcd", args={"text": "cn43n"})
    c = _context_comment(acao)
    assert c is not None and c.text == "NAVEGANDO para a transação: CN43N"
    assert _parse_transaction("/oVA01") == "VA01"
    assert _parse_transaction("/n") is None       # volta ao menu → sem comentário
    assert _parse_transaction("=POST") is None     # função, não transação
    assert _parse_transaction("/nend") is None     # comando de sistema


def test_comentario_selecao_aba_usa_label_ou_id() -> None:
    from src.codegen.instructions import _context_comment

    com_label = Acao(tipo="select", obj_id="wnd[0]/usr/tabsTS/tabpQTD", label="Quantidades")
    assert _context_comment(com_label).text == "SELEÇÃO de aba: Quantidades"  # type: ignore[union-attr]
    sem_label = Acao(tipo="select", obj_id="wnd[0]/usr/tabsTS/tabpOK_GOITEM_QTD")
    assert _context_comment(sem_label).text == "SELEÇÃO de aba: OK_GOITEM_QTD"  # type: ignore[union-attr]


def test_comentario_selecao_menu() -> None:
    from src.codegen.instructions import _context_comment

    acao = Acao(tipo="select", obj_id="wnd[0]/mbar/menu[3]/menu[1]", label="Criar")
    assert _context_comment(acao).text == "SELEÇÃO de item de Menu: Criar"  # type: ignore[union-attr]


def test_radio_e_botao_nao_geram_comentario_de_contexto() -> None:
    from src.codegen.instructions import _context_comment

    assert _context_comment(Acao(tipo="select", obj_id="wnd[0]/usr/radX")) is None
    assert _context_comment(Acao(tipo="press", obj_id="wnd[0]/tbar[0]/btn[0]")) is None


def test_comentario_contexto_aparece_no_script_gerado() -> None:
    acoes = [
        Acao(tipo="property_set", obj_id="wnd[0]/tbar[0]/okcd",
             args={"property": "text", "value": "/nME23N"}),
    ]
    script = get_generator("vba").gerar_script_completo(acoes, INFO)
    assert "' NAVEGANDO para a transação: ME23N" in script


# --------------------------------------------------------------------------- #
# IDs relativos a wnd[N] (como o gravador nativo do SAP)
# --------------------------------------------------------------------------- #
def test_relative_id_remove_prefixo_da_sessao() -> None:
    from src.codegen.instructions import relative_id

    assert relative_id("/app/con[0]/ses[0]/wnd[0]/tbar[0]/okcd") == "wnd[0]/tbar[0]/okcd"
    assert relative_id("/app/con[2]/ses[3]/wnd[1]/usr/txtX") == "wnd[1]/usr/txtX"
    assert relative_id("wnd[0]/usr/txtX") == "wnd[0]/usr/txtX"  # já relativo
    assert relative_id("") == ""


def test_script_gerado_usa_ids_relativos() -> None:
    acoes = [
        Acao(tipo="set_text", obj_id="/app/con[0]/ses[0]/wnd[0]/usr/txtX", args={"text": "v"}),
        Acao(tipo="press", obj_id="/app/con[0]/ses[0]/wnd[1]/tbar[0]/btn[0]"),
    ]
    script = get_generator("vba").gerar_script_completo(acoes, INFO)
    assert 'FindById("wnd[0]/usr/txtX")' in script
    assert 'FindById("wnd[1]/tbar[0]/btn[0]")' in script
    assert "/app/con[0]/ses[0]" not in script

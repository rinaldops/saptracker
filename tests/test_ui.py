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

from PyQt6.QtCore import Qt  # noqa: E402

from src.codegen import Acao  # noqa: E402
from src.core.sap_connection import SessionInfo  # noqa: E402
from src.ui.code_editor import CodeEditor  # noqa: E402
from src.ui.context import AppContext  # noqa: E402
from src.ui.main_window import MainWindow  # noqa: E402
from tests.conftest import FakeSession  # noqa: E402


@pytest.fixture
def janela(qtbot):  # type: ignore[no-untyped-def]
    win = MainWindow()
    qtbot.addWidget(win)
    return win


def test_abas(janela) -> None:  # type: ignore[no-untyped-def]
    titulos = [janela.tabs.tabText(i) for i in range(janela.tabs.count())]
    assert titulos == [
        "Conexão",
        "Analisador",
        "Gravador",
        "Código",
        "Referência da API",
        "Notas",
    ]


def test_notas_roundtrip(janela) -> None:  # type: ignore[no-untyped-def]
    aba = janela.notes_tab
    aba.set_text("wnd[0]/usr/txt — lembrete")
    assert aba.text() == "wnd[0]/usr/txt — lembrete"


def test_api_ref_filtra(janela) -> None:  # type: ignore[no-untyped-def]
    aba = janela.api_ref_tab
    total = aba.lista.count()
    assert total >= 5  # referência embutida não-vazia
    aba.search.setText("GridView")
    nomes = [aba.lista.item(i).text() for i in range(aba.lista.count())]
    assert nomes == ["GuiGridView"]
    assert "RowCount" in aba.detalhe.toPlainText()
    # Limpar o filtro restaura a lista completa.
    aba.search.setText("")
    assert aba.lista.count() == total


def test_api_ref_inclui_novos_objetos_e_multiplos_exemplos(janela) -> None:  # type: ignore[no-untyped-def]
    aba = janela.api_ref_tab
    nomes = {aba.lista.item(i).text() for i in range(aba.lista.count())}
    # Objetos adicionados na expansão da referência.
    for esperado in ("GuiComboBox", "GuiOkCodeField", "GuiSessionInfo", "GuiCalendar"):
        assert esperado in nomes
    # Filtrar ComboBox mostra o objeto e seus exemplos rotulados.
    aba.search.setText("ComboBox")
    assert [aba.lista.item(i).text() for i in range(aba.lista.count())] == ["GuiComboBox"]
    detalhe = aba.detalhe.toPlainText()
    assert "Exemplos" in detalhe
    assert "Selecionar por chave" in detalhe and "Ler valor exibido" in detalhe


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


def test_atalho_refresh_traz_analyser(janela, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    chamado: list[bool] = []
    monkeypatch.setattr(janela.analyser_tab, "analyse", lambda: chamado.append(True))
    janela.refresh_tree()
    assert chamado == [True]
    assert janela.tabs.currentWidget() is janela.analyser_tab


def test_atalho_gravacao_respeita_estado(janela, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    chamadas: list[str] = []
    monkeypatch.setattr(janela.ctx, "start_recording", lambda: chamadas.append("start"))
    monkeypatch.setattr(janela.ctx, "stop_recording", lambda: chamadas.append("stop"))
    # Sem recorder, is_recording é False: F9 inicia, Shift+F9 é no-op.
    janela.start_recording()
    janela.stop_recording()
    assert chamadas == ["start"]


def test_context_start_recording_sem_sessao_falha() -> None:
    ctx = AppContext()
    assert ctx.start_recording() is False
    assert not ctx.is_recording


class _FakeAnalyser:
    """Analisador falso: árvore pronta + registro de chamadas de highlight."""

    def __init__(self, root, on_build=None) -> None:  # type: ignore[no-untyped-def]
        self._root = root
        self._on_build = on_build
        self.highlights: list[tuple[str, bool]] = []
        self.select_nodes: list[tuple[str, str]] = []

    def build_tree(self, progress_callback=None):  # type: ignore[no-untyped-def]
        if progress_callback is not None:
            progress_callback(0, 3)
            progress_callback(1, 3)
        if self._on_build is not None:
            self._on_build()
        if progress_callback is not None:
            progress_callback(3, 3)
        return self._root

    def inspect(self, obj_id: str) -> dict:
        return {"id": obj_id}

    def highlight(self, obj_id: str, *, on: bool = True) -> bool:
        self.highlights.append((obj_id, on))
        return True

    def select_node(self, obj_id: str, key: str) -> bool:
        self.select_nodes.append((obj_id, key))
        return True


def _arvore_exemplo():  # type: ignore[no-untyped-def]
    from src.core.analyser import ObjectNode

    return ObjectNode(
        id="r",
        type="GuiSession",
        children=[
            ObjectNode(id="a", type="GuiButton", name="BTN_SAVE", text="Salvar"),
            ObjectNode(id="b", type="GuiLabel", text="Salvar como"),
        ],
    )


def _preparar_analyser_tab(janela, fake):  # type: ignore[no-untyped-def]
    aba = janela.analyser_tab
    janela.ctx.session = object()  # has_session True, sem disparar sessionChanged
    aba._analyser = fake
    aba.analyse()
    return aba


def test_highlight_e_removido_ao_soltar_botao_direito(janela, qtbot) -> None:  # type: ignore[no-untyped-def]
    fake = _FakeAnalyser(_arvore_exemplo())
    aba = _preparar_analyser_tab(janela, fake)
    raiz = aba.tree.topLevelItem(0)
    item_a = raiz.child(0)
    item_b = raiz.child(1)
    aba.tree.expandAll()
    aba.tree.doItemsLayout()

    posicao_a = aba.tree.visualItemRect(item_a).center()
    qtbot.mousePress(aba.tree.viewport(), Qt.MouseButton.RightButton, pos=posicao_a)
    assert aba.tree.currentItem() is item_a
    assert fake.highlights == [("a", True)]
    qtbot.mouseRelease(aba.tree.viewport(), Qt.MouseButton.RightButton, pos=posicao_a)
    assert fake.highlights == [("a", True), ("a", False)]

    posicao_b = aba.tree.visualItemRect(item_b).center()
    qtbot.mousePress(aba.tree.viewport(), Qt.MouseButton.RightButton, pos=posicao_b)
    qtbot.mouseRelease(aba.tree.viewport(), Qt.MouseButton.RightButton, pos=posicao_b)
    assert fake.highlights[-1] == ("b", False)
    assert aba._highlighted_id == ""
    assert not hasattr(aba, "btn_highlight")
    assert not hasattr(aba, "btn_clear_highlight")
    # Nenhum dos dois é GuiTreeNode: select_node nunca é chamado.
    assert fake.select_nodes == []


def test_destaque_em_no_de_tree_tambem_seleciona_no_real(janela, qtbot) -> None:  # type: ignore[no-untyped-def]
    """Destacar um GuiTreeNode sintético também chama SelectNode (via select_node)."""
    from src.core.analyser import ObjectNode

    arvore = ObjectNode(
        id="r",
        type="GuiSession",
        children=[
            ObjectNode(id="shell1", type="GuiTreeNode", name="000013", text="000013: Ferragem"),
        ],
    )
    fake = _FakeAnalyser(arvore)
    aba = _preparar_analyser_tab(janela, fake)
    raiz = aba.tree.topLevelItem(0)
    item_no = raiz.child(0)
    aba.tree.expandAll()
    aba.tree.doItemsLayout()

    posicao = aba.tree.visualItemRect(item_no).center()
    qtbot.mousePress(aba.tree.viewport(), Qt.MouseButton.RightButton, pos=posicao)

    assert fake.highlights == [("shell1", True)]
    assert fake.select_nodes == [("shell1", "000013")]


def test_colunas_do_analisador_iniciam_em_dois_tercos(janela) -> None:  # type: ignore[no-untyped-def]
    aba = janela.analyser_tab
    aba.tree.resize(600, 400)
    aba._column_widths_initialized = False
    aba._set_initial_column_widths()
    total = aba.tree.viewport().width()
    assert abs((aba.tree.columnWidth(0) / total) - (2 / 3)) < 0.02
    assert aba.tree.columnWidth(1) == total - aba.tree.columnWidth(0)


def test_busca_cicla_pelos_resultados(janela) -> None:  # type: ignore[no-untyped-def]
    fake = _FakeAnalyser(_arvore_exemplo())
    aba = _preparar_analyser_tab(janela, fake)

    aba.search.setText("salvar")
    aba.find_next()
    primeiro = aba.tree.currentItem()
    aba.find_next()
    segundo = aba.tree.currentItem()
    assert primeiro is not segundo  # dois resultados distintos
    aba.find_next()
    assert aba.tree.currentItem() is primeiro  # cicla de volta ao início


def test_busca_sem_resultado_nao_quebra(janela) -> None:  # type: ignore[no-untyped-def]
    fake = _FakeAnalyser(_arvore_exemplo())
    aba = _preparar_analyser_tab(janela, fake)
    aba.search.setText("inexistente-xyz")
    aba.find_next()
    assert aba.tree.currentItem() is None


def test_busca_considera_nome_nao_exibido(janela) -> None:  # type: ignore[no-untyped-def]
    fake = _FakeAnalyser(_arvore_exemplo())
    aba = _preparar_analyser_tab(janela, fake)
    aba.search.setText("btn_save")
    aba.find_next()
    assert aba.tree.currentItem().data(0, Qt.ItemDataRole.UserRole) == "a"


def test_analyse_exibe_estado_de_processamento(janela) -> None:  # type: ignore[no-untyped-def]
    estados: list[tuple[bool, bool, str]] = []
    aba = janela.analyser_tab
    fake = _FakeAnalyser(
        _arvore_exemplo(),
        lambda: estados.append(
            (
                not aba.analysis_status.isHidden(),
                not aba.analysis_progress.isHidden(),
                aba.btn_analyse.text(),
            )
        ),
    )
    _preparar_analyser_tab(janela, fake)
    assert estados == [(True, True, "Analisando…")]
    assert not aba.analysis_status.isVisible()
    assert not aba.analysis_progress.isVisible()
    assert aba.btn_analyse.text() == "Analisar sessão"


class _FakeConnection:
    def __init__(self) -> None:
        self.session = FakeSession()

    def ensure_connected(self) -> None:
        return None

    def list_sessions_info(self):  # type: ignore[no-untyped-def]
        return [SessionInfo(0, 0, "PRD", "100", "TESTER", "SE16", "Consulta")]

    def get_session(self, connection_index: int, session_index: int):  # type: ignore[no-untyped-def]
        assert (connection_index, session_index) == (0, 0)
        return self.session


def test_conexao_lista_e_marca_sessao_ativa(qtbot) -> None:  # type: ignore[no-untyped-def]
    conexao = _FakeConnection()
    win = MainWindow(connection=conexao)
    qtbot.addWidget(win)
    win.connection_tab.refresh_sessions()
    assert win.ctx.session is conexao.session
    assert "CONECTADO" in win.connection_tab.lista.item(0).text()
    assert win.connection_tab.status.text().startswith("Conectado:")

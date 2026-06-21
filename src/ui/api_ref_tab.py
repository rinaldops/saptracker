"""Aba API Reference — referência rápida da API SAP GUI Scripting.

Lista pesquisável dos objetos COM mais usados (``GuiApplication``,
``GuiSession``, ``GuiGridView``, ``GuiTree`` …) com seus métodos e propriedades
principais e um exemplo. Os dados são estáticos (não dependem de conexão SAP) e
servem de consulta enquanto se escreve ou se lê um script gerado.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from src.ui.context import AppContext
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ApiEntry:
    """Uma entrada da referência: um objeto SAP e seus membros."""

    name: str
    summary: str
    members: list[tuple[str, str]] = field(default_factory=list)
    #: Lista de ``(rótulo, código)``. Vários exemplos por objeto.
    examples: list[tuple[str, str]] = field(default_factory=list)

    def matches(self, termo: str) -> bool:
        """Indica se o termo (case-insensitive) ocorre no nome ou nos membros."""
        t = termo.lower()
        if t in self.name.lower() or t in self.summary.lower():
            return True
        return any(t in m.lower() or t in d.lower() for m, d in self.members)

    def to_html(self) -> str:
        """Renderiza a entrada como HTML para o painel de detalhes."""
        e = html.escape
        linhas = [f"<h2>{e(self.name)}</h2>", f"<p>{e(self.summary)}</p>"]
        if self.members:
            linhas.append("<h3>Membros principais</h3><ul>")
            linhas += [
                f"<li><b>{e(nome)}</b> — {e(desc)}</li>" for nome, desc in self.members
            ]
            linhas.append("</ul>")
        if self.examples:
            linhas.append("<h3>Exemplos</h3>")
            for rotulo, codigo in self.examples:
                if rotulo:
                    linhas.append(f"<p><b>{e(rotulo)}</b></p>")
                linhas.append(f"<pre>{e(codigo)}</pre>")
        return "".join(linhas)


#: Referência embutida dos objetos SAP GUI Scripting mais frequentes.
API_REFERENCE: list[ApiEntry] = [
    ApiEntry(
        name="GuiApplication",
        summary="Raiz do modelo de objetos. Obtida do Scripting Engine.",
        members=[
            ("Children", "Coleção de GuiConnection abertas."),
            ("OpenConnection(desc)", "Abre uma nova conexão pelo nome do sistema."),
            ("ActiveSession", "Sessão atualmente em foco."),
        ],
        examples=[
            (
                "Obter o engine",
                'sap_gui = win32com.client.GetObject("SAPGUI").GetScriptingEngine\n'
                "app = sap_gui  # GuiApplication",
            ),
            ("Sessão em foco", "sess = app.ActiveSession"),
        ],
    ),
    ApiEntry(
        name="GuiConnection",
        summary="Representa uma conexão a um sistema SAP; contém sessões.",
        members=[
            ("Children", "Coleção de GuiSession da conexão."),
            ("Description", "Nome/descrição da conexão."),
            ("CloseConnection()", "Encerra a conexão."),
        ],
        examples=[
            ("Primeira conexão/sessão", "conn = app.Children(0)\nsession = conn.Children(0)"),
        ],
    ),
    ApiEntry(
        name="GuiSession",
        summary="Uma sessão (janela) SAP. Ponto de entrada para FindById.",
        members=[
            ("FindById(id)", "Localiza um objeto pelo ID completo."),
            ("FindById(id, False)", "Idem, mas retorna None se não existir (tolerante)."),
            ("StartTransaction(tcode)", "Executa uma transação."),
            ("EndTransaction()", "Encerra a transação atual."),
            ("ActiveWindow", "Janela ativa (GuiMainWindow/GuiModalWindow)."),
            ("Info", "GuiSessionInfo: sistema, cliente, usuário, transação."),
        ],
        examples=[
            (
                "Preencher campo e confirmar",
                'session.FindById("wnd[0]/usr/txtRSYST-BNAME").Text = "USUARIO"\n'
                'session.FindById("wnd[0]").sendVKey(0)',
            ),
            (
                "Busca tolerante (não lança)",
                'obj = session.FindById("wnd[0]/usr/txtX", False)\n'
                "if obj is not None:\n    obj.Text = \"valor\"",
            ),
        ],
    ),
    ApiEntry(
        name="GuiTextField / GuiCTextField",
        summary="Campos de texto editáveis da tela (entrada de dados).",
        members=[
            ("Text", "Conteúdo do campo (leitura/escrita)."),
            ("SetFocus()", "Coloca o cursor no campo."),
            ("CaretPosition", "Posição do cursor no campo."),
            ("Changeable", "False se o campo é somente-leitura."),
        ],
        examples=[
            ("Escrever", 'session.FindById("wnd[0]/usr/ctxtVBAK-VBELN").Text = "1000"'),
            ("Ler", 'v = session.FindById("wnd[0]/usr/ctxtVBAK-VBELN").Text'),
        ],
    ),
    ApiEntry(
        name="GuiButton",
        summary="Botão de tela. Acionado por Press.",
        members=[("Press()", "Aciona o botão.")],
        examples=[
            ("Botão da toolbar", 'session.FindById("wnd[0]/tbar[0]/btn[11]").Press()'),
            ("Botão na tela", 'session.FindById("wnd[0]/usr/btnEXEC").Press()'),
        ],
    ),
    ApiEntry(
        name="GuiMainWindow / GuiModalWindow",
        summary="Janelas SAP. sendVKey simula teclas de função.",
        members=[
            ("sendVKey(n)", "Envia uma VKey (0=Enter, 8=F8, 11=Salvar…)."),
            ("Text", "Título da janela."),
            ("Close()", "Fecha janelas modais."),
        ],
        examples=[
            (
                "Enter e F-keys",
                'session.FindById("wnd[0]").sendVKey(0)   # Enter\n'
                'session.FindById("wnd[0]").sendVKey(8)   # F8 (executar)\n'
                'session.FindById("wnd[0]").sendVKey(11)  # Salvar',
            ),
            ("Confirmar um popup modal", 'session.FindById("wnd[1]/tbar[0]/btn[0]").Press()'),
        ],
    ),
    ApiEntry(
        name="GuiOkCodeField",
        summary="Campo de comando (okcd) na barra — entrada de transações e funções.",
        members=[
            ("Text", "Código a executar (ex.: '/nME23N', '=POST')."),
            ("Opened", "True quando o campo está visível/aberto."),
        ],
        examples=[
            (
                "Navegar para transação",
                'session.FindById("wnd[0]/tbar[0]/okcd").Text = "/nME23N"\n'
                'session.FindById("wnd[0]").sendVKey(0)',
            ),
            (
                "Comando dentro da tela",
                'session.FindById("wnd[0]/tbar[0]/okcd").Text = "=POST"\n'
                'session.FindById("wnd[0]").sendVKey(0)',
            ),
        ],
    ),
    ApiEntry(
        name="GuiComboBox",
        summary="Lista suspensa. Selecione pela CHAVE (Key), não pelo texto.",
        members=[
            ("Key", "Chave da opção selecionada (leitura/escrita)."),
            ("Value", "Texto exibido da opção atual."),
            ("Entries", "Coleção de opções (cada uma com Key e Value)."),
        ],
        examples=[
            ("Selecionar por chave", 'session.FindById("wnd[0]/usr/cmbRF05A-NEWBS").Key = "40"'),
            ("Ler valor exibido", 'v = session.FindById("wnd[0]/usr/cmbXXX").Value'),
        ],
    ),
    ApiEntry(
        name="GuiCheckBox",
        summary="Caixa de marcação. Estado em Selected (booleano).",
        members=[("Selected", "True/False (leitura/escrita).")],
        examples=[
            ("Marcar", 'session.FindById("wnd[0]/usr/chkRF05A-XPOS1").Selected = True'),
        ],
    ),
    ApiEntry(
        name="GuiRadioButton",
        summary="Botão de opção. Selecionado via Select(); estado em Selected.",
        members=[
            ("Select()", "Seleciona este botão do grupo."),
            ("Selected", "True se está selecionado (leitura)."),
        ],
        examples=[
            ("Selecionar opção", 'session.FindById("wnd[0]/usr/radRB_OPT1").Select()'),
        ],
    ),
    ApiEntry(
        name="GuiTab / GuiTabStrip",
        summary="Abas de uma tela. GuiTab é uma aba; GuiTabStrip é o conjunto.",
        members=[
            ("Select()", "(GuiTab) Ativa esta aba."),
            ("SelectedTab", "(GuiTabStrip) Aba atualmente ativa."),
        ],
        examples=[
            (
                "Trocar de aba",
                'session.FindById("wnd[0]/usr/tabsTS_GOITEM/tabpOK_GOITEM_QUANTITIES").Select()',
            ),
        ],
    ),
    ApiEntry(
        name="GuiCalendar",
        summary="Controle de calendário (GuiShell). Datas no formato AAAAMMDD.",
        members=[
            ("selectionInterval", "Intervalo selecionado ('AAAAMMDD,AAAAMMDD')."),
            ("focusDate", "Data com foco."),
            ("firstVisibleDate / lastVisibleDate", "Faixa visível."),
        ],
        examples=[
            (
                "Selecionar intervalo",
                'cal = session.FindById("wnd[0]/usr/cntlCAL/shellcont/shell")\n'
                'cal.selectionInterval = "20260101,20260131"',
            ),
        ],
    ),
    ApiEntry(
        name="GuiToolbarControl",
        summary="Barra de botões de um GuiShell (acima de grids/árvores).",
        members=[
            ("PressButton(id)", "Aciona um botão da toolbar pelo ID/função."),
            ("PressContextButton(id)", "Abre o menu de contexto de um botão."),
            ("ButtonCount", "Quantidade de botões."),
        ],
        examples=[
            (
                "Acionar botão da toolbar",
                'tb = session.FindById("wnd[0]/usr/cntlX/shellcont/shell")\n'
                'tb.PressButton("ABLM")',
            ),
        ],
    ),
    ApiEntry(
        name="GuiPasswordField",
        summary="Campo de senha (texto mascarado), ex.: tela de logon.",
        members=[
            ("Text", "Escreve a senha. A leitura retorna vazio (segurança)."),
        ],
        examples=[
            (
                "Preencher senha (evite hard-code)",
                'session.FindById("wnd[0]/usr/pwdRSYST-BCODE").Text = senha',
            ),
        ],
    ),
    ApiEntry(
        name="GuiMenu",
        summary="Item da barra de menus (mbar). Acionado por Select().",
        members=[
            ("Select()", "Aciona o item de menu."),
            ("Text", "Rótulo visível do item."),
        ],
        examples=[
            ("Acionar item de menu", 'session.FindById("wnd[0]/mbar/menu[0]/menu[1]").Select()'),
        ],
    ),
    ApiEntry(
        name="GuiGridView",
        summary="ALV Grid (GuiShell). Sem eventos COM — requer polling.",
        members=[
            ("RowCount", "Número de linhas."),
            ("GetColumnNames()", "Coleção com os nomes técnicos das colunas."),
            ("GetCellValue(row, col)", "Valor de uma célula."),
            ("SetCurrentCell(row, col)", "Define a célula atual."),
            ("SelectedRows", "Linhas selecionadas (string '0,1,2')."),
            ("DoubleClickCurrentCell()", "Duplo-clique na célula atual."),
            ("PressButton(id)", "Aciona um botão da toolbar do grid."),
        ],
        examples=[
            (
                "Selecionar célula e linha",
                'grid = session.FindById("wnd[0]/usr/cntlGRID1/shellcont/shell")\n'
                'grid.SetCurrentCell(2, "MATNR")\n'
                'grid.SelectedRows = "2"',
            ),
            (
                "Ler valores",
                "n = grid.RowCount\n"
                'val = grid.GetCellValue(0, "MATNR")',
            ),
            ("Duplo-clique / botão", 'grid.DoubleClickCurrentCell()\ngrid.PressButton("&FILTER")'),
        ],
    ),
    ApiEntry(
        name="GuiTree",
        summary="Árvore (GuiShell). SelectNode dispara a navegação.",
        members=[
            ("GetAllNodeKeys()", "Chaves dos nós CARREGADOS (lazy-load!)."),
            ("GetNodeTextByKey(key)", "Texto de um nó."),
            ("SelectNode(key)", "Seleciona um nó pela chave."),
            ("ExpandNode(key)", "Expande um nó."),
            ("GetSubNodesCol(key)", "Coleção de chaves filhas."),
        ],
        examples=[
            (
                "Selecionar e expandir nó",
                'tree = session.FindById("wnd[0]/usr/cntlTREE/shellcont/shell")\n'
                'tree.SelectNode("000042")\n'
                'tree.ExpandNode("000001")',
            ),
            (
                "Percorrer nós carregados",
                "for k in tree.GetAllNodeKeys():\n    print(k, tree.GetNodeTextByKey(k))",
            ),
        ],
    ),
    ApiEntry(
        name="GuiTextEdit",
        summary="Editor de texto multilinha (GuiShell).",
        members=[
            ("Text", "Conteúdo completo."),
            ("LineCount", "Número de linhas."),
            ("FirstVisibleLine", "Primeira linha visível."),
            ("SetSelectionIndexes(a, b)", "Define a seleção."),
        ],
        examples=[
            (
                "Ler conteúdo",
                'edit = session.FindById(".../shell")\ntexto = edit.Text\nn = edit.LineCount',
            ),
        ],
    ),
    ApiEntry(
        name="GuiLabel",
        summary="Rótulo/texto de tela (não editável). Útil para ler valores exibidos.",
        members=[
            ("Text", "Texto exibido."),
            ("Changeable", "Geralmente False (somente leitura)."),
        ],
        examples=[
            ("Ler um rótulo", 'txt = session.FindById("wnd[0]/usr/lbl[6,3]").Text'),
        ],
    ),
    ApiEntry(
        name="GuiStatusbar",
        summary="Barra de status — mensagens de retorno da transação.",
        members=[
            ("MessageType", "Tipo: S (sucesso), E (erro), W (aviso)…"),
            ("Text", "Texto da mensagem."),
            ("MessageId / MessageNumber", "Classe e número da mensagem."),
        ],
        examples=[
            (
                "Verificar retorno",
                'sbar = session.FindById("wnd[0]/sbar")\n'
                'if sbar.MessageType == "E":\n'
                "    raise Exception(sbar.Text)",
            ),
        ],
    ),
    ApiEntry(
        name="GuiSessionInfo",
        summary="Metadados da sessão (session.Info). Somente leitura.",
        members=[
            ("Transaction", "Transação atual (ex.: 'ME23N')."),
            ("Program", "Programa ABAP da tela atual."),
            ("User / Client", "Usuário e mandante."),
            ("SystemName", "Nome do sistema (ex.: 'S4H')."),
            ("ScreenNumber", "Número da dynpro atual."),
        ],
        examples=[
            (
                "Ler contexto da sessão",
                "info = session.Info\n"
                "tcode = info.Transaction\n"
                "usuario = info.User",
            ),
        ],
    ),
]


class ApiRefTab(QWidget):
    """Referência pesquisável da API SAP GUI Scripting."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._entries = API_REFERENCE
        self._build_ui()
        self._populate("")

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        topo = QHBoxLayout()
        titulo = QLabel("Referência da API")
        titulo.setObjectName("title")
        topo.addWidget(titulo)
        topo.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filtrar objetos e membros…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._populate)
        self.search.setMinimumWidth(280)
        topo.addWidget(self.search)
        layout.addLayout(topo)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.lista = QListWidget()
        self.lista.currentItemChanged.connect(self._on_select)
        splitter.addWidget(self.lista)

        self.detalhe = QTextBrowser()
        self.detalhe.setOpenExternalLinks(False)
        splitter.addWidget(self.detalhe)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

    # ------------------------------------------------------------------ #
    def _populate(self, termo: str) -> None:
        """Repreenche a lista aplicando o filtro de busca."""
        self.lista.clear()
        for entry in self._entries:
            if not termo or entry.matches(termo):
                item = QListWidgetItem(entry.name)
                item.setData(Qt.ItemDataRole.UserRole, entry)
                self.lista.addItem(item)
        if self.lista.count():
            self.lista.setCurrentRow(0)
        else:
            self.detalhe.setHtml("<p>Nenhum objeto corresponde ao filtro.</p>")

    def _on_select(self, current: QListWidgetItem | None, _previous: object = None) -> None:
        if current is None:
            self.detalhe.clear()
            return
        entry: ApiEntry = current.data(Qt.ItemDataRole.UserRole)
        self.detalhe.setHtml(entry.to_html())

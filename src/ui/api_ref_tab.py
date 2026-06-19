"""Aba API Reference — referência rápida da API SAP GUI Scripting.

Lista pesquisável dos objetos COM mais usados (``GuiApplication``,
``GuiSession``, ``GuiGridView``, ``GuiTree`` …) com seus métodos e propriedades
principais e um exemplo. Os dados são estáticos (não dependem de conexão SAP) e
servem de consulta enquanto se escreve ou se lê um script gerado.
"""

from __future__ import annotations

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
    example: str = ""

    def matches(self, termo: str) -> bool:
        """Indica se o termo (case-insensitive) ocorre no nome ou nos membros."""
        t = termo.lower()
        if t in self.name.lower() or t in self.summary.lower():
            return True
        return any(t in m.lower() or t in d.lower() for m, d in self.members)

    def to_html(self) -> str:
        """Renderiza a entrada como HTML para o painel de detalhes."""
        linhas = [f"<h2>{self.name}</h2>", f"<p>{self.summary}</p>"]
        if self.members:
            linhas.append("<h3>Membros principais</h3><ul>")
            linhas += [
                f"<li><b>{nome}</b> — {desc}</li>" for nome, desc in self.members
            ]
            linhas.append("</ul>")
        if self.example:
            linhas.append("<h3>Exemplo</h3>")
            linhas.append(f"<pre>{self.example}</pre>")
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
        example=(
            'sap_gui = win32com.client.GetObject("SAPGUI").GetScriptingEngine\n'
            "app = sap_gui  # GuiApplication"
        ),
    ),
    ApiEntry(
        name="GuiConnection",
        summary="Representa uma conexão a um sistema SAP; contém sessões.",
        members=[
            ("Children", "Coleção de GuiSession da conexão."),
            ("Description", "Nome/descrição da conexão."),
            ("CloseConnection()", "Encerra a conexão."),
        ],
        example="conn = app.Children(0)\nsession = conn.Children(0)",
    ),
    ApiEntry(
        name="GuiSession",
        summary="Uma sessão (janela) SAP. Ponto de entrada para FindById.",
        members=[
            ("FindById(id)", "Localiza um objeto pelo ID completo."),
            ("StartTransaction(tcode)", "Executa uma transação."),
            ("EndTransaction()", "Encerra a transação atual."),
            ("ActiveWindow", "Janela ativa (GuiMainWindow/GuiModalWindow)."),
            ("Info", "GuiSessionInfo: sistema, cliente, usuário, transação."),
        ],
        example=(
            'session.FindById("wnd[0]/usr/txtRSYST-BNAME").Text = "USUARIO"\n'
            'session.FindById("wnd[0]").sendVKey(0)'
        ),
    ),
    ApiEntry(
        name="GuiTextField / GuiCTextField",
        summary="Campos de texto editáveis da tela (entrada de dados).",
        members=[
            ("Text", "Conteúdo do campo (leitura/escrita)."),
            ("SetFocus()", "Coloca o cursor no campo."),
            ("CaretPosition", "Posição do cursor no campo."),
        ],
        example='session.FindById("wnd[0]/usr/ctxtVBAK-VBELN").Text = "1000"',
    ),
    ApiEntry(
        name="GuiButton",
        summary="Botão de tela. Acionado por Press.",
        members=[("Press()", "Aciona o botão.")],
        example='session.FindById("wnd[0]/tbar[0]/btn[11]").Press()',
    ),
    ApiEntry(
        name="GuiMainWindow / GuiModalWindow",
        summary="Janelas SAP. sendVKey simula teclas de função.",
        members=[
            ("sendVKey(n)", "Envia uma VKey (0=Enter, 8=F8, 11=Salvar…)."),
            ("Text", "Título da janela."),
            ("Close()", "Fecha janelas modais."),
        ],
        example='session.FindById("wnd[0]").sendVKey(0)  # Enter',
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
            ("PressButton(id)", "Aciona um botão da toolbar do grid."),
        ],
        example=(
            'grid = session.FindById("wnd[0]/usr/cntlGRID1/shellcont/shell")\n'
            'grid.SetCurrentCell(2, "MATNR")\n'
            "grid.SelectedRows = \"2\""
        ),
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
        example=(
            'tree = session.FindById("wnd[0]/usr/cntlTREE/shellcont/shell")\n'
            'tree.SelectNode("000042")'
        ),
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
        example='edit = session.FindById(".../shell"); n = edit.LineCount',
    ),
    ApiEntry(
        name="GuiStatusbar",
        summary="Barra de status — mensagens de retorno da transação.",
        members=[
            ("MessageType", "Tipo: S (sucesso), E (erro), W (aviso)…"),
            ("Text", "Texto da mensagem."),
            ("MessageId / MessageNumber", "Classe e número da mensagem."),
        ],
        example='msg = session.FindById("wnd[0]/sbar").Text',
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

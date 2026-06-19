"""Aba de conexão — conectar ao SAP GUI e escolher a sessão."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.sap_connection import SapConnectionError, SessionInfo
from src.ui.context import AppContext
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ConnectionTab(QWidget):
    """Conecta ao SAP GUI Scripting Engine e lista as sessões disponíveis."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._sessions: list[SessionInfo] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel("Conexão com o SAP GUI")
        title.setObjectName("title")
        layout.addWidget(title)

        botoes = QHBoxLayout()
        self.btn_connect = QPushButton("Conectar / Atualizar sessões")
        self.btn_connect.clicked.connect(self.refresh_sessions)
        botoes.addWidget(self.btn_connect)
        botoes.addStretch(1)
        layout.addLayout(botoes)

        self.lista = QListWidget()
        self.lista.itemSelectionChanged.connect(self._on_select)
        layout.addWidget(self.lista, 1)

        self.status = QLabel("Não conectado.")
        layout.addWidget(self.status)

    # ------------------------------------------------------------------ #
    def refresh_sessions(self) -> None:
        """Conecta ao SAP e popula a lista de sessões."""
        self.lista.clear()
        try:
            # Reconecta automaticamente se a referência COM tiver morrido.
            self._ctx.connection.ensure_connected()
            self._sessions = self._ctx.connection.list_sessions_info()
        except SapConnectionError as e:
            self.status.setText(f"Erro de conexão: {e}")
            self._ctx.statusMessage.emit("Falha ao conectar ao SAP GUI.")
            return

        if not self._sessions:
            self.status.setText("Conectado, mas nenhuma sessão encontrada.")
            return

        for info in self._sessions:
            label = f"{info.label}  |  {info.transaction or '—'}  |  {info.title}"
            item = QListWidgetItem(label)
            self.lista.addItem(item)
        self.status.setText(f"{len(self._sessions)} sessão(ões) encontrada(s).")
        self.lista.setCurrentRow(0)

    def _on_select(self) -> None:
        """Define a sessão escolhida no contexto da aplicação."""
        row = self.lista.currentRow()
        if not (0 <= row < len(self._sessions)):
            return
        info = self._sessions[row]
        try:
            session = self._ctx.connection.get_session(
                info.connection_index, info.session_index
            )
        except SapConnectionError as e:
            self.status.setText(f"Erro ao abrir sessão: {e}")
            return
        self._ctx.set_session(session)

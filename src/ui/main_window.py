"""Janela principal — monta as quatro abas sobre um :class:`AppContext`."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QMainWindow, QTabWidget

from src.core.sap_connection import SapConnection
from src.ui.analyser_tab import AnalyserTab
from src.ui.api_ref_tab import ApiRefTab
from src.ui.code_tab import CodeTab
from src.ui.connection_tab import ConnectionTab
from src.ui.context import AppContext
from src.ui.notes_tab import NotesTab
from src.ui.recorder_tab import RecorderTab
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MainWindow(QMainWindow):
    """Janela principal da SAP GUI Scripting Tool.

    Args:
        connection: Conexão SAP a usar (injetável em testes). Se omitida, uma
            :class:`SapConnection` real é criada.
    """

    def __init__(self, connection: SapConnection | None = None) -> None:
        super().__init__()
        self.setWindowTitle("SAP GUI Scripting Tool")
        self.resize(1100, 720)

        self.ctx = AppContext(connection)

        self.tabs = QTabWidget()
        self.connection_tab = ConnectionTab(self.ctx)
        self.analyser_tab = AnalyserTab(self.ctx)
        self.recorder_tab = RecorderTab(self.ctx)
        self.code_tab = CodeTab(self.ctx)
        self.api_ref_tab = ApiRefTab(self.ctx)
        self.notes_tab = NotesTab(self.ctx)

        self.tabs.addTab(self.connection_tab, "Conexão")
        self.tabs.addTab(self.analyser_tab, "Analyser")
        self.tabs.addTab(self.recorder_tab, "Recorder")
        self.tabs.addTab(self.code_tab, "Código")
        self.tabs.addTab(self.api_ref_tab, "API Reference")
        self.tabs.addTab(self.notes_tab, "Notas")
        self.setCentralWidget(self.tabs)

        barra_status = self.statusBar()
        if barra_status is not None:
            barra_status.showMessage("Pronto.")
            self.ctx.statusMessage.connect(barra_status.showMessage)
        # Ao gerar código, traz a aba Código para frente.
        self.ctx.codeGenerated.connect(lambda *_: self.tabs.setCurrentWidget(self.code_tab))

        self._install_shortcuts()

    def _install_shortcuts(self) -> None:
        """Instala os atalhos de teclado globais (NFR seção 9).

        F5 = atualizar árvore · F9 = gravar · Shift+F9 = parar ·
        Ctrl+C = copiar ID (apenas com foco no Analyser, para não atropelar a
        cópia padrão de texto nas demais abas).
        """
        QShortcut(QKeySequence(Qt.Key.Key_F5), self).activated.connect(self.refresh_tree)
        QShortcut(QKeySequence(Qt.Key.Key_F9), self).activated.connect(self.start_recording)
        QShortcut(QKeySequence("Shift+F9"), self).activated.connect(self.stop_recording)
        copy_id = QShortcut(QKeySequence.StandardKey.Copy, self.analyser_tab)
        copy_id.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        copy_id.activated.connect(self.analyser_tab.copy_selected_id)

    # ------------------------------------------------------------------ #
    # Ações de atalho
    # ------------------------------------------------------------------ #
    def refresh_tree(self) -> None:
        """F5 — reconstrói a árvore do Analyser e traz a aba para frente."""
        self.tabs.setCurrentWidget(self.analyser_tab)
        self.analyser_tab.analyse()

    def start_recording(self) -> None:
        """F9 — inicia a gravação se ainda não estiver gravando."""
        if not self.ctx.is_recording:
            self.ctx.start_recording()

    def stop_recording(self) -> None:
        """Shift+F9 — para a gravação se houver uma em curso."""
        if self.ctx.is_recording:
            self.ctx.stop_recording()

    def closeEvent(self, event: object) -> None:  # noqa: N802 - override Qt
        """Garante que a gravação pare ao fechar a janela."""
        if self.ctx.is_recording:
            self.ctx.stop_recording()
        super().closeEvent(event)  # type: ignore[arg-type]

"""Janela principal — monta as quatro abas sobre um :class:`AppContext`."""

from __future__ import annotations

from PyQt6.QtWidgets import QMainWindow, QTabWidget

from src.core.sap_connection import SapConnection
from src.ui.analyser_tab import AnalyserTab
from src.ui.code_tab import CodeTab
from src.ui.connection_tab import ConnectionTab
from src.ui.context import AppContext
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

        self.tabs.addTab(self.connection_tab, "Conexão")
        self.tabs.addTab(self.analyser_tab, "Analyser")
        self.tabs.addTab(self.recorder_tab, "Recorder")
        self.tabs.addTab(self.code_tab, "Código")
        self.setCentralWidget(self.tabs)

        barra_status = self.statusBar()
        if barra_status is not None:
            barra_status.showMessage("Pronto.")
            self.ctx.statusMessage.connect(barra_status.showMessage)
        # Ao gerar código, traz a aba Código para frente.
        self.ctx.codeGenerated.connect(lambda *_: self.tabs.setCurrentWidget(self.code_tab))

    def closeEvent(self, event: object) -> None:  # noqa: N802 - override Qt
        """Garante que a gravação pare ao fechar a janela."""
        if self.ctx.is_recording:
            self.ctx.stop_recording()
        super().closeEvent(event)  # type: ignore[arg-type]

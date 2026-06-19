"""Contexto de aplicação compartilhado entre as abas da UI.

Centraliza o estado global (conexão SAP, sessão selecionada, gravação em curso)
e expõe sinais Qt para que as abas reajam a mudanças sem se acoplarem entre si.
Toda a lógica de negócio é delegada a :mod:`src.core`/:mod:`src.codegen`; este
objeto apenas orquestra e emite eventos.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

from src.core.recorder import Recorder
from src.core.recorder_polling import DEFAULT_POLL_INTERVAL
from src.core.sap_connection import SapConnection
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AppContext(QObject):
    """Estado e sinais compartilhados pela aplicação.

    Signals:
        sessionChanged: Emitido com o ``GuiSession`` selecionado (ou ``None``).
        recordingChanged: Emitido com ``True``/``False`` ao iniciar/parar gravação.
        statusMessage: Mensagem curta para a barra de status.
    """

    sessionChanged = pyqtSignal(object)
    recordingChanged = pyqtSignal(bool)
    statusMessage = pyqtSignal(str)
    #: Emitido com (código, linguagem) quando a aba Recorder gera um script.
    codeGenerated = pyqtSignal(str, str)

    def __init__(self, connection: SapConnection | None = None) -> None:
        super().__init__()
        self.connection: SapConnection = connection or SapConnection()
        self.session: Any | None = None
        self.recorder: Recorder | None = None

    # ------------------------------------------------------------------ #
    # Sessão
    # ------------------------------------------------------------------ #
    def set_session(self, session: Any | None) -> None:
        """Define a sessão ativa e notifica as abas."""
        self.session = session
        self.sessionChanged.emit(session)
        if session is not None:
            self.statusMessage.emit("Sessão selecionada.")

    @property
    def has_session(self) -> bool:
        return self.session is not None

    # ------------------------------------------------------------------ #
    # Gravação
    # ------------------------------------------------------------------ #
    @property
    def is_recording(self) -> bool:
        return self.recorder is not None and self.recorder.is_recording

    def start_recording(self, *, poll_interval: float = DEFAULT_POLL_INTERVAL) -> bool:
        """Inicia a gravação na sessão atual.

        Returns:
            ``True`` se iniciou; ``False`` se não há sessão.
        """
        if self.session is None:
            self.statusMessage.emit("Selecione uma sessão antes de gravar.")
            return False
        self.recorder = Recorder(self.session, poll_interval=poll_interval)
        self.recorder.start()
        self.recordingChanged.emit(True)
        self.statusMessage.emit("Gravando…")
        return True

    def stop_recording(self) -> None:
        """Para a gravação (mantém as ações no buffer para gerar código)."""
        if self.recorder is not None:
            self.recorder.stop()
        self.recordingChanged.emit(False)
        n = len(self.recorder.actions) if self.recorder else 0
        self.statusMessage.emit(f"Gravação parada — {n} ação(ões) capturada(s).")

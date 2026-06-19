"""Orquestrador do Recorder — combina os três motores de captura.

Coordena:

* :class:`~src.core.recorder_com.ComRecorder` — eventos COM (objetos normais);
* :class:`~src.core.recorder_polling.PollingRecorder` — snapshot/diff (GuiShell);
* :class:`~src.core.recorder_win32.Win32Recorder` — diálogos Win32 nativos.

Cada motor empurra :class:`Acao` para um buffer único e *thread-safe*, na ordem
cronológica em que chegam — produzindo a gravação híbrida (SAP + Win32
intercalados) que é o diferencial sobre o Scripting Tracker. Ao final, o buffer
é renderizado na linguagem escolhida via :mod:`src.codegen`.
"""

from __future__ import annotations

import threading
from typing import Any

from src.codegen import Acao, SessionInfoLite, get_generator
from src.core.com_utils import safe_get
from src.core.recorder_com import ComRecorder
from src.core.recorder_polling import DEFAULT_POLL_INTERVAL, PollingRecorder
from src.core.recorder_win32 import Win32Recorder
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ActionBuffer:
    """Buffer *thread-safe* de :class:`Acao` capturadas pelos motores."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._acoes: list[Acao] = []

    def add(self, acao: Acao) -> None:
        """Acrescenta uma ação (chamado de múltiplas threads)."""
        with self._lock:
            self._acoes.append(acao)

    def snapshot(self) -> list[Acao]:
        """Retorna uma cópia imutável da sequência atual de ações."""
        with self._lock:
            return list(self._acoes)

    def clear(self) -> None:
        """Esvazia o buffer."""
        with self._lock:
            self._acoes.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._acoes)


class Recorder:
    """Orquestra os três motores de gravação sobre uma sessão SAP.

    Args:
        session: Objeto COM ``GuiSession`` a gravar.
        poll_interval: Intervalo do motor de polling (segundos).
        capture_com: Habilita o motor de eventos COM.
        capture_polling: Habilita o motor de polling de GuiShell.
        capture_win32: Habilita o motor de diálogos Win32 nativos.
    """

    def __init__(
        self,
        session: Any,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        capture_com: bool = True,
        capture_polling: bool = True,
        capture_win32: bool = True,
    ) -> None:
        self._session = session
        self._buffer = ActionBuffer()
        self._recording = False

        self._com = ComRecorder(session, self._buffer.add) if capture_com else None
        self._polling = (
            PollingRecorder(session, self._buffer.add, poll_interval=poll_interval)
            if capture_polling
            else None
        )
        self._win32 = Win32Recorder(self._buffer.add) if capture_win32 else None

    # ------------------------------------------------------------------ #
    # Ciclo de vida
    # ------------------------------------------------------------------ #
    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        """Inicia todos os motores habilitados."""
        if self._recording:
            return
        self._buffer.clear()
        for motor in (self._com, self._polling, self._win32):
            if motor is not None:
                motor.start()
        self._recording = True
        logger.info("Gravação iniciada.")

    def stop(self) -> None:
        """Para todos os motores; o buffer é preservado para geração de código."""
        for motor in (self._com, self._polling, self._win32):
            if motor is not None:
                motor.stop()
        self._recording = False
        logger.info("Gravação parada (%d ações no buffer).", len(self._buffer))

    # ------------------------------------------------------------------ #
    # Acesso às ações e geração de código
    # ------------------------------------------------------------------ #
    @property
    def actions(self) -> list[Acao]:
        """Cópia da sequência de ações capturadas até o momento."""
        return self._buffer.snapshot()

    def add_action(self, acao: Acao) -> None:
        """Adiciona uma ação manualmente (ex.: comentário inserido pela UI)."""
        self._buffer.add(acao)

    def clear(self) -> None:
        """Descarta as ações capturadas."""
        self._buffer.clear()

    def generate_code(self, language: str, info: SessionInfoLite | None = None) -> str:
        """Renderiza as ações capturadas na ``language`` escolhida.

        Args:
            language: Identificador de linguagem registrado em :mod:`src.codegen`.
            info: Metadados de cabeçalho; se omitido, são extraídos da sessão.

        Returns:
            O script completo (cabeçalho + ações + rodapé).
        """
        gen = get_generator(language)
        return gen.gerar_script_completo(self.actions, info or self.session_info())

    def session_info(self) -> SessionInfoLite:
        """Extrai :class:`SessionInfoLite` da sessão COM (best-effort)."""
        info = safe_get(self._session, "Info")
        return SessionInfoLite(
            system=str(safe_get(info, "SystemName", "") or ""),
            client=str(safe_get(info, "Client", "") or ""),
            user=str(safe_get(info, "User", "") or ""),
            transaction=str(safe_get(info, "Transaction", "") or ""),
        )

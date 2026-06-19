"""Aba do Recorder — iniciar/parar gravação, ver ações e gerar código."""

from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.codegen import available_generators
from src.codegen.base import Acao
from src.ui.context import AppContext
from src.utils.logger import get_logger

logger = get_logger(__name__)

#: Período de atualização da lista de ações durante a gravação (ms).
_REFRESH_MS = 400


class RecorderTab(QWidget):
    """Controla a gravação e gera o código na linguagem escolhida."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.setInterval(_REFRESH_MS)
        self._timer.timeout.connect(self._refresh_actions)
        ctx.sessionChanged.connect(lambda *_: self._update_enabled())
        ctx.recordingChanged.connect(self._on_recording_changed)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel("Gravador")
        title.setObjectName("title")
        layout.addWidget(title)

        barra = QHBoxLayout()
        self.btn_record = QPushButton("● Gravar")
        self.btn_record.clicked.connect(self._toggle_record)
        barra.addWidget(self.btn_record)

        barra.addWidget(QLabel("Linguagem:"))
        self.combo = QComboBox()
        for language, display in available_generators():
            self.combo.addItem(display, language)
        barra.addWidget(self.combo)

        self.btn_generate = QPushButton("Gerar código")
        self.btn_generate.clicked.connect(self.generate)
        barra.addWidget(self.btn_generate)

        self.btn_clear = QPushButton("Limpar")
        self.btn_clear.clicked.connect(self.clear)
        barra.addWidget(self.btn_clear)
        barra.addStretch(1)
        layout.addLayout(barra)

        self.lista = QListWidget()
        layout.addWidget(self.lista, 1)

        self._update_enabled()

    # ------------------------------------------------------------------ #
    @property
    def selected_language(self) -> str:
        return str(self.combo.currentData())

    def _update_enabled(self) -> None:
        recording = self._ctx.is_recording
        self.btn_record.setEnabled(self._ctx.has_session or recording)
        has_actions = self._ctx.recorder is not None and bool(self._ctx.recorder.actions)
        self.btn_generate.setEnabled(has_actions)
        self.btn_clear.setEnabled(has_actions)

    # ------------------------------------------------------------------ #
    def _toggle_record(self) -> None:
        if self._ctx.is_recording:
            self._ctx.stop_recording()
        else:
            self._ctx.start_recording()

    def _on_recording_changed(self, recording: bool) -> None:
        if recording:
            self.btn_record.setText("■ Parar")
            self.btn_record.setObjectName("danger")
            self.lista.clear()
            self._timer.start()
        else:
            self.btn_record.setText("● Gravar")
            self.btn_record.setObjectName("")
            self._timer.stop()
            self._refresh_actions()
        # Reaplica o QSS para refletir a troca de objectName.
        estilo = self.btn_record.style()
        if estilo is not None:
            estilo.polish(self.btn_record)
        self._update_enabled()

    def _refresh_actions(self) -> None:
        if self._ctx.recorder is None:
            return
        acoes = self._ctx.recorder.actions
        self.lista.clear()
        for a in acoes:
            self.lista.addItem(self._format_action(a))
        self._update_enabled()

    @staticmethod
    def _format_action(a: Acao) -> str:
        origem = {"com_event": "COM", "polling": "SHELL", "win32": "WIN32"}.get(
            a.origem, a.origem
        )
        alvo = a.obj_id or a.args.get("title", "")
        return f"[{origem}] {a.tipo}  {alvo}  {a.args if a.args else ''}".rstrip()

    # ------------------------------------------------------------------ #
    def generate(self) -> None:
        """Gera o código a partir das ações e o publica para a aba Código."""
        if self._ctx.recorder is None:
            return
        codigo = self._ctx.recorder.generate_code(self.selected_language)
        self._ctx.codeGenerated.emit(codigo, self.selected_language)
        self._ctx.statusMessage.emit(
            f"Código {self.selected_language} gerado ({len(self._ctx.recorder.actions)} ações)."
        )

    def clear(self) -> None:
        if self._ctx.recorder is not None:
            self._ctx.recorder.clear()
        self.lista.clear()
        self._update_enabled()

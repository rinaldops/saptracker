"""Aba de Notas — área de texto livre para anotações do desenvolvedor.

Bloco de rascunho persistido em arquivo, útil para guardar IDs, trechos de
código e lembretes durante a análise/gravação. Não interage com o SAP.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.ui.context import AppContext
from src.utils.clipboard import copy_text
from src.utils.logger import get_logger

logger = get_logger(__name__)


class NotesTab(QWidget):
    """Bloco de notas textuais com cópia, salvar e abrir."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        barra = QHBoxLayout()
        titulo = QLabel("Notas")
        titulo.setObjectName("title")
        barra.addWidget(titulo)
        barra.addStretch(1)
        self.btn_copy = QPushButton("Copiar")
        self.btn_copy.clicked.connect(self.copy)
        self.btn_open = QPushButton("Abrir…")
        self.btn_open.clicked.connect(self.open)
        self.btn_save = QPushButton("Salvar…")
        self.btn_save.clicked.connect(self.save)
        barra.addWidget(self.btn_copy)
        barra.addWidget(self.btn_open)
        barra.addWidget(self.btn_save)
        layout.addLayout(barra)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(
            "Anote aqui IDs, trechos de código e lembretes…"
        )
        layout.addWidget(self.editor, 1)

    # ------------------------------------------------------------------ #
    def text(self) -> str:
        """Retorna o conteúdo atual das notas."""
        return self.editor.toPlainText()

    def set_text(self, value: str) -> None:
        """Substitui o conteúdo das notas."""
        self.editor.setPlainText(value)

    def copy(self) -> None:
        if copy_text(self.text()):
            self._ctx.statusMessage.emit("Notas copiadas para a área de transferência.")

    def save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar notas", "notas.txt", "Texto (*.txt);;Todos (*.*)"
        )
        if path:
            Path(path).write_text(self.text(), encoding="utf-8")
            self._ctx.statusMessage.emit(f"Notas salvas em {path}.")

    def open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir notas", "", "Texto (*.txt);;Todos (*.*)"
        )
        if path:
            self.set_text(Path(path).read_text(encoding="utf-8"))
            self._ctx.statusMessage.emit(f"Notas carregadas de {path}.")

"""Aba de Código — exibe o script gerado, com cópia e salvamento."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.codegen import get_generator
from src.ui.code_editor import CodeEditor
from src.ui.context import AppContext
from src.utils.clipboard import copy_text
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CodeTab(QWidget):
    """Mostra o código gerado pelo Recorder e permite copiar/salvar."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._language = "python"
        self._build_ui()
        ctx.codeGenerated.connect(self.show_code)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        barra = QHBoxLayout()
        self.label = QLabel("Código gerado")
        self.label.setObjectName("title")
        barra.addWidget(self.label)
        barra.addStretch(1)
        self.btn_copy = QPushButton("Copiar")
        self.btn_copy.clicked.connect(self.copy)
        self.btn_save = QPushButton("Salvar…")
        self.btn_save.clicked.connect(self.save)
        barra.addWidget(self.btn_copy)
        barra.addWidget(self.btn_save)
        layout.addLayout(barra)

        self.editor = CodeEditor()
        layout.addWidget(self.editor, 1)

    # ------------------------------------------------------------------ #
    def show_code(self, code: str, language: str) -> None:
        """Recebe o código gerado e o exibe com o realce da linguagem."""
        self._language = language
        self.editor.set_language(language)
        self.editor.set_text(code)
        self.label.setText(f"Código gerado — {language}")

    def copy(self) -> None:
        if copy_text(self.editor.text()):
            self._ctx.statusMessage.emit("Código copiado para a área de transferência.")

    def save(self) -> None:
        ext = get_generator(self._language).file_extension
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar script", f"script{ext}", f"Script (*{ext});;Todos (*.*)"
        )
        if path:
            from pathlib import Path

            Path(path).write_text(self.editor.text(), encoding="utf-8")
            self._ctx.statusMessage.emit(f"Script salvo em {path}.")

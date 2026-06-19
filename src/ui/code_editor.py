"""Editor de código baseado em QScintilla, com realce por linguagem.

Usa ``QsciScintilla`` quando disponível (lexers para as linguagens que o
QScintilla suporta nativamente — Python e Java); para as demais (VBA, VBScript,
PowerShell, AutoIt) o texto é exibido sem realce. Se o QScintilla não estiver
instalado, recai para um ``QPlainTextEdit`` simples, preservando a mesma API
(``set_text``/``text``/``set_language``).
"""

from __future__ import annotations

from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QPlainTextEdit, QWidget

from src.utils.logger import get_logger

logger = get_logger(__name__)

try:  # pragma: no cover - depende do pacote QScintilla
    from PyQt6.Qsci import QsciScintilla

    _HAS_QSCI = True
except ImportError:  # pragma: no cover
    _HAS_QSCI = False


def _lexer_for(language: str) -> object | None:
    """Retorna uma instância de lexer QScintilla para a linguagem, se houver."""
    if not _HAS_QSCI:
        return None
    from PyQt6 import Qsci

    mapa = {
        "python": "QsciLexerPython",
        "java": "QsciLexerJava",
    }
    nome = mapa.get(language)
    if nome is None:
        return None
    lexer_cls = getattr(Qsci, nome, None)
    return lexer_cls() if lexer_cls is not None else None


class CodeEditor(QWidget):
    """Widget de edição/visualização de código com realce opcional.

    A API pública é estável independentemente do backend (QScintilla ou
    ``QPlainTextEdit``): :meth:`set_text`, :meth:`text` e :meth:`set_language`.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from PyQt6.QtWidgets import QVBoxLayout

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._language = "python"
        if _HAS_QSCI:
            self._editor: QWidget = self._build_qsci()
        else:
            self._editor = QPlainTextEdit()
            self._editor.setFont(QFont("Consolas", 11))
        layout.addWidget(self._editor)

    # ------------------------------------------------------------------ #
    def _build_qsci(self) -> QWidget:
        editor = QsciScintilla()
        editor.setFont(QFont("Consolas", 11))
        editor.setUtf8(True)
        editor.setMarginType(0, QsciScintilla.MarginType.NumberMargin)
        editor.setMarginWidth(0, "0000")
        editor.setMarginsBackgroundColor(QColor("#171a1f"))
        editor.setMarginsForegroundColor(QColor("#6a707a"))
        editor.setPaper(QColor("#171a1f"))
        editor.setColor(QColor("#d7dae0"))
        editor.setCaretForegroundColor(QColor("#ffffff"))
        editor.setCaretLineVisible(True)
        editor.setCaretLineBackgroundColor(QColor("#21262d"))
        return editor

    # ------------------------------------------------------------------ #
    # API pública
    # ------------------------------------------------------------------ #
    def set_text(self, text: str) -> None:
        """Define o conteúdo do editor."""
        if _HAS_QSCI:
            self._editor.setText(text)  # type: ignore[attr-defined]
        else:
            self._editor.setPlainText(text)  # type: ignore[attr-defined]

    def text(self) -> str:
        """Retorna o conteúdo atual do editor."""
        if _HAS_QSCI:
            return str(self._editor.text())  # type: ignore[attr-defined]
        return str(self._editor.toPlainText())  # type: ignore[attr-defined]

    def set_language(self, language: str) -> None:
        """Troca o realce de sintaxe conforme a linguagem alvo."""
        self._language = language
        if not _HAS_QSCI:
            return
        lexer = _lexer_for(language)
        self._editor.setLexer(lexer)  # type: ignore[attr-defined]
        if lexer is None:
            # Sem lexer: reforça as cores do tema escuro.
            self._editor.setPaper(QColor("#171a1f"))  # type: ignore[attr-defined]
            self._editor.setColor(QColor("#d7dae0"))  # type: ignore[attr-defined]

    @property
    def language(self) -> str:
        return self._language

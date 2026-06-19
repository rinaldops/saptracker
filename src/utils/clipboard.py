"""Utilitários de clipboard.

Usa o clipboard do Qt quando há um ``QApplication`` ativo; caso contrário,
recorre ao clipboard nativo do Windows via pywin32. Isso permite copiar IDs e
código tanto a partir da UI quanto de scripts/testes sem GUI.
"""

from __future__ import annotations

from src.utils.logger import get_logger

logger = get_logger(__name__)


def copy_text(text: str) -> bool:
    """Copia ``text`` para o clipboard do sistema.

    Returns:
        ``True`` se a cópia foi bem-sucedida, ``False`` caso contrário.
    """
    if _copy_via_qt(text):
        return True
    return _copy_via_win32(text)


def _copy_via_qt(text: str) -> bool:
    """Tenta copiar usando o clipboard do Qt (se houver QApplication)."""
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        return False

    app = QApplication.instance()
    if app is None:
        return False
    clipboard = app.clipboard()
    if clipboard is None:
        return False
    clipboard.setText(text)
    return True


def _copy_via_win32(text: str) -> bool:
    """Tenta copiar usando o clipboard nativo do Windows."""
    try:
        import win32clipboard
        import win32con
    except ImportError:
        logger.debug("win32clipboard indisponível; cópia ignorada.")
        return False

    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
        return True
    except Exception as e:  # noqa: BLE001 - clipboard pode falhar por concorrência
        logger.debug("Falha ao copiar via win32clipboard: %s", e)
        return False
    finally:
        try:
            win32clipboard.CloseClipboard()
        except Exception:  # noqa: BLE001
            pass

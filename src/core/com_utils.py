"""Helpers para chamadas COM seguras ao SAP GUI Scripting Engine.

Toda chamada ao SAP GUI COM pode falhar se a sessão for fechada, a tela mudar
ou o objeto deixar de existir. Estes helpers padronizam o tratamento de erro
(seção 4.3 da spec), logando em DEBUG para não poluir a interface.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from src.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

# ``pywintypes`` só existe no Windows. Em outros ambientes (CI Linux, testes),
# definimos um placeholder para que ``except`` não quebre na importação.
try:  # pragma: no cover - dependente de plataforma
    import pywintypes

    _COMError: type[BaseException] = pywintypes.com_error
except ImportError:  # pragma: no cover - ambiente sem Windows
    class _COMError(Exception):  # type: ignore[no-redef]
        """Placeholder para ``pywintypes.com_error`` fora do Windows."""


def safe_com_call(func: Callable[..., T], *args: Any, default: T | None = None) -> T | None:
    """Executa uma chamada COM tratando erros de forma padronizada.

    Args:
        func: Callable que faz a chamada COM (ex: ``lambda: obj.RowCount``).
        *args: Argumentos posicionais repassados a ``func``.
        default: Valor retornado se a chamada falhar.

    Returns:
        O resultado de ``func`` ou ``default`` em caso de erro COM/atributo.
    """
    try:
        return func(*args)
    except _COMError as e:
        logger.debug("Chamada COM falhou: %s | args: %s", e, args)
        return default
    except AttributeError as e:
        logger.debug("Atributo COM indisponível: %s", e)
        return default


def safe_get(obj: Any, attr: str, default: Any = None) -> Any:
    """Lê ``obj.attr`` com tratamento de erro COM.

    Útil para propriedades que podem não existir em todos os tipos de objeto.
    """
    return safe_com_call(lambda: getattr(obj, attr), default=default)


def is_com_error(exc: BaseException) -> bool:
    """Indica se ``exc`` é um erro originado do subsistema COM."""
    return isinstance(exc, (_COMError, AttributeError))


def com_len(collection: Any) -> int:
    """Retorna o número de elementos de uma coleção COM do SAP GUI.

    O SAP expõe o tamanho de formas diferentes conforme o tipo de coleção:
    ``GuiComponentCollection`` (ex.: ``Children``) usa ``Count``, enquanto as
    coleções retornadas por métodos como ``GetAllNodeKeys`` /
    ``GetColumnNames`` (``GuiCollection``) usam ``Length``. Tenta ambos.
    """
    if collection is None:
        return 0
    for attr in ("Count", "Length"):
        value = safe_get(collection, attr, None)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    try:
        return len(collection)
    except (TypeError, ValueError, _COMError):
        return 0


def get_clipboard_text() -> str | None:
    """Lê o texto atual da área de transferência do Windows.

    Returns:
        O texto, ou ``None`` se vazio/indisponível/fora do Windows.
    """
    try:
        import win32clipboard

        win32clipboard.OpenClipboard()
        try:
            return str(win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT))
        finally:
            win32clipboard.CloseClipboard()
    except Exception as e:  # noqa: BLE001 - clipboard vazio, ocupado ou fora do Windows
        logger.debug("Leitura do clipboard falhou: %s", e)
        return None


def set_clipboard_text(text: str | None) -> None:
    """Grava (ou limpa, se ``None``) o texto da área de transferência do Windows."""
    try:
        import win32clipboard

        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            if text:
                win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
        finally:
            win32clipboard.CloseClipboard()
    except Exception as e:  # noqa: BLE001 - clipboard ocupado ou fora do Windows
        logger.debug("Escrita no clipboard falhou: %s", e)


def com_item(collection: Any, index: int, default: Any = None) -> Any:
    """Retorna o elemento ``index`` de uma coleção COM, tolerante à API.

    Tenta ``ElementAt(index)`` (SAP), ``Item(index)``, o indexador
    ``collection[index]`` e, por fim, ``collection(index)``. Isso inclui os
    ``SAFEARRAY`` convertidos pelo pywin32 em tuplas/listas Python.
    """
    if collection is None:
        return default
    for method in ("ElementAt", "Item"):
        func = safe_get(collection, method, None)
        if callable(func):
            value = safe_com_call(func, index)
            if value is not None:
                return value
    try:
        return collection[index]
    except (TypeError, KeyError, IndexError, AttributeError, _COMError):
        pass
    try:
        value = collection(index)
    except (TypeError, AttributeError, _COMError):
        return default
    return default if value is None else value

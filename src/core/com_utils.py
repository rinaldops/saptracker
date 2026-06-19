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

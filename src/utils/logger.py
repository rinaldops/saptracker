"""Logging estruturado para toda a aplicação.

Fornece um único ponto de configuração (`configure_logging`) e uma fábrica de
loggers (`get_logger`) usada por todos os módulos. Erros de COM são logados em
nível DEBUG para não poluir a interface (ver `src.core` e a seção 4.3 da spec).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_CONFIGURED = False
_DEFAULT_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-28s | %(message)s"
_DATE_FORMAT = "%H:%M:%S"


def configure_logging(
    level: int = logging.INFO,
    *,
    log_file: Path | None = None,
) -> None:
    """Configura o logging raiz uma única vez.

    Args:
        level: Nível mínimo para o console (ex: ``logging.DEBUG``).
        log_file: Caminho opcional para também gravar logs em arquivo
            (sempre em nível DEBUG, independente do nível de console).
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger("sap_scripting_tool")
    root.setLevel(logging.DEBUG)
    root.propagate = False

    formatter = logging.Formatter(_DEFAULT_FORMAT, datefmt=_DATE_FORMAT)

    console = logging.StreamHandler(stream=sys.stderr)
    console.setLevel(level)
    console.setFormatter(formatter)
    root.addHandler(console)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Retorna um logger filho do logger raiz da aplicação.

    Args:
        name: Normalmente ``__name__`` do módulo chamador.

    Returns:
        Logger nomeado sob o namespace ``sap_scripting_tool``.
    """
    if not _CONFIGURED:
        configure_logging()
    short = name.split(".")[-1] if name else "root"
    return logging.getLogger(f"sap_scripting_tool.{short}")

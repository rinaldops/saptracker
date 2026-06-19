"""Logging estruturado para toda a aplicação.

Fornece um único ponto de configuração (`configure_logging`) e uma fábrica de
loggers (`get_logger`) usada por todos os módulos. Erros de COM são logados em
nível DEBUG para não poluir a interface (ver `src.core` e a seção 4.3 da spec).
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path

_CONFIGURED = False
_DEFAULT_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-28s | %(message)s"
_DATE_FORMAT = "%H:%M:%S"

#: Caminho do arquivo de log efetivamente em uso (preenchido na configuração).
_LOG_FILE_PATH: Path | None = None


def default_log_file() -> Path:
    """Caminho padrão do arquivo de log (gravável mesmo a partir do EXE).

    Usa ``%LOCALAPPDATA%/SAPScriptingTool/logs`` no Windows e, como reserva, o
    diretório temporário do sistema.
    """
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    raiz = Path(base) if base else Path(tempfile.gettempdir())
    return raiz / "SAPScriptingTool" / "logs" / "sap_tool.log"


def configure_logging(
    level: int | None = None,
    *,
    log_file: Path | None = None,
) -> None:
    """Configura o logging raiz uma única vez.

    Por padrão grava SEMPRE em arquivo (nível DEBUG) para facilitar o
    diagnóstico do executável. O nível do console pode ser controlado pela
    variável de ambiente ``SAPTOOL_LOG_LEVEL`` (ex.: ``DEBUG``).

    Args:
        level: Nível do console. Se ``None``, usa ``SAPTOOL_LOG_LEVEL`` ou INFO.
        log_file: Arquivo de log. Se ``None``, usa :func:`default_log_file`.
    """
    global _CONFIGURED, _LOG_FILE_PATH
    if _CONFIGURED:
        return

    if level is None:
        env_level = os.environ.get("SAPTOOL_LOG_LEVEL", "INFO").upper()
        level = getattr(logging, env_level, logging.INFO)

    root = logging.getLogger("sap_scripting_tool")
    root.setLevel(logging.DEBUG)
    root.propagate = False

    formatter = logging.Formatter(_DEFAULT_FORMAT, datefmt=_DATE_FORMAT)

    console = logging.StreamHandler(stream=sys.stderr)
    console.setLevel(level)
    console.setFormatter(formatter)
    root.addHandler(console)

    if log_file is None:
        log_file = default_log_file()
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
        _LOG_FILE_PATH = log_file
    except OSError as e:  # diretório sem permissão: segue só com console
        root.warning("Não foi possível abrir o arquivo de log %s: %s", log_file, e)

    _CONFIGURED = True
    if _LOG_FILE_PATH is not None:
        root.info("Log em arquivo: %s", _LOG_FILE_PATH)


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

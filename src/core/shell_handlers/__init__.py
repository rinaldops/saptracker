"""Registry de handlers de GuiShell.

Mapeia o tipo SAP (string retornada por ``obj.Type``) para a instância de
handler responsável. Use :func:`get_handler` para obter o handler adequado a um
objeto COM; tipos sem handler dedicado recebem o :class:`GuiShellGenerico`.

Para adicionar suporte a um novo tipo (ex: ``GuiOfficeIntegration``):

1. Crie ``src/core/shell_handlers/office_integration.py`` com a classe handler.
2. Importe-a aqui e registre uma instância em :data:`HANDLERS`.
"""

from __future__ import annotations

from typing import Any

from src.core.com_utils import safe_get
from src.core.shell_handlers.base import GuiShellHandler
from src.core.shell_handlers.calendar import GuiCalendarHandler
from src.core.shell_handlers.generic import GuiShellGenerico
from src.core.shell_handlers.grid_view import GuiGridViewHandler
from src.core.shell_handlers.text_edit import GuiTextEditHandler
from src.core.shell_handlers.toolbar import GuiToolbarHandler
from src.core.shell_handlers.tree import GuiTreeHandler
from src.utils.logger import get_logger

logger = get_logger(__name__)

#: Registry tipo SAP -> instância de handler (handlers são stateless/reusáveis).
HANDLERS: dict[str, GuiShellHandler] = {
    "GuiGridView": GuiGridViewHandler(),
    "GuiTree": GuiTreeHandler(),
    "GuiTextEdit": GuiTextEditHandler(),
    "GuiCalendar": GuiCalendarHandler(),
    "GuiToolbarControl": GuiToolbarHandler(),
}

#: Handler de fallback para qualquer tipo não registrado.
GENERIC_HANDLER: GuiShellHandler = GuiShellGenerico()

#: Controles GuiShell reportam ``Type == "GuiShell"`` e o tipo real em
#: ``SubType`` — SEM o prefixo ``Gui`` (ex.: ``"Tree"``, ``"GridView"``).
#: Este mapa traduz os SubTypes observados no SAP real para a chave do registry.
_SUBTYPE_ALIASES: dict[str, str] = {
    "Tree": "GuiTree",
    "GridView": "GuiGridView",
    "ALVGrid": "GuiGridView",
    "TextEdit": "GuiTextEdit",
    "Calendar": "GuiCalendar",
    "Toolbar": "GuiToolbarControl",
    "ToolbarControl": "GuiToolbarControl",
}


def normalize_shell_type(sap_type: str, subtype: str = "") -> str:
    """Resolve o tipo efetivo de um controle a partir de ``Type`` e ``SubType``.

    Quando ``Type == "GuiShell"``, o tipo real está em ``SubType`` (ex.: o SAP
    reporta ``"Tree"`` para um ``GuiTree``). Tenta, nesta ordem: o ``SubType``
    como chave direta do registry, um alias conhecido e, por fim, o ``SubType``
    com prefixo ``Gui``.
    """
    if sap_type != "GuiShell" or not subtype:
        return sap_type
    if subtype in HANDLERS:
        return subtype
    if subtype in _SUBTYPE_ALIASES:
        return _SUBTYPE_ALIASES[subtype]
    return subtype if subtype.startswith("Gui") else f"Gui{subtype}"


def get_handler_for_type(sap_type: str) -> GuiShellHandler:
    """Retorna o handler registrado para ``sap_type`` (ou o genérico)."""
    return HANDLERS.get(sap_type, GENERIC_HANDLER)


def effective_type(obj: Any) -> str:
    """Tipo efetivo do objeto COM, resolvendo ``GuiShell`` via ``SubType``."""
    sap_type = str(safe_get(obj, "Type", "") or "")
    subtype = str(safe_get(obj, "SubType", "") or "") if sap_type == "GuiShell" else ""
    return normalize_shell_type(sap_type, subtype)


def get_handler(obj: Any) -> GuiShellHandler:
    """Retorna o handler adequado ao objeto COM ``obj``.

    Vários controles SAP reportam ``Type == "GuiShell"`` e expõem o tipo real em
    ``SubType`` (ex.: ``"Tree"`` → ``GuiTree``). A resolução é feita por
    :func:`normalize_shell_type`. Tipos não registrados recebem o genérico.
    """
    sap_type = str(safe_get(obj, "Type", "") or "")
    subtype = str(safe_get(obj, "SubType", "") or "") if sap_type == "GuiShell" else ""
    resolved = normalize_shell_type(sap_type, subtype)
    handler = get_handler_for_type(resolved)
    logger.debug(
        "get_handler: Type=%r SubType=%r -> tipo=%r handler=%s",
        sap_type, subtype, resolved, type(handler).__name__,
    )
    return handler


def is_supported_shell(sap_type: str) -> bool:
    """Indica se há handler dedicado (introspecção rica) para ``sap_type``."""
    return sap_type in HANDLERS


__all__ = [
    "HANDLERS",
    "GENERIC_HANDLER",
    "GuiShellHandler",
    "effective_type",
    "get_handler",
    "get_handler_for_type",
    "is_supported_shell",
    "normalize_shell_type",
]

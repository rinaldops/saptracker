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


def get_handler_for_type(sap_type: str) -> GuiShellHandler:
    """Retorna o handler registrado para ``sap_type`` (ou o genérico)."""
    return HANDLERS.get(sap_type, GENERIC_HANDLER)


def get_handler(obj: Any) -> GuiShellHandler:
    """Retorna o handler adequado ao objeto COM ``obj``.

    Determina o tipo via ``obj.Type`` e busca no registry. Objetos que não
    expõem ``Type`` ou cujo tipo não está registrado recebem o handler genérico.
    """
    sap_type = str(safe_get(obj, "Type", "") or "")
    return get_handler_for_type(sap_type)


def is_supported_shell(sap_type: str) -> bool:
    """Indica se há handler dedicado (introspecção rica) para ``sap_type``."""
    return sap_type in HANDLERS


__all__ = [
    "HANDLERS",
    "GENERIC_HANDLER",
    "GuiShellHandler",
    "get_handler",
    "get_handler_for_type",
    "is_supported_shell",
]

"""Handler de fallback para tipos de GuiShell sem handler dedicado."""

from __future__ import annotations

from typing import Any

from src.core.com_utils import safe_get
from src.core.shell_handlers.base import GuiShellHandler, Lang


class GuiShellGenerico(GuiShellHandler):
    """Fallback para qualquer GuiShell sem handler especializado.

    Exibe apenas a identificação básica (ID, tipo, SubType). Não faz
    introspecção de conteúdo nem geração de código a partir de diff.
    """

    sap_type = "*"

    def inspecionar(self, obj: Any) -> dict[str, Any]:
        """Retorna identificação básica do controle."""
        return {
            "tipo": str(safe_get(obj, "Type", "GuiShell") or "GuiShell"),
            "subtype": str(safe_get(obj, "SubType", "") or ""),
            "id": str(safe_get(obj, "Id", "") or ""),
            "introspeccao": False,
            "nota": "Tipo sem handler dedicado — sem introspecção de conteúdo.",
        }

    def tirar_snapshot(self, obj: Any) -> dict[str, Any]:
        """Snapshot vazio: o handler genérico não detecta mudanças."""
        return {"tipo": "GuiShellGenerico"}

    def gerar_codigo(
        self,
        obj_id: str,
        antes: dict[str, Any],
        depois: dict[str, Any],
        lang: Lang,
    ) -> list[str]:
        """O handler genérico não gera código a partir de diff."""
        return []

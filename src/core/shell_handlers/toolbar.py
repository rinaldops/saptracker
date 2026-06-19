"""Handler para controles GuiToolbarControl."""

from __future__ import annotations

from typing import Any

from src.core.com_utils import safe_com_call, safe_get
from src.core.shell_handlers.base import GuiShellHandler, Lang


class GuiToolbarHandler(GuiShellHandler):
    """Handler especializado para controles GuiToolbarControl.

    Inspeciona os botões disponíveis, tooltips e estado de habilitação.
    Detecta clique de botão (mudança de pressed) para o Recorder.
    """

    sap_type = "GuiToolbarControl"

    def _buttons(self, obj: Any) -> list[dict[str, Any]]:
        """Enumera os botões da toolbar com seus metadados."""
        count = int(safe_get(obj, "ButtonCount", 0) or 0)
        buttons: list[dict[str, Any]] = []
        for i in range(count):
            buttons.append(
                {
                    "indice": i,
                    "id": str(safe_com_call(obj.GetButtonId, i, default="") or ""),
                    "tooltip": str(safe_com_call(obj.GetButtonTooltip, i, default="") or ""),
                    "texto": str(safe_com_call(obj.GetButtonText, i, default="") or ""),
                    "habilitado": bool(safe_com_call(obj.GetButtonEnabled, i, default=False)),
                    "tipo": str(safe_com_call(obj.GetButtonType, i, default="") or ""),
                }
            )
        return buttons

    def inspecionar(self, obj: Any) -> dict[str, Any]:
        """Retorna a lista de botões da toolbar."""
        buttons = self._buttons(obj)
        return {
            "tipo": "GuiToolbarControl",
            "total_botoes": len(buttons),
            "botoes": buttons,
        }

    def tirar_snapshot(self, obj: Any) -> dict[str, Any]:
        """Toolbars não mantêm estado entre cliques; snapshot mínimo.

        O clique em si é capturado via evento COM (``pressButton``) quando
        disponível; o snapshot serve apenas para identidade/estado de botões.
        """
        return {
            "tipo": "GuiToolbarControl",
            "total_botoes": int(safe_get(obj, "ButtonCount", 0) or 0),
        }

    def gerar_codigo(
        self,
        obj_id: str,
        antes: dict[str, Any],
        depois: dict[str, Any],
        lang: Lang,
    ) -> list[str]:
        """Cliques de toolbar vêm de eventos COM, não de diff de snapshot."""
        return []

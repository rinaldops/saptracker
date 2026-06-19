"""Handler para controles GuiCalendar."""

from __future__ import annotations

from typing import Any

from src.core.com_utils import safe_get
from src.core.shell_handlers.base import GuiShellHandler, Lang


class GuiCalendarHandler(GuiShellHandler):
    """Handler especializado para controles GuiCalendar.

    Inspeciona a data de foco, o intervalo de seleção e o primeiro dia visível.
    Detecta mudança de seleção para o Recorder.
    """

    sap_type = "GuiCalendar"

    def inspecionar(self, obj: Any) -> dict[str, Any]:
        """Retorna data de foco e intervalo de seleção do calendário."""
        return {
            "tipo": "GuiCalendar",
            "data_foco": str(safe_get(obj, "focusDate", "") or ""),
            "selecao_inicio": str(safe_get(obj, "selectionInterval", "") or ""),
            "primeiro_dia_visivel": str(safe_get(obj, "firstVisibleDate", "") or ""),
            "ultimo_dia_visivel": str(safe_get(obj, "lastVisibleDate", "") or ""),
        }

    def tirar_snapshot(self, obj: Any) -> dict[str, Any]:
        """Captura a seleção atual do calendário."""
        return {
            "tipo": "GuiCalendar",
            "data_foco": str(safe_get(obj, "focusDate", "") or ""),
            "selecao": str(safe_get(obj, "selectionInterval", "") or ""),
        }

    def gerar_codigo(
        self,
        obj_id: str,
        antes: dict[str, Any],
        depois: dict[str, Any],
        lang: Lang,
    ) -> list[str]:
        """Gera ``selectionInterval`` quando a seleção do calendário muda."""
        ref = self._ref(obj_id, lang)
        end = self._stmt_end(lang)
        sel_after = depois.get("selecao", "")
        if sel_after and sel_after != antes.get("selecao", ""):
            valor = self._str_lit(str(sel_after), lang)
            prop = "selectionInterval"
            return [f"{ref}.{prop} = {valor}{end}"]
        return []

"""Handler para controles GuiTextEdit (editor de texto multilinha)."""

from __future__ import annotations

from typing import Any

from src.core.com_utils import safe_com_call, safe_get
from src.core.shell_handlers.base import GuiShellHandler, Lang


class GuiTextEditHandler(GuiShellHandler):
    """Handler especializado para controles GuiTextEdit.

    Inspeciona número de linhas, primeira linha visível, texto selecionado e
    o conteúdo atual. Detecta mudança de conteúdo para o Recorder.
    """

    sap_type = "GuiTextEdit"

    def __init__(self, max_lines: int = 1000) -> None:
        self.max_lines = max_lines

    def _read_lines(self, obj: Any) -> list[str]:
        """Lê as linhas do editor via ``GetLineText`` até ``NumberOfLines``."""
        n = int(safe_get(obj, "NumberOfLines", 0) or 0)
        lines: list[str] = []
        for i in range(min(n, self.max_lines)):
            text = safe_com_call(obj.GetLineText, i, default="")
            lines.append("" if text is None else str(text))
        return lines

    def inspecionar(self, obj: Any) -> dict[str, Any]:
        """Retorna número de linhas e conteúdo atual do editor."""
        lines = self._read_lines(obj)
        return {
            "tipo": "GuiTextEdit",
            "numero_linhas": int(safe_get(obj, "NumberOfLines", 0) or 0),
            "primeira_visivel": int(safe_get(obj, "FirstVisibleLine", 0) or 0),
            "linha_atual": int(safe_get(obj, "CurrentLine", 0) or 0),
            "texto_selecionado": str(safe_get(obj, "SelectedText", "") or ""),
            "conteudo": "\n".join(lines),
            "linhas": lines,
        }

    def tirar_snapshot(self, obj: Any) -> dict[str, Any]:
        """Captura conteúdo completo para detectar edições."""
        lines = self._read_lines(obj)
        return {
            "tipo": "GuiTextEdit",
            "conteudo": "\n".join(lines),
            "numero_linhas": int(safe_get(obj, "NumberOfLines", 0) or 0),
        }

    def gerar_codigo(
        self,
        obj_id: str,
        antes: dict[str, Any],
        depois: dict[str, Any],
        lang: Lang,
    ) -> list[str]:
        """Gera ``SetSelectionIndexes``/``Text`` quando o conteúdo muda."""
        ref = self._ref(obj_id, lang)
        end = self._stmt_end(lang)
        conteudo_after = depois.get("conteudo", "")
        if conteudo_after == antes.get("conteudo", ""):
            return []

        # GuiTextEdit não expõe ``Text`` setável diretamente em todas as versões;
        # o padrão idiomático do Tracker é usar a propriedade ``text``.
        valor = self._str_lit(conteudo_after.replace("\n", "\\n"), lang)
        prop = "text" if lang in ("python",) else "Text"
        return [f"{ref}.{prop} = {valor}{end}"]

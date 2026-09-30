"""Handler para controles GuiGridView (ALV Grid)."""

from __future__ import annotations

from typing import Any

from src.core.com_utils import com_item, com_len, safe_com_call, safe_get
from src.core.shell_handlers.base import GuiShellHandler, Lang


class GuiGridViewHandler(GuiShellHandler):
    """Handler especializado para controles GuiGridView (ALV Grid).

    Implementa introspecção de colunas, linhas e células, além de detecção de
    mudanças de estado (célula atual e linhas selecionadas) para o Recorder.

    Attributes:
        max_rows: Número máximo de linhas inspecionadas para não travar a UI
            em grids muito grandes.
    """

    sap_type = "GuiGridView"

    def __init__(self, max_rows: int = 200) -> None:
        self.max_rows = max_rows

    # ------------------------------------------------------------------ #
    def _column_names(self, obj: Any) -> list[str]:
        """Retorna os nomes técnicos das colunas do grid."""
        col_collection = safe_com_call(lambda: obj.GetColumnOrder())
        names: list[str] = []
        for i in range(com_len(col_collection)):
            name = com_item(col_collection, i)
            if name is not None:
                names.append(str(name))
        if names:
            return names
        # Fallback: GetColumnNames retorna uma coleção de nomes técnicos.
        col_names = safe_com_call(lambda: obj.GetColumnNames())
        for i in range(com_len(col_names)):
            name = com_item(col_names, i)
            if name is not None:
                names.append(str(name))
        if not names:
            current_column = str(safe_get(obj, "CurrentCellColumn", "") or "")
            if current_column:
                names.append(current_column)
        return names

    def inspecionar(self, obj: Any) -> dict[str, Any]:
        """Retorna colunas e valores das células visíveis do grid.

        Alguns grids ALV (ex.: hospedados via container/Web Dynpro) não
        implementam ``GetColumnOrder``/``GetColumnNames`` via Scripting —
        nesse caso ``colunas`` cai para só a coluna com foco atual
        (``CurrentCellColumn``), embora ``ColumnCount`` possa reportar mais.
        ``colunas_completas`` sinaliza esse déficit em vez de escondê-lo: sem
        isso, a maior parte dos dados da tabela nunca é capturada e a busca
        (UI/CLI) não encontra nada nas colunas ausentes.

        Returns:
            Dicionário com ``"tipo"``, ``"colunas"``, ``"total_colunas"``,
            ``"colunas_completas"``, ``"linhas"``, ``"total"``,
            ``"celula_atual"`` e ``"linhas_selecionadas"``.
        """
        colunas = self._column_names(obj)
        total_colunas = int(safe_get(obj, "ColumnCount", len(colunas)) or len(colunas))
        row_count = int(safe_get(obj, "RowCount", 0) or 0)
        visible = min(row_count, self.max_rows)

        linhas: list[dict[str, str]] = []
        for r in range(visible):
            row: dict[str, str] = {}
            for col in colunas:
                value = safe_com_call(obj.GetCellValue, r, col, default="")
                row[col] = "" if value is None else str(value)
            linhas.append(row)

        return {
            "tipo": "GuiGridView",
            "colunas": colunas,
            "total_colunas": total_colunas,
            "colunas_completas": len(colunas) >= total_colunas,
            "linhas": linhas,
            "total": row_count,
            "exibidas": visible,
            "celula_atual": {
                "linha": int(safe_get(obj, "CurrentCellRow", -1) or -1),
                "coluna": str(safe_get(obj, "CurrentCellColumn", "") or ""),
            },
            "linhas_selecionadas": str(safe_get(obj, "SelectedRows", "") or ""),
            "primeira_visivel": int(safe_get(obj, "FirstVisibleRow", 0) or 0),
        }

    def tirar_snapshot(self, obj: Any) -> dict[str, Any]:
        """Captura estado leve: célula atual e linhas selecionadas."""
        return {
            "tipo": "GuiGridView",
            "celula_atual_linha": int(safe_get(obj, "CurrentCellRow", -1) or -1),
            "celula_atual_coluna": str(safe_get(obj, "CurrentCellColumn", "") or ""),
            "linhas_selecionadas": str(safe_get(obj, "SelectedRows", "") or ""),
            "primeira_visivel": int(safe_get(obj, "FirstVisibleRow", 0) or 0),
        }

    def gerar_codigo(
        self,
        obj_id: str,
        antes: dict[str, Any],
        depois: dict[str, Any],
        lang: Lang,
    ) -> list[str]:
        """Gera código para mudança de célula atual e/ou seleção de linhas."""
        ref = self._ref(obj_id, lang)
        end = self._stmt_end(lang)
        linhas: list[str] = []

        cell_changed = (
            antes.get("celula_atual_linha") != depois.get("celula_atual_linha")
            or antes.get("celula_atual_coluna") != depois.get("celula_atual_coluna")
        )
        if cell_changed and depois.get("celula_atual_linha", -1) >= 0:
            row = depois["celula_atual_linha"]
            col = self._str_lit(str(depois.get("celula_atual_coluna", "")), lang)
            linhas.append(f"{ref}.SetCurrentCell({row}, {col}){end}")

        sel_before = antes.get("linhas_selecionadas", "")
        sel_after = depois.get("linhas_selecionadas", "")
        if sel_after and sel_after != sel_before:
            sel = self._str_lit(str(sel_after), lang)
            if lang in ("python", "java"):
                linhas.append(f"{ref}.selectedRows = {sel}{end}"
                              if lang == "java" else f"{ref}.SelectedRows = {sel}")
            else:
                linhas.append(f"{ref}.SelectedRows = {sel}")
        return linhas

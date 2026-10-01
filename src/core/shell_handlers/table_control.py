"""Handler para tabelas classicas ``GuiTableControl`` do SAP GUI."""

from __future__ import annotations

import re
import time
from typing import Any

from src.core.com_utils import com_item, com_len, safe_com_call, safe_get
from src.core.table_capture import capture_table_pages
from src.core.shell_handlers.base import GuiShellHandler, Lang
from src.utils.logger import get_logger

_CELL_RE = re.compile(r"/(?P<kind>txt|chk)(?P<name>[^/\[]+)\[(?P<column>\d+),(?P<row>\d+)\]$")

# GuiTableControl não expõe necessariamente o cabeçalho visual pela API COM.
# Este mapeamento é explícito e restrito ao controle confirmado no diagnóstico.
logger = get_logger(__name__)

_TABLE_HEADERS = {
    "SAPMYS_MANUT_REGRAS_PEPTC_REGRAS": {"TI_REGRAS-BUKRS": "Empresa"},
}


class GuiTableControlHandler(GuiShellHandler):
    """Le e, opcionalmente, pagina todas as celulas de um Table Control."""

    sap_type = "GuiTableControl"

    @staticmethod
    def _read_visible(obj: Any, row_offset: int = 0) -> tuple[dict[int, str], dict[int, dict[str, str]]]:
        columns: dict[int, str] = {}
        rows: dict[int, dict[str, str]] = {}
        children = safe_get(obj, "Children")
        for i in range(com_len(children)):
            cell = com_item(children, i)
            if cell is None:
                continue
            match = _CELL_RE.search(str(safe_get(cell, "Id", "") or ""))
            if not match:
                continue
            column = int(match.group("column"))
            row = row_offset + int(match.group("row"))
            field = match.group("name")
            columns[column] = field
            value = safe_get(cell, "Text", "")
            if match.group("kind") == "chk":
                value = safe_get(cell, "Selected", value)
            rows.setdefault(row, {})[field] = "" if value is None else str(value)
        return columns, rows

    @staticmethod
    def _read_visible_cells(obj: Any) -> list[dict[str, Any]]:
        """Retorna os controles reais da viewport, sem criar linhas sintéticas."""
        cells: list[dict[str, Any]] = []
        children = safe_get(obj, "Children")
        for i in range(com_len(children)):
            cell = com_item(children, i)
            if cell is None:
                continue
            match = _CELL_RE.search(str(safe_get(cell, "Id", "") or ""))
            if not match:
                continue
            value = safe_get(cell, "Text", "")
            if match.group("kind") == "chk":
                value = safe_get(cell, "Selected", value)
            cells.append({
                "id": str(safe_get(cell, "Id", "") or ""),
                "tipo": str(safe_get(cell, "Type", "") or "GuiTextField"),
                "coluna": int(match.group("column")),
                "linha": int(match.group("row")),
                "nome": match.group("name"),
                "texto": "" if value is None else str(value),
            })
        return cells

    @staticmethod
    def _column_titles(obj: Any, columns: dict[int, str] | None = None) -> dict[int, str]:
        """Lê títulos por coleção ou método, quando o SAP os expõe."""
        result: dict[int, str] = {}
        collection = safe_get(obj, "Columns")
        for i in range(com_len(collection)):
            column = com_item(collection, i)
            if column is None:
                continue
            title = next(
                (safe_get(column, attr, "") for attr in ("Title", "Caption", "Text")
                 if safe_get(column, attr, "")),
                "",
            )
            if title:
                result[i] = str(title)
        for i in (columns or {}):
            if i in result:
                continue
            for method in ("GetColumnTitle", "GetColumnHeader", "GetColumnText"):
                value = safe_com_call(lambda method=method, i=i: getattr(obj, method)(i), default="")
                if value:
                    result[i] = str(value)
                    break
        return result

    @staticmethod
    def _result(
        columns: dict[int, str],
        rows: dict[int, dict[str, str]],
        total: int = 0,
        titles: dict[int, str] | None = None,
    ) -> dict[str, Any]:
        ordered_columns = [columns[i] for i in sorted(columns)]
        ordered_rows = [rows[i] for i in sorted(rows)]
        return {
            "tipo": "GuiTableControl",
            "colunas": ordered_columns,
            "titulos": [titles.get(i, "") for i in sorted(columns)] if titles else [],
            "linhas": ordered_rows,
            "total": total or len(ordered_rows),
        }

    def inspecionar(self, obj: Any) -> dict[str, Any]:
        """Retorna as células da página visível e seu estado de completude."""
        columns, rows = self._read_visible(obj)
        row_count = int(safe_get(obj, "RowCount", 0) or 0)
        result = self._result(columns, rows, row_count)
        result["celulas"] = self._read_visible_cells(obj)
        result["capturadas"] = len(rows)
        result["completa"] = not row_count or len(rows) >= row_count
        result["titulos"] = [self._column_titles(obj, columns).get(i, "") for i in sorted(columns)]
        return result

    def inspecionar_completo(self, obj: Any) -> dict[str, Any]:
        """Captura todas as linhas por páginas estáveis do ``GuiTableControl``."""
        table_id = str(safe_get(obj, "Id", "") or "")
        owner = obj
        for _ in range(3):
            parent = safe_get(owner, "Parent")
            if parent is None:
                break
            owner = parent
        session = owner if str(safe_get(owner, "Type", "")) == "GuiSession" else None

        def current_table() -> Any:
            logger.debug("table_capture FindById BEGIN id=%s", table_id)
            if session is not None and table_id:
                fresh = safe_com_call(lambda: session.FindById(table_id))
                logger.debug("table_capture FindById END found=%s", fresh is not None)
                if fresh is not None:
                    return fresh
            logger.debug("table_capture using original table reference")
            return obj

        table = current_table()
        logger.info("table_capture table_resolved type=%s", safe_get(table, "Type", ""))
        scrollbar = safe_get(table, "VerticalScrollbar")
        row_count = int(safe_get(table, "RowCount", 0) or 0)
        visible = int(safe_get(table, "VisibleRowCount", 0) or 0)
        if scrollbar is None or row_count <= 0 or visible <= 0:
            return self.inspecionar(obj)

        columns, initial_rows = self._read_visible(table)
        titles = self._column_titles(table, columns)
        maximum = safe_get(scrollbar, "Maximum", None)
        maximum = int(maximum) if maximum is not None else None
        original = safe_get(scrollbar, "Position", None)
        logger.info("table_capture dimensions rows=%s visible=%s maximum=%s original=%s", row_count, visible, maximum, original)

        spxlsap_used = [False]

        def read_page(_position: int) -> list[dict[str, Any]]:
            logger.info("table_capture page READ BEGIN requested=%s", _position)
            result: list[dict[str, Any]] = []
            sp_table = None
            if session is not None and table_id:
                try:
                    import win32com.client
                    logger.info("table_capture SPXLSAP Window BEGIN page=%s", _position)
                    sp_window = win32com.client.Dispatch("SPXLSAP.GuiMainWindow")
                    sp_window.Init(session, "wnd[0]")
                    logger.info("table_capture SPXLSAP Window END page=%s", _position)
                    sp_table = sp_window.GuiTable(table_id.rsplit("/", 1)[-1])
                    spxlsap_used[0] = True
                    logger.info("table_capture SPXLSAP GuiTable END page=%s", _position)
                except Exception as exc:
                    logger.exception("table_capture SPXLSAP FAILED page=%s: %s", _position, exc)
                    sp_table = None
            reader = sp_table or current_table()
            logger.info("table_capture reader=%s page=%s", "SPXLSAP" if sp_table is not None else "COM", _position)
            if not callable(safe_get(reader, "GetCell", None)):
                _, visible_rows = self._read_visible(reader)
                return [
                    {**visible_rows[i], "__sap_absolute_row": _position + i}
                    for i in sorted(visible_rows)
                ]
            for relative in range(visible):
                row: dict[str, Any] = {}
                for column, technical in sorted(columns.items()):
                    cell = None
                    # GetCell pode falhar enquanto o SAP troca a viewport.
                    # Repetir a c�lula evita transformar uma falha transit�ria
                    # em uma p�gina aparentemente vazia.
                    for _ in range(3):
                        cell = safe_com_call(lambda r=relative, c=column: reader.GetCell(r, c))
                        if cell is not None:
                            break
                        time.sleep(0.05)
                    if cell is None:
                        continue
                    value = safe_get(cell, "Text", "")
                    if str(safe_get(cell, "Type", "")) == "GuiCheckBox":
                        value = safe_get(cell, "Selected", value)
                    row[technical] = "" if value is None else str(value)
                # A posi��o f�sica existe mesmo quando todas as c�lulas est�o
                # vazias; isso preserva as 22 linhas por viewport.
                row["__sap_absolute_row"] = _position + relative
                result.append(row)
            logger.info("table_capture page READ END requested=%s cells=%s", _position, len(result))
            return result

        def set_position(position: int) -> None:
            logger.info("table_capture scrollbar SET BEGIN requested=%s", position)
            current_scrollbar = safe_get(current_table(), "VerticalScrollbar") or scrollbar
            logger.debug("table_capture scrollbar object resolved position_before=%s", safe_get(current_scrollbar, "Position", None))
            safe_com_call(lambda: setattr(current_scrollbar, "Position", position))
            logger.info("table_capture scrollbar SET END requested=%s effective=%s", position, safe_get(current_scrollbar, "Position", None))
            # SAP GUI atualiza os objetos de célula de forma assíncrona.
            time.sleep(0.08)

        try:
            page_counts: list[int] = []
            logger.info("table_capture pagination BEGIN")
            rows = capture_table_pages(
                read_page,
                row_count=row_count,
                visible_row_count=visible,
                maximum=maximum,
                set_position=set_position,
                row_key=lambda row: row.get("__sap_absolute_row"),
                page_counts=page_counts,
            )
        finally:
            # Com SPXLSAP, n�o reutilize o objeto de scrollbar COM antigo ap�s
            # uma captura longa: essa escrita provocava a queda do SAP GUI.
            # No caminho COM/fake, preservamos o contrato hist�rico e restauramos.
            if spxlsap_used[0]:
                logger.info("table_capture restore SKIP original=%s reason=spxlsap_stability", original)
            elif original is not None:
                logger.info("table_capture restore BEGIN original=%s", original)
                safe_com_call(lambda: setattr(scrollbar, "Position", original))
                logger.info("table_capture restore END effective=%s", safe_get(scrollbar, "Position", None))

        # Se GetCell não estiver disponível, preserva a página inicial lida
        # por Children em vez de retornar uma captura vazia.
        if not rows and initial_rows:
            rows = [initial_rows[i] for i in sorted(initial_rows)]
        name = str(safe_get(obj, "Id", "") or "").rsplit("/", 1)[-1].removeprefix("tbl")
        for index, technical in columns.items():
            if technical in _TABLE_HEADERS.get(name, {}):
                titles[index] = _TABLE_HEADERS[name][technical]
        for row in rows:
            row.pop("__sap_absolute_row", None)
        result = self._result(columns, {i: row for i, row in enumerate(rows)}, row_count, titles)
        result["paginas"] = page_counts if "page_counts" in locals() else []
        result["linhas_acumuladas"] = sum(result["paginas"])
        result["capturadas"] = len(rows)
        result["completa"] = len(rows) >= row_count
        logger.info("table_capture END pages=%s accumulated=%s captured=%s complete=%s", len(result["paginas"]), result["linhas_acumuladas"], result["capturadas"], result["completa"])
        return result
    def tirar_snapshot(self, obj: Any) -> dict[str, Any]:
        return {"tipo": self.sap_type}

    def gerar_codigo(self, obj_id: str, antes: dict[str, Any], depois: dict[str, Any], lang: Lang) -> list[str]:
        return []




















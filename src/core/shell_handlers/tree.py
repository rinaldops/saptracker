"""Handler para controles GuiTree (Simple, Column e List tree)."""

from __future__ import annotations

from typing import Any

from src.core.com_utils import com_item, com_len, safe_com_call, safe_get
from src.core.shell_handlers.base import GuiShellHandler, Lang


class GuiTreeHandler(GuiShellHandler):
    """Handler especializado para controles GuiTree.

    Inspeciona chaves de nós, texto por chave e hierarquia de filhos. Detecta
    seleção de nó para o Recorder.

    Limitação conhecida: ``GetAllNodeKeys()`` retorna apenas os nós atualmente
    carregados no controle. Nós não expandidos (lazy-load) podem não aparecer.
    """

    sap_type = "GuiTree"

    def __init__(self, max_nodes: int = 500) -> None:
        self.max_nodes = max_nodes

    # ------------------------------------------------------------------ #
    def _all_node_keys(self, obj: Any) -> list[str]:
        """Retorna as chaves de todos os nós carregados no controle."""
        keys = safe_com_call(lambda: obj.GetAllNodeKeys())
        result: list[str] = []
        for i in range(min(com_len(keys), self.max_nodes)):
            k = com_item(keys, i)
            if k is not None:
                result.append(str(k))
        return result

    def _column_names(self, obj: Any) -> list[str]:
        """Retorna nomes de coluna (apenas para column trees)."""
        cols = safe_com_call(lambda: obj.GetColumnNames())
        names: list[str] = []
        for i in range(com_len(cols)):
            c = com_item(cols, i)
            if c is not None:
                names.append(str(c))
        return names

    def inspecionar(self, obj: Any) -> dict[str, Any]:
        """Retorna nós (chave, texto, filhos) e colunas do tree."""
        keys = self._all_node_keys(obj)
        colunas = self._column_names(obj)

        nodes: list[dict[str, Any]] = []
        for key in keys:
            text = safe_com_call(obj.GetNodeTextByKey, key, default="")
            children = safe_com_call(obj.GetSubNodesCol, key)
            child_keys: list[str] = []
            for i in range(com_len(children)):
                ck = com_item(children, i)
                if ck is not None:
                    child_keys.append(str(ck))
            item_values: dict[str, str] = {}
            for col in colunas:
                val = safe_com_call(obj.GetItemText, key, col, default="")
                if val:
                    item_values[col] = str(val)
            nodes.append(
                {
                    "chave": key,
                    "texto": "" if text is None else str(text),
                    "filhos": child_keys,
                    "colunas": item_values,
                }
            )

        return {
            "tipo": "GuiTree",
            "colunas": colunas,
            "nos": nodes,
            "total": len(nodes),
            "no_selecionado": self._selected_key(obj),
        }

    def _selected_key(self, obj: Any) -> str:
        """Retorna a chave do nó atualmente selecionado, se houver."""
        selected = safe_com_call(lambda: obj.GetSelectedNodes())
        if com_len(selected):
            first = com_item(selected, 0)
            return "" if first is None else str(first)
        # Fallback: topNode/selectedNode dependem do subtype.
        return str(safe_get(obj, "selectedNode", "") or "")

    def tirar_snapshot(self, obj: Any) -> dict[str, Any]:
        """Captura o nó selecionado e o nó de topo visível."""
        return {
            "tipo": "GuiTree",
            "no_selecionado": self._selected_key(obj),
            "no_topo": str(safe_get(obj, "topNode", "") or ""),
        }

    def gerar_codigo(
        self,
        obj_id: str,
        antes: dict[str, Any],
        depois: dict[str, Any],
        lang: Lang,
    ) -> list[str]:
        """Gera ``SelectNode`` quando o nó selecionado muda."""
        ref = self._ref(obj_id, lang)
        end = self._stmt_end(lang)
        linhas: list[str] = []

        sel_after = depois.get("no_selecionado", "")
        if sel_after and sel_after != antes.get("no_selecionado", ""):
            key = self._str_lit(str(sel_after), lang)
            linhas.append(f"{ref}.SelectNode({key}){end}")
        return linhas

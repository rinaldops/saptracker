"""Analyser — percurso da árvore de objetos de uma sessão SAP GUI.

Constrói uma representação serializável (``ObjectNode``) da hierarquia de
objetos a partir de um ``GuiSession``, identificando controles GuiShell e
delegando sua introspecção ao handler apropriado. Também oferece o *highlight*
(``Visualize``) que desenha a moldura vermelha em torno de um objeto no SAP.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.core.com_utils import (
    com_item,
    com_len,
    get_clipboard_text,
    safe_com_call,
    safe_get,
    set_clipboard_text,
)
from src.core.shell_handlers import (
    get_handler,
    get_handler_for_type,
    is_supported_shell,
    normalize_shell_type,
)
from src.core.shell_handlers.grid_view import ensure_grid_rows_loaded
from src.utils.logger import get_logger

logger = get_logger(__name__)

#: Profundidade máxima de recursão para evitar loops em hierarquias anômalas.
MAX_DEPTH = 64

#: Máximo de linhas/itens de conteúdo de um GuiShell exibidos na árvore (o
#: conteúdo completo continua disponível no painel de detalhes via ``inspect``).
SHELL_TREE_MAX_ITEMS = 50

ProgressCallback = Callable[[int, int], None]


@dataclass
class ObjectNode:
    """Nó da árvore de objetos SAP.

    Attributes:
        id: ID completo (ex: ``wnd[0]/usr/cntlGRID1/shellcont/shell``).
        type: Tipo SAP (ex: ``GuiGridView``).
        name: Nome do objeto.
        text: Texto/rótulo do objeto.
        top, left, width, height: Posição e dimensões em pixels (0 se N/A).
        is_shell: ``True`` se o objeto é um GuiShell.
        shell_supported: ``True`` se há handler dedicado para o tipo.
        children: Subnós.
    """

    id: str
    type: str
    name: str = ""
    text: str = ""
    top: int = 0
    left: int = 0
    width: int = 0
    height: int = 0
    is_shell: bool = False
    shell_supported: bool = False
    children: list[ObjectNode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serializa o nó (e subárvore) para um dicionário JSON-friendly."""
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "text": self.text,
            "top": self.top,
            "left": self.left,
            "width": self.width,
            "height": self.height,
            "is_shell": self.is_shell,
            "shell_supported": self.shell_supported,
            "children": [c.to_dict() for c in self.children],
        }

    def flatten(self) -> list[ObjectNode]:
        """Retorna todos os nós da subárvore em pré-ordem (inclui ``self``)."""
        result = [self]
        for child in self.children:
            result.extend(child.flatten())
        return result


class Analyser:
    """Percorre a árvore de objetos de uma sessão SAP e a inspeciona.

    Args:
        session: Objeto COM ``GuiSession`` a ser analisado.
    """

    def __init__(self, session: Any) -> None:
        self._session = session

    # ------------------------------------------------------------------ #
    # Percurso da árvore
    # ------------------------------------------------------------------ #
    def build_tree(self, progress_callback: ProgressCallback | None = None) -> ObjectNode:
        """Constrói a árvore de objetos a partir da sessão.

        Quando ``progress_callback`` é informado, faz uma contagem leve da
        hierarquia COM e reporta ``(processados, total)`` durante o percurso.

        Returns:
            Nó raiz representando a própria sessão (com as janelas como filhos).
        """
        root = ObjectNode(
            id=str(safe_get(self._session, "Id", "session") or "session"),
            type=str(safe_get(self._session, "Type", "GuiSession") or "GuiSession"),
            name=str(safe_get(self._session, "Name", "") or ""),
            text="Sessão SAP",
        )
        children = safe_get(self._session, "Children")
        total = 1 + self._count_nodes(children, depth=0) if progress_callback else 0
        processed = [1]
        if progress_callback is not None:
            progress_callback(0, total)
            progress_callback(1, total)
        self._append_children(
            root,
            children,
            depth=0,
            progress_callback=progress_callback,
            processed=processed,
            total=total,
        )
        if progress_callback is not None:
            progress_callback(total, total)
        todos = root.flatten()
        shells = [n for n in todos if n.is_shell]
        logger.debug(
            "Árvore construída: %d nós, %d shells (%d com handler dedicado).",
            len(todos), len(shells), sum(1 for n in shells if n.shell_supported),
        )
        return root

    def _count_nodes(self, collection: Any, depth: int) -> int:
        """Conta a hierarquia COM sem executar introspecção de GuiShell."""
        if collection is None or depth >= MAX_DEPTH:
            return 0
        total = 0
        for index in range(com_len(collection)):
            obj = com_item(collection, index)
            if obj is None:
                continue
            total += 1
            total += self._count_nodes(safe_get(obj, "Children"), depth + 1)
        return total

    def _append_children(
        self,
        parent: ObjectNode,
        collection: Any,
        depth: int,
        progress_callback: ProgressCallback | None = None,
        processed: list[int] | None = None,
        total: int = 0,
    ) -> None:
        """Itera sobre uma ``GuiComponentCollection`` adicionando subnós."""
        if collection is None or depth >= MAX_DEPTH:
            return
        for i in range(com_len(collection)):
            obj = com_item(collection, i)
            if obj is None:
                continue
            node = self._node_from_obj(obj)
            parent.children.append(node)
            # Conteúdo interno de GuiShell (colunas, linhas, nós, botões) não
            # vem por ``Children`` COM — é introspectado pelo handler dedicado.
            if node.shell_supported:
                self._append_shell_content(node, obj)
            if progress_callback is not None and processed is not None:
                processed[0] += 1
                progress_callback(processed[0], total)
            # Recursão apenas em containers (objetos com Children).
            sub = safe_get(obj, "Children")
            if sub is not None:
                self._append_children(
                    node,
                    sub,
                    depth + 1,
                    progress_callback,
                    processed,
                    total,
                )

    def _node_from_obj(self, obj: Any) -> ObjectNode:
        """Cria um ``ObjectNode`` a partir de um objeto COM SAP."""
        sap_type = str(safe_get(obj, "Type", "") or "")
        subtype = str(safe_get(obj, "SubType", "") or "")
        is_shell = sap_type == "GuiShell" or self._has_shell_interface(obj, sap_type)
        # Para GuiShell, o tipo real vem do SubType (ex.: "Tree" -> "GuiTree").
        eff_type = normalize_shell_type(sap_type, subtype) if sap_type == "GuiShell" else sap_type
        supported = is_shell and is_supported_shell(eff_type)

        if is_shell:
            logger.debug(
                "Shell detectado: id=%s Type=%r SubType=%r -> tipo=%r suportado=%s",
                safe_get(obj, "Id", ""), sap_type, subtype, eff_type, supported,
            )

        return ObjectNode(
            id=str(safe_get(obj, "Id", "") or ""),
            type=eff_type,
            name=str(safe_get(obj, "Name", "") or ""),
            text=str(safe_get(obj, "Text", "") or ""),
            top=int(safe_get(obj, "Top", 0) or 0),
            left=int(safe_get(obj, "Left", 0) or 0),
            width=int(safe_get(obj, "Width", 0) or 0),
            height=int(safe_get(obj, "Height", 0) or 0),
            is_shell=is_shell,
            shell_supported=supported,
        )

    @staticmethod
    def _has_shell_interface(obj: Any, sap_type: str) -> bool:
        """Heurística para detectar controles GuiShell por suas propriedades."""
        if sap_type.startswith("GuiGridView") or sap_type in (
            "GuiTree",
            "GuiTextEdit",
            "GuiCalendar",
            "GuiToolbarControl",
        ):
            return True
        # GuiShell genuíno expõe SubType.
        return safe_get(obj, "SubType", None) is not None and sap_type.startswith("Gui")

    # ------------------------------------------------------------------ #
    # Conteúdo interno de GuiShell como nós da árvore
    # ------------------------------------------------------------------ #
    def _append_shell_content(self, node: ObjectNode, obj: Any) -> None:
        """Anexa o conteúdo interno do GuiShell como filhos de ``node``.

        A introspecção é *best-effort*: qualquer falha (objeto sumiu, método
        indisponível) apenas deixa o nó sem conteúdo, sem interromper a árvore.
        """
        handler = get_handler_for_type(node.type)
        try:
            data = handler.inspecionar(obj)
            filhos = self._shell_content_nodes(node.type, data, node.id)
            node.children.extend(filhos)
            logger.debug(
                "Conteúdo do shell %s (%s via %s): %d nós de conteúdo.",
                node.id, node.type, type(handler).__name__, len(filhos),
            )
        except Exception as e:  # noqa: BLE001 - introspecção é best-effort
            logger.warning("Falha ao listar conteúdo do shell %s (%s): %s",
                           node.id, node.type, e)

    def _shell_content_nodes(
        self, shell_type: str, data: dict[str, Any], parent_id: str
    ) -> list[ObjectNode]:
        """Converte a introspecção de um handler em nós de árvore legíveis.

        Os nós sintéticos herdam o ``id`` do shell pai, de modo que selecioná-los
        ainda exibe os detalhes completos do controle no painel lateral.
        """
        if shell_type == "GuiGridView":
            return self._grid_nodes(data, parent_id)
        if shell_type == "GuiTree":
            return self._tree_nodes(data, parent_id)
        if shell_type == "GuiTextEdit":
            linhas = data.get("linhas", [])
            return [
                ObjectNode(id=parent_id, type="GuiTextLine", text=f"[{i}] {linha}")
                for i, linha in enumerate(linhas[:SHELL_TREE_MAX_ITEMS])
            ]
        if shell_type == "GuiCalendar":
            return [
                ObjectNode(id=parent_id, type="GuiCalendarInfo",
                           text=f"Data de foco: {data.get('data_foco', '')}"),
                ObjectNode(id=parent_id, type="GuiCalendarInfo",
                           text=f"Seleção: {data.get('selecao_inicio', '')}"),
            ]
        if shell_type == "GuiToolbarControl":
            return [
                ObjectNode(
                    id=parent_id,
                    type="GuiToolbarButton",
                    text=f"{b.get('id', '')}: {b.get('tooltip', '') or b.get('texto', '')}",
                )
                for b in data.get("botoes", [])
            ]
        return []

    def _grid_nodes(self, data: dict[str, Any], parent_id: str) -> list[ObjectNode]:
        """Nós de colunas e linhas (amostra) de um GuiGridView.

        Quando ``colunas_completas`` é ``False`` (grid cuja API de Scripting
        não expõe todas as colunas — ver
        :meth:`GuiGridViewHandler.inspecionar`), acrescenta um nó de aviso
        visível/pesquisável em vez de deixar a lacuna invisível: sem isso, a
        maior parte dos dados da tabela nunca aparece na árvore/snapshot nem
        na busca, dando a falsa impressão de que o grid só tem 1 coluna.
        """
        nodes: list[ObjectNode] = []
        colunas: list[str] = data.get("colunas", [])
        total_colunas = int(data.get("total_colunas", len(colunas)))
        if colunas:
            grupo = ObjectNode(
                id=parent_id, type="GuiGridColumns", text=f"Colunas ({len(colunas)})"
            )
            grupo.children = [
                ObjectNode(id=parent_id, type="GuiGridColumn", text=str(c)) for c in colunas
            ]
            if not data.get("colunas_completas", True):
                grupo.children.append(
                    ObjectNode(
                        id=parent_id,
                        type="GuiGridColumnsAviso",
                        text=(
                            f"⚠ Apenas {len(colunas)} de {total_colunas} colunas capturadas "
                            "— este grid não expõe GetColumnOrder/GetColumnNames via "
                            "Scripting; use inspect para tentar a coluna em foco."
                        ),
                    )
                )
            nodes.append(grupo)

        linhas: list[dict[str, str]] = data.get("linhas", [])
        total = int(data.get("total", len(linhas)))
        if linhas:
            grupo = ObjectNode(id=parent_id, type="GuiGridRows", text=f"Linhas ({total})")
            for i, linha in enumerate(linhas[:SHELL_TREE_MAX_ITEMS]):
                valores = " | ".join(str(linha.get(c, "")) for c in colunas) if colunas \
                    else " | ".join(str(v) for v in linha.values())
                grupo.children.append(
                    ObjectNode(
                        id=parent_id, type="GuiGridRow", name=str(i), text=f"[{i}] {valores}"
                    )
                )
            if len(linhas) > SHELL_TREE_MAX_ITEMS:
                restante = len(linhas) - SHELL_TREE_MAX_ITEMS
                grupo.children.append(
                    ObjectNode(id=parent_id, type="GuiGridRow",
                               text=f"... (+{restante} linhas — ver detalhes)")
                )
            nodes.append(grupo)
        return nodes

    def _tree_nodes(self, data: dict[str, Any], parent_id: str) -> list[ObjectNode]:
        """Reconstrói a hierarquia de nós de um GuiTree a partir das chaves.

        O rótulo inclui os valores de ``colunas`` (ex.: ``TECH_KEY``), não só
        ``texto`` — em árvores de projeto SAP PS, o código real do objeto
        (rede/atividade/elemento de tarefa) costuma estar numa coluna oculta,
        não no texto visível. Sem isso, esse código não aparece em nenhum
        campo pesquisável (nem na árvore da UI, nem no ``snapshot`` da CLI).
        """
        nos: list[dict[str, Any]] = data.get("nos", [])
        por_chave: dict[str, ObjectNode] = {}
        for no in nos:
            chave = str(no.get("chave", ""))
            texto = str(no.get("texto", ""))
            colunas_vals = [str(v) for v in (no.get("colunas") or {}).values() if v]
            partes = [p for p in (texto, " | ".join(colunas_vals)) if p]
            rotulo = f"{chave}: {' | '.join(partes)}" if partes else chave
            por_chave[chave] = ObjectNode(id=parent_id, type="GuiTreeNode", name=chave, text=rotulo)

        filhos_de: set[str] = set()
        for no in nos:
            chave = str(no.get("chave", ""))
            for ck in no.get("filhos", []):
                ck = str(ck)
                if ck in por_chave and ck != chave:
                    por_chave[chave].children.append(por_chave[ck])
                    filhos_de.add(ck)
        return [on for chave, on in por_chave.items() if chave not in filhos_de]

    # ------------------------------------------------------------------ #
    # Inspeção de detalhes (delegada aos handlers)
    # ------------------------------------------------------------------ #
    def inspect(self, obj_id: str) -> dict[str, Any]:
        """Inspeciona um objeto por ID, usando o handler de GuiShell se aplicável.

        Returns:
            Dicionário de detalhes. Para GuiShell suportado, contém a
            introspecção rica do handler; caso contrário, dados básicos.
        """
        obj = self.find_by_id(obj_id)
        if obj is None:
            return {"erro": f"Objeto não encontrado: {obj_id}"}

        sap_type = str(safe_get(obj, "Type", "") or "")
        details: dict[str, Any] = {
            "id": str(safe_get(obj, "Id", "") or ""),
            "type": sap_type,
            "name": str(safe_get(obj, "Name", "") or ""),
            "text": str(safe_get(obj, "Text", "") or ""),
        }
        handler = get_handler(obj)
        # Só delega introspecção rica a handlers dedicados (não ao genérico)
        # quando o objeto realmente parece um GuiShell.
        try:
            shell_details = handler.inspecionar(obj)
            details["shell"] = shell_details
        except Exception as e:  # noqa: BLE001 - introspecção é best-effort
            logger.debug("Introspecção do handler falhou para %s: %s", obj_id, e)
        return details

    def find_by_id(self, obj_id: str) -> Any | None:
        """Retorna o objeto COM por ID via ``session.FindById`` (tolerante)."""
        return safe_com_call(lambda: self._session.FindById(obj_id, False)) or safe_com_call(
            lambda: self._session.FindById(obj_id)
        )

    # ------------------------------------------------------------------ #
    # Highlight (Visualize)
    # ------------------------------------------------------------------ #
    def highlight(self, obj_id: str, *, on: bool = True) -> bool:
        """Desenha (ou remove) a moldura vermelha em torno do objeto.

        Usa o método ``Visualize(on)`` exposto por objetos visuais do SAP GUI.

        Returns:
            ``True`` se o comando foi enviado com sucesso.
        """
        obj = self.find_by_id(obj_id)
        if obj is None:
            return False
        result = safe_com_call(lambda: obj.Visualize(on))
        return result is not None

    # ------------------------------------------------------------------ #
    # Seleção de nó (GuiTree)
    # ------------------------------------------------------------------ #
    def select_node(self, obj_id: str, key: str) -> bool:
        """Seleciona um nó de uma ``GuiTree`` pela chave (``SelectNode``).

        ``GuiTree`` não expõe ``Visualize`` por nó (só o controle inteiro tem
        posição própria) — ``SelectNode`` é o equivalente da API para apontar
        para um nó específico: seleciona e rola até ele.

        Returns:
            ``True`` se, após o comando, o nó selecionado passou a ser ``key``
            (``SelectNode`` não expõe erro próprio, então a confirmação é lida
            de volta via ``GetSelectedNodes``).
        """
        obj = self.find_by_id(obj_id)
        if obj is None:
            return False
        safe_com_call(lambda: obj.SelectNode(key))
        selected = safe_com_call(lambda: obj.GetSelectedNodes())
        if selected is None:
            return False
        return any(str(com_item(selected, i)) == key for i in range(com_len(selected)))

    # ------------------------------------------------------------------ #
    # Seleção de linha (GuiGridView)
    # ------------------------------------------------------------------ #
    def select_row(self, obj_id: str, row: int) -> bool:
        """Seleciona uma linha de uma ``GuiGridView`` (célula atual + seleção).

        ``GuiGridView`` também não expõe ``Visualize`` por linha — usa o
        mesmo par ``SetCurrentCell``/``SelectedRows`` que o Recorder já grava
        como ``set_current_cell``/``set_selected_rows``: o primeiro rola até a
        linha e move o foco; o segundo desenha a seleção (barra de destaque).

        Returns:
            ``True`` se, após o comando, ``CurrentCellRow`` passou a ser
            ``row`` (``SetCurrentCell`` não expõe erro próprio).
        """
        obj = self.find_by_id(obj_id)
        if obj is None:
            return False
        safe_com_call(lambda: obj.SetCurrentCell(row, ""))
        safe_com_call(lambda: setattr(obj, "SelectedRows", str(row)))
        atual = safe_get(obj, "CurrentCellRow", -1)
        return bool(atual == row)

    # ------------------------------------------------------------------ #
    # Cópia de tabela via clipboard (fallback para colunas não enumeráveis)
    # ------------------------------------------------------------------ #
    def copy_grid_table(self, obj_id: str) -> list[list[str]] | None:
        """Copia a grade inteira de uma ``GuiGridView`` via clipboard.

        Fallback para quando ``GetColumnOrder``/``GetColumnNames`` não estão
        disponíveis (ver ``GuiGridColumnsAviso`` em :meth:`_grid_nodes`) — em
        vez de ler célula a célula por nome de coluna (que exigiria já saber
        os nomes técnicos), usa a mesma ação que o menu de contexto do SAP
        oferece ao usuário: selecionar tudo e copiar. Recupera 100% das
        linhas/colunas mesmo quando a introspecção por nome não funciona.

        O SAP GUI só busca do servidor 1-2 "páginas" de linhas por vez — sem
        forçar o carregamento de todas antes de copiar, linhas além da(s)
        primeira(s) página(s) viriam vazias (grids grandes, ex.: milhares de
        linhas). Por isso rola o grid inteiro (:func:`ensure_grid_rows_loaded`)
        antes de selecionar e copiar.

        Efeitos colaterais (por operar via UI, não introspecção): rola e
        seleciona todas as linhas do grid na tela (visível ao usuário) e usa a
        área de transferência do Windows — o conteúdo anterior é restaurado ao
        final.

        Returns:
            Lista de linhas (cada uma como lista de valores, na ordem exibida
            na tela — sem nomes de coluna), ou ``None`` se o objeto não
            existir ou nada tiver sido copiado.
        """
        obj = self.find_by_id(obj_id)
        if obj is None:
            return None
        ensure_grid_rows_loaded(obj)
        anterior = get_clipboard_text()
        try:
            safe_com_call(lambda: obj.SelectAll())
            safe_com_call(lambda: obj.ContextMenu())
            safe_com_call(lambda: obj.SelectContextMenuItemByPosition("0"))
            texto = get_clipboard_text()
        finally:
            set_clipboard_text(anterior)
        if not texto:
            return None
        return [linha.split("\t") for linha in texto.splitlines() if linha.strip()]

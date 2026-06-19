"""Analyser — percurso da árvore de objetos de uma sessão SAP GUI.

Constrói uma representação serializável (``ObjectNode``) da hierarquia de
objetos a partir de um ``GuiSession``, identificando controles GuiShell e
delegando sua introspecção ao handler apropriado. Também oferece o *highlight*
(``Visualize``) que desenha a moldura vermelha em torno de um objeto no SAP.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.core.com_utils import safe_com_call, safe_get
from src.core.shell_handlers import get_handler, is_supported_shell
from src.utils.logger import get_logger

logger = get_logger(__name__)

#: Profundidade máxima de recursão para evitar loops em hierarquias anômalas.
MAX_DEPTH = 64


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
    children: list["ObjectNode"] = field(default_factory=list)

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

    def flatten(self) -> list["ObjectNode"]:
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
    def build_tree(self) -> ObjectNode:
        """Constrói a árvore de objetos a partir da sessão.

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
        self._append_children(root, children, depth=0)
        return root

    def _append_children(self, parent: ObjectNode, collection: Any, depth: int) -> None:
        """Itera sobre uma ``GuiComponentCollection`` adicionando subnós."""
        if collection is None or depth >= MAX_DEPTH:
            return
        count = int(safe_get(collection, "Count", 0) or 0)
        for i in range(count):
            obj = safe_com_call(collection.ElementAt, i)
            if obj is None:
                continue
            node = self._node_from_obj(obj)
            parent.children.append(node)
            # Recursão apenas em containers (objetos com Children).
            sub = safe_get(obj, "Children")
            if sub is not None:
                self._append_children(node, sub, depth + 1)

    def _node_from_obj(self, obj: Any) -> ObjectNode:
        """Cria um ``ObjectNode`` a partir de um objeto COM SAP."""
        sap_type = str(safe_get(obj, "Type", "") or "")
        is_shell = sap_type == "GuiShell" or self._has_shell_interface(obj, sap_type)
        # Para GuiShell, o tipo "real" vem de SubType/SubTypeAsText quando o
        # Type genérico é "GuiShell".
        effective_type = sap_type
        if sap_type == "GuiShell":
            subtype = str(safe_get(obj, "SubType", "") or "")
            if subtype:
                effective_type = subtype

        return ObjectNode(
            id=str(safe_get(obj, "Id", "") or ""),
            type=effective_type,
            name=str(safe_get(obj, "Name", "") or ""),
            text=str(safe_get(obj, "Text", "") or ""),
            top=int(safe_get(obj, "Top", 0) or 0),
            left=int(safe_get(obj, "Left", 0) or 0),
            width=int(safe_get(obj, "Width", 0) or 0),
            height=int(safe_get(obj, "Height", 0) or 0),
            is_shell=is_shell,
            shell_supported=is_shell and is_supported_shell(effective_type),
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

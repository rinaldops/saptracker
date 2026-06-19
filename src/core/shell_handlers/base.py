"""Interface base para handlers de controles GuiShell.

Cada subclasse de GuiShell (GuiGridView, GuiTree, ...) recebe um handler
dedicado que implementa três responsabilidades (seção 2.4 da spec):

* :meth:`inspecionar` — conteúdo interno para o Analyser.
* :meth:`tirar_snapshot` — estado atual para o sistema de diff do Recorder.
* :meth:`gerar_codigo` — linhas de código correspondentes a uma mudança.

Os handlers são *stateless* em relação a um objeto específico: recebem o objeto
COM em cada chamada. Isso permite reutilizar uma única instância por tipo.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

# Linguagens reconhecidas pelos handlers ao gerar código a partir de diffs.
# Mantido alinhado com ``src.codegen`` (inclui VBA além da spec original).
Lang = str


class GuiShellHandler(ABC):
    """Classe abstrata para todos os handlers de GuiShell.

    Attributes:
        sap_type: Nome do tipo SAP tratado por este handler (ex: ``"GuiGridView"``).
    """

    #: Tipo SAP tratado (sobrescrever em subclasses concretas).
    sap_type: str = ""

    @abstractmethod
    def inspecionar(self, obj: Any) -> dict[str, Any]:
        """Inspeciona o controle e retorna seu conteúdo interno.

        Args:
            obj: Objeto COM do controle (obtido via ``session.FindById``).

        Returns:
            Dicionário com os dados internos para exibição no Analyser.
            Deve sempre conter ao menos a chave ``"tipo"``.
        """
        raise NotImplementedError

    @abstractmethod
    def tirar_snapshot(self, obj: Any) -> dict[str, Any]:
        """Captura o estado atual do controle para o sistema de diff.

        Deve retornar apenas dados comparáveis e baratos de obter — o snapshot
        é tirado repetidamente pela thread de polling.
        """
        raise NotImplementedError

    @abstractmethod
    def gerar_codigo(
        self,
        obj_id: str,
        antes: dict[str, Any],
        depois: dict[str, Any],
        lang: Lang,
    ) -> list[str]:
        """Compara dois snapshots e retorna linhas de código da mudança.

        Args:
            obj_id: ID completo do objeto SAP (``wnd[0]/usr/.../shell``).
            antes: Snapshot anterior (estado prévio).
            depois: Snapshot atual (novo estado).
            lang: Linguagem alvo (ver :data:`src.codegen.LANGUAGES`).

        Returns:
            Lista de linhas de código. Vazia se não houve mudança relevante.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # Helpers comuns de geração de código por linguagem
    # ------------------------------------------------------------------ #
    @staticmethod
    def _ref(obj_id: str, lang: Lang) -> str:
        """Gera a expressão que referencia o objeto na linguagem alvo.

        Centraliza a forma idiomática de ``FindById`` por linguagem para que
        os handlers gerem código consistente com os geradores de ``codegen``.
        """
        find = f'FindById("{obj_id}")'
        if lang in ("python",):
            return f"session.{find}"
        if lang in ("vbscript", "vba"):
            return f"session.{find}"
        if lang == "powershell":
            return f"$Session.{find}"
        if lang == "autoit":
            return f"$oSession.{find}"
        if lang == "java":
            return f"session.{find}"
        return f"session.{find}"

    @staticmethod
    def _stmt_end(lang: Lang) -> str:
        """Terminador de instrução para a linguagem (``;`` em Java)."""
        return ";" if lang == "java" else ""

    @staticmethod
    def _str_lit(value: str, lang: Lang) -> str:
        """Literal de string idiomático por linguagem."""
        escaped = value.replace('"', '""' if lang in ("vbscript", "vba") else '\\"')
        return f'"{escaped}"'

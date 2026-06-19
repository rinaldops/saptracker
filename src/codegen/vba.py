"""Gerador de código VBA (.bas) — público-alvo prioritário.

Mesma renderização de instruções da família VB, mas o script é envolvido em
``Sub Macro() ... End Sub`` com declaração ``Dim`` das variáveis de objeto, de
modo que possa ser colado direto num módulo do Excel/Access VBA.
"""

from __future__ import annotations

from src.codegen.base import SessionInfoLite
from src.codegen.vb_base import VBBaseGenerator


class VBAGenerator(VBBaseGenerator):
    """Gera macros VBA que automatizam o SAP GUI via COM."""

    language = "vba"
    display_name = "VBA (Excel/Access)"
    file_extension = ".bas"

    #: indentação aplicada às linhas do corpo (dentro do ``Sub``).
    _indent = "    "

    def gerar_cabecalho(self, info: SessionInfoLite) -> str:
        c = self.comment_prefix
        return (
            f"{c} Macro gerada por SAP GUI Scripting Tool\n"
            f"{c} Sistema: {info.system}  Mandante: {info.client}  "
            f"Usuário: {info.user}  Transação: {info.transaction}\n"
            "Sub SAP_Macro()\n"
            f"{self._indent}Dim SapGuiAuto As Object, application As Object\n"
            f"{self._indent}Dim connection As Object, {self.session_var} As Object\n"
            f"{self._indent}Set SapGuiAuto = GetObject(\"SAPGUI\")\n"
            f"{self._indent}Set application = SapGuiAuto.GetScriptingEngine\n"
            f"{self._indent}Set connection = application.Children({info.connection_index})\n"
            f"{self._indent}Set {self.session_var} = "
            f"connection.Children({info.session_index})"
        )

    def gerar_rodape(self) -> str:
        return (
            f"{self._indent}{self.comment_prefix} Fim da macro\n"
            f'{self._indent}MsgBox "Macro concluída."\n'
            "End Sub\n"
        )

    def gerar_linha(self, acao: object) -> str:
        """Renderiza a ação e indenta cada linha para dentro do ``Sub``."""
        linha = super().gerar_linha(acao)  # type: ignore[arg-type]
        if not linha:
            return linha
        return "\n".join(self._indent + ln if ln else ln for ln in linha.split("\n"))

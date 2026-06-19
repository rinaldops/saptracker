"""Gerador de código VBScript (.vbs).

Roda solto via ``cscript``/``wscript``. Conexão por ``GetObject("SAPGUI")``.
"""

from __future__ import annotations

from src.codegen.base import SessionInfoLite
from src.codegen.vb_base import VBBaseGenerator


class VBScriptGenerator(VBBaseGenerator):
    """Gera scripts VBScript que automatizam o SAP GUI via COM."""

    language = "vbscript"
    display_name = "VBScript"
    file_extension = ".vbs"

    def gerar_cabecalho(self, info: SessionInfoLite) -> str:
        c = self.comment_prefix
        return (
            f"{c} Script gerado por SAP GUI Scripting Tool\n"
            f"{c} Sistema: {info.system}  Mandante: {info.client}  "
            f"Usuário: {info.user}  Transação: {info.transaction}\n"
            'If Not IsObject(application) Then\n'
            '   Set SapGuiAuto = GetObject("SAPGUI")\n'
            "   Set application = SapGuiAuto.GetScriptingEngine\n"
            "End If\n"
            f"Set connection = application.Children({info.connection_index})\n"
            f"Set {self.session_var} = connection.Children({info.session_index})\n"
        )

    def gerar_rodape(self) -> str:
        return f'{self.comment_prefix} Fim do script\nMsgBox "Script concluído."\n'

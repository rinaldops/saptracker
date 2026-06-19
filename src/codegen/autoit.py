"""Gerador de código AutoIt (.au3).

Estilo dot-call com parênteses sobre objetos COM. A conexão usa
``ObjGet("SAPGUI")``. Strings AutoIt escapam a aspa dupla dobrando-a.
Diálogos Win32 nativos usam as funções internas do AutoIt.
"""

from __future__ import annotations

from src.codegen.base import CodeGenerator, SessionInfoLite


class AutoItGenerator(CodeGenerator):
    """Gera scripts AutoIt que automatizam o SAP GUI via COM."""

    language = "autoit"
    display_name = "AutoIt"
    file_extension = ".au3"
    session_var = "$session"
    stmt_end = ""
    comment_prefix = ";"
    bool_true = "True"
    bool_false = "False"

    def gerar_cabecalho(self, info: SessionInfoLite) -> str:
        c = self.comment_prefix
        return (
            f"{c} Script gerado por SAP GUI Scripting Tool\n"
            f"{c} Sistema: {info.system}  Mandante: {info.client}  "
            f"Usuário: {info.user}  Transação: {info.transaction}\n"
            '$SapGuiAuto = ObjGet("SAPGUI")\n'
            "$application = $SapGuiAuto.GetScriptingEngine\n"
            f"$connection = $application.Children({info.connection_index})\n"
            f"{self.session_var} = $connection.Children({info.session_index})\n"
        )

    def gerar_rodape(self) -> str:
        return f'{self.comment_prefix} Fim do script\nConsoleWrite("Script concluído." & @CRLF)\n'

    def _str_lit(self, value: str) -> str:
        """Literal AutoIt: aspas duplas, dobrando a aspa interna."""
        return '"' + value.replace('"', '""') + '"'

    def _render_win32(self, dialog: object) -> list[str]:
        d = dialog  # type: ignore[assignment]
        linhas = [f'WinWait("{d.title}", "", {d.timeout})']  # type: ignore[attr-defined]
        for ctrl in d.controls:  # type: ignore[attr-defined]
            linhas.append(
                f'ControlSetText("{d.title}", "", '  # type: ignore[attr-defined]
                f'"{ctrl.control}", "{ctrl.text}")'
            )
        if d.button:  # type: ignore[attr-defined]
            linhas.append(
                f'ControlClick("{d.title}", "", "{d.button}")'  # type: ignore[attr-defined]
            )
        return linhas

"""Gerador de código PowerShell.

Estilo dot-call com parênteses. A conexão usa ``GetActiveObject("SAPGUI")``
da interop .NET. Strings são renderizadas como literais com aspas simples
(seguro contra ``$`` de interpolação), dobrando a aspa simples interna.
"""

from __future__ import annotations

from src.codegen.base import CodeGenerator, SessionInfoLite


class PowerShellGenerator(CodeGenerator):
    """Gera scripts PowerShell que automatizam o SAP GUI via COM."""

    language = "powershell"
    display_name = "PowerShell"
    file_extension = ".ps1"
    session_var = "$session"
    stmt_end = ""
    comment_prefix = "#"
    bool_true = "$true"
    bool_false = "$false"

    def gerar_cabecalho(self, info: SessionInfoLite) -> str:
        c = self.comment_prefix
        return (
            f"{c} Script gerado por SAP GUI Scripting Tool\n"
            f"{c} Sistema: {info.system}  Mandante: {info.client}  "
            f"Usuário: {info.user}  Transação: {info.transaction}\n"
            '$SapGuiAuto = [System.Runtime.InteropServices.Marshal]::'
            'GetActiveObject("SAPGUI")\n'
            "$application = $SapGuiAuto.GetScriptingEngine()\n"
            f"$connection = $application.Children({info.connection_index})\n"
            f"{self.session_var} = $connection.Children({info.session_index})\n"
        )

    def gerar_rodape(self) -> str:
        return f"{self.comment_prefix} Fim do script\nWrite-Host 'Script concluído.'\n"

    def _str_lit(self, value: str) -> str:
        """Literal PowerShell com aspas simples (dobra a aspa simples)."""
        return "'" + value.replace("'", "''") + "'"

    def _render_win32(self, dialog: object) -> list[str]:
        d = dialog  # type: ignore[assignment]
        linhas = [
            '$autoit = New-Object -ComObject AutoItX3.Control',
            f'$autoit.WinWait("{d.title}", "", {d.timeout})',  # type: ignore[attr-defined]
        ]
        for ctrl in d.controls:  # type: ignore[attr-defined]
            linhas.append(
                f'$autoit.ControlSetText("{d.title}", "", '  # type: ignore[attr-defined]
                f'"{ctrl.control}", "{ctrl.text}")'
            )
        if d.button:  # type: ignore[attr-defined]
            linhas.append(
                f'$autoit.ControlClick("{d.title}", "", "{d.button}")'  # type: ignore[attr-defined]
            )
        return linhas

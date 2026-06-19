"""Gerador de código Python (pywin32 / win32com.client).

Usa o estilo padrão da base (dot-call com parênteses). A conexão ao SAP GUI é
feita via ``win32com.client.GetObject("SAPGUI")``.
"""

from __future__ import annotations

from src.codegen.base import CodeGenerator, SessionInfoLite


class PythonGenerator(CodeGenerator):
    """Gera scripts Python que automatizam o SAP GUI via COM (pywin32)."""

    language = "python"
    display_name = "Python (pywin32)"
    file_extension = ".py"
    session_var = "session"
    stmt_end = ""
    comment_prefix = "#"
    bool_true = "True"
    bool_false = "False"

    def gerar_cabecalho(self, info: SessionInfoLite) -> str:
        c = self.comment_prefix
        return (
            f"{c} -*- coding: utf-8 -*-\n"
            f"{c} Script gerado por SAP GUI Scripting Tool\n"
            f"{c} Sistema: {info.system}  Mandante: {info.client}  "
            f"Usuário: {info.user}  Transação: {info.transaction}\n"
            "import win32com.client\n"
            "\n"
            'SapGuiAuto = win32com.client.GetObject("SAPGUI")\n'
            "application = SapGuiAuto.GetScriptingEngine\n"
            f"connection = application.Children({info.connection_index})\n"
            f"{self.session_var} = connection.Children({info.session_index})\n"
        )

    def gerar_rodape(self) -> str:
        return f'{self.comment_prefix} Fim do script\nprint("Script concluído.")\n'

    def _render_win32(self, dialog: object) -> list[str]:
        """Diálogo Win32 nativo via o módulo ``autoit`` (pyautoit)."""
        d = dialog  # type: ignore[assignment]
        linhas = [
            "import autoit",
            f'autoit.win_wait("{d.title}", timeout={d.timeout})',  # type: ignore[attr-defined]
        ]
        for ctrl in d.controls:  # type: ignore[attr-defined]
            linhas.append(
                f'autoit.control_set_text("{d.title}", "{ctrl.control}", '  # type: ignore[attr-defined]
                f'"{ctrl.text}")'
            )
        if d.button:  # type: ignore[attr-defined]
            linhas.append(
                f'autoit.control_click("{d.title}", "{d.button}")'  # type: ignore[attr-defined]
            )
        return linhas

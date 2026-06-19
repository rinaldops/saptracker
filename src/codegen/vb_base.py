"""Base compartilhada da família VB (VBScript e VBA).

Diverge do estilo padrão da base em dois pontos:

* Chamadas de método são *statements* sem parênteses (``obj.Method arg1, arg2``);
  parênteses em VB indicariam passagem por valor / chamada de função.
* Literais de string dobram a aspa dupla interna (``""``).

O cabeçalho/rodapé fica a cargo das subclasses (VBScript roda solto; VBA é
envolvido em ``Sub ... End Sub`` com ``Dim`` das variáveis de objeto).
"""

from __future__ import annotations

from typing import Any

from src.codegen.base import CodeGenerator


class VBBaseGenerator(CodeGenerator):
    """Renderização comum a VBScript e VBA."""

    comment_prefix = "'"
    bool_true = "True"
    bool_false = "False"
    session_var = "session"

    def _render_method_call(self, ref_id: str, method: str, args: list[Any]) -> str:
        """``obj.Method arg1, arg2`` — sem parênteses (statement VB)."""
        ref = f"{self._ref(ref_id)}.{method}"
        if not args:
            return ref
        rendered = ", ".join(self._literal(a) for a in args)
        return f"{ref} {rendered}"

    def _str_lit(self, value: str) -> str:
        """Literal VB: aspas duplas, dobrando a aspa interna."""
        return '"' + value.replace('"', '""') + '"'

    def _render_win32(self, dialog: object) -> list[str]:
        """Diálogo Win32 via objeto COM ``AutoItX3.Control``."""
        d = dialog  # type: ignore[assignment]
        linhas = [
            'Set autoit = CreateObject("AutoItX3.Control")',
            f'autoit.WinWait "{d.title}", "", {d.timeout}',  # type: ignore[attr-defined]
        ]
        for ctrl in d.controls:  # type: ignore[attr-defined]
            linhas.append(
                f'autoit.ControlSetText "{d.title}", "", '  # type: ignore[attr-defined]
                f'"{ctrl.control}", "{ctrl.text}"'
            )
        if d.button:  # type: ignore[attr-defined]
            linhas.append(
                f'autoit.ControlClick "{d.title}", "", "{d.button}"'  # type: ignore[attr-defined]
            )
        return linhas

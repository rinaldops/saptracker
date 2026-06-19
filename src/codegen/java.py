"""Gerador de código Java (via Jacob — Java COM Bridge).

No Windows não há uma API Java tipada para o SAP GUI Scripting; o caminho
realista é a ponte COM `Jacob <https://github.com/freemansoft/jacob-project>`_.
Cada interação vira ``Dispatch.call`` / ``Dispatch.put`` sobre o objeto
retornado por ``findById``. Por isso esta linguagem sobrescreve todas as
primitivas de renderização da base.
"""

from __future__ import annotations

from typing import Any

from src.codegen.base import CodeGenerator, SessionInfoLite


class JavaGenerator(CodeGenerator):
    """Gera classes Java que automatizam o SAP GUI via Jacob (COM)."""

    language = "java"
    display_name = "Java (Jacob)"
    file_extension = ".java"
    session_var = "session"
    stmt_end = ";"
    comment_prefix = "//"
    bool_true = "true"
    bool_false = "false"

    _indent = "        "

    def gerar_cabecalho(self, info: SessionInfoLite) -> str:
        c = self.comment_prefix
        return (
            f"{c} Classe gerada por SAP GUI Scripting Tool\n"
            f"{c} Sistema: {info.system}  Mandante: {info.client}  "
            f"Usuário: {info.user}  Transação: {info.transaction}\n"
            "import com.jacob.activeX.ActiveXComponent;\n"
            "import com.jacob.com.Dispatch;\n"
            "import com.jacob.com.Variant;\n"
            "\n"
            "public class SapScript {\n"
            "    public static void main(String[] args) {\n"
            f'{self._indent}Dispatch sapGuiAuto = new ActiveXComponent("SAPGUI").getObject();\n'
            f'{self._indent}Dispatch application = Dispatch.call(sapGuiAuto, '
            '"GetScriptingEngine").toDispatch();\n'
            f"{self._indent}Dispatch connection = Dispatch.call(application, "
            f'"Children", {info.connection_index}).toDispatch();\n'
            f"{self._indent}Dispatch {self.session_var} = Dispatch.call(connection, "
            f'"Children", {info.session_index}).toDispatch();'
        )

    def gerar_rodape(self) -> str:
        return (
            f"{self._indent}{self.comment_prefix} Fim do script\n"
            f'{self._indent}System.out.println("Script concluído.");\n'
            "    }\n"
            "}\n"
        )

    def gerar_linha(self, acao: object) -> str:
        """Renderiza a ação e indenta cada linha para dentro do ``main``."""
        linha = super().gerar_linha(acao)  # type: ignore[arg-type]
        if not linha:
            return linha
        return "\n".join(self._indent + ln if ln else ln for ln in linha.split("\n"))

    def _ref(self, ref_id: str) -> str:
        return f'Dispatch.call({self.session_var}, "findById", "{ref_id}").toDispatch()'

    def _render_method_call(self, ref_id: str, method: str, args: list[Any]) -> str:
        partes = [self._ref(ref_id), f'"{method[0].lower() + method[1:]}"']
        partes.extend(self._literal(a) for a in args)
        return f"Dispatch.call({', '.join(partes)}){self.stmt_end}"

    def _render_property_set(self, ref_id: str, prop: str, value: Any) -> str:
        nome = prop[0].lower() + prop[1:]
        return f'Dispatch.put({self._ref(ref_id)}, "{nome}", {self._literal(value)}){self.stmt_end}'

    def _str_lit(self, value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

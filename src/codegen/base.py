"""Modelo de ação e interface base para geradores de código.

Uma :class:`Acao` representa uma interação SAP capturada pelo Recorder. Cada
:class:`CodeGenerator` traduz a ação em instruções neutras (ver
``src.codegen.instructions``) e as renderiza na sintaxe da linguagem alvo,
montando cabeçalho + linhas + rodapé.

A base já implementa o estilo "dot-call com parênteses" (Python/PowerShell/
AutoIt), parametrizado por atributos de classe. Linguagens divergentes (família
VB, Java) sobrescrevem as primitivas de renderização.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Acao:
    """Representa uma ação SAP capturada pelo Recorder.

    Attributes:
        tipo: Tipo da ação (ex: ``"set_text"``, ``"press"``, ``"select_node"``).
        obj_id: ID completo do objeto SAP alvo (vazio para ações sem objeto).
        args: Argumentos específicos da ação (ex: ``{"text": "ME23N"}``).
        origem: ``"com_event"`` | ``"polling"`` | ``"win32"``.
        timestamp: Marca de tempo legível (``HH:MM:SS``) opcional.
    """

    tipo: str
    obj_id: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    origem: str = "com_event"
    timestamp: str = ""


@dataclass
class SessionInfoLite:
    """Informações mínimas da sessão para o cabeçalho do script."""

    system: str = ""
    client: str = ""
    user: str = ""
    transaction: str = ""
    connection_index: int = 0
    session_index: int = 0


class CodeGenerator(ABC):
    """Interface base para todos os geradores de código.

    Attributes:
        language: Identificador (ex: ``"python"``, ``"vba"``).
        display_name: Nome amigável para a UI.
        file_extension: Extensão sugerida ao salvar.
        session_var: Nome da variável de sessão na linguagem.
        stmt_end: Terminador de instrução (``";"`` em Java, vazio nas demais).
        comment_prefix: Prefixo de comentário de linha.
    """

    language: str = ""
    display_name: str = ""
    file_extension: str = ".txt"
    session_var: str = "session"
    stmt_end: str = ""
    comment_prefix: str = "#"
    bool_true: str = "True"
    bool_false: str = "False"

    # ------------------------------------------------------------------ #
    # Partes obrigatórias
    # ------------------------------------------------------------------ #
    @abstractmethod
    def gerar_cabecalho(self, info: SessionInfoLite) -> str:
        """Gera o cabeçalho do script (imports, conexão ao SAP GUI)."""
        raise NotImplementedError

    @abstractmethod
    def gerar_rodape(self) -> str:
        """Gera o rodapé do script (mensagem final / fechamento)."""
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # Renderização de uma ação
    # ------------------------------------------------------------------ #
    def gerar_linha(self, acao: Acao) -> str:
        """Traduz e renderiza uma :class:`Acao` em linhas de código."""
        from src.codegen.instructions import translate

        linhas: list[str] = []
        for instr in translate(acao):
            linhas.extend(self._render(instr))
        return "\n".join(linhas)

    def gerar_script_completo(self, acoes: list[Acao], info: SessionInfoLite) -> str:
        """Combina cabeçalho + linhas + rodapé em um script completo."""
        partes: list[str] = [self.gerar_cabecalho(info)]
        for a in acoes:
            linha = self.gerar_linha(a)
            if linha:
                partes.append(linha)
        rodape = self.gerar_rodape()
        if rodape:
            partes.append(rodape)
        return "\n".join(p for p in partes if p is not None).rstrip() + "\n"

    # ------------------------------------------------------------------ #
    # Primitivas de renderização (sobrescrevíveis por linguagem)
    # ------------------------------------------------------------------ #
    def _render(self, instr: Any) -> list[str]:
        """Despacha uma instrução neutra para o renderizador apropriado."""
        from src.codegen.instructions import (
            Comment,
            MethodCall,
            PropertySet,
            Raw,
            Win32Dialog,
        )

        if isinstance(instr, MethodCall):
            return [self._render_method_call(instr.ref_id, instr.method, instr.args)]
        if isinstance(instr, PropertySet):
            return [self._render_property_set(instr.ref_id, instr.prop, instr.value)]
        if isinstance(instr, Comment):
            return [self._render_comment(instr.text)]
        if isinstance(instr, Raw):
            return [instr.text]
        if isinstance(instr, Win32Dialog):
            return self._render_win32(instr)
        return [self._render_comment(f"[instrução desconhecida: {instr!r}]")]

    def _ref(self, ref_id: str) -> str:
        """Expressão que referencia o objeto SAP (``FindById``)."""
        return f'{self.session_var}.FindById("{ref_id}")'

    def _render_method_call(self, ref_id: str, method: str, args: list[Any]) -> str:
        """Renderiza ``ref.Method(arg1, arg2)`` (estilo com parênteses)."""
        rendered = ", ".join(self._literal(a) for a in args)
        return f"{self._ref(ref_id)}.{method}({rendered}){self.stmt_end}"

    def _render_property_set(self, ref_id: str, prop: str, value: Any) -> str:
        """Renderiza ``ref.Prop = value``."""
        return f"{self._ref(ref_id)}.{prop} = {self._literal(value)}{self.stmt_end}"

    def _render_comment(self, text: str) -> str:
        """Renderiza um comentário de linha."""
        return f"{self.comment_prefix} {text}"

    def _render_win32(self, dialog: Any) -> list[str]:
        """Renderiza um bloco de diálogo Win32 (sobrescrever por linguagem)."""
        return [self._render_comment(f"[Diálogo Win32: {dialog.title!r} não suportado]")]

    # ------------------------------------------------------------------ #
    # Literais
    # ------------------------------------------------------------------ #
    def _literal(self, value: Any) -> str:
        """Renderiza um literal Python/PS/AutoIt (string, int, bool)."""
        if isinstance(value, bool):
            return self.bool_true if value else self.bool_false
        if isinstance(value, (int, float)):
            return str(value)
        return self._str_lit(str(value))

    def _str_lit(self, value: str) -> str:
        """Literal de string com escape padrão (aspas duplas, ``\\`` escapado)."""
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

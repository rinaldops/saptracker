"""Instruções intermediárias, neutras de linguagem.

Uma :class:`Acao` semântica é traduzida (por :func:`translate`) em uma lista de
instruções neutras (``MethodCall``, ``PropertySet``, ``Comment``, ``Raw``,
``Win32Dialog``). Cada gerador de linguagem apenas renderiza essas instruções
com sua sintaxe — então adicionar uma linguagem nunca precisa reimplementar o
mapeamento semântico de cada tipo de ação.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.codegen.base import Acao


@dataclass
class MethodCall:
    """Chamada de método em um objeto SAP referenciado por ``ref_id``."""

    ref_id: str
    method: str
    args: list[Any] = field(default_factory=list)


@dataclass
class PropertySet:
    """Atribuição de propriedade em um objeto SAP referenciado por ``ref_id``."""

    ref_id: str
    prop: str
    value: Any


@dataclass
class Comment:
    """Comentário de linha única."""

    text: str


@dataclass
class Raw:
    """Linha bruta inserida verbatim (já idiomática o suficiente)."""

    text: str


@dataclass
class Win32Control:
    """Um controle de diálogo Win32 a preencher."""

    control: str
    text: str


@dataclass
class Win32Dialog:
    """Bloco de interação com um diálogo Win32 nativo (via AutoItX)."""

    title: str
    win_class: str
    controls: list[Win32Control] = field(default_factory=list)
    button: str = ""
    timeout: int = 10


Instruction = MethodCall | PropertySet | Comment | Raw | Win32Dialog


def translate(acao: Acao) -> list[Instruction]:
    """Traduz uma :class:`Acao` semântica em instruções neutras de linguagem.

    Tipos de ação reconhecidos:
        ``set_text``, ``press``, ``select``, ``set_focus``, ``set_checkbox``,
        ``send_vkey``, ``select_node``, ``set_current_cell``,
        ``set_selected_rows``, ``selection_interval``, ``set_combo_key``,
        ``maximize``, ``comment``, ``raw``, ``win32_dialog``.

    Tipos desconhecidos viram um comentário de aviso para não perder o registro.
    """
    a = acao.args
    oid = acao.obj_id
    out: list[Instruction] = []

    if acao.timestamp or acao.origem != "com_event":
        out.append(Comment(_origem_label(acao)))

    tipo = acao.tipo
    if tipo == "set_text":
        out.append(PropertySet(oid, "Text", str(a.get("text", ""))))
    elif tipo == "press":
        out.append(MethodCall(oid, "Press"))
    elif tipo == "select":
        out.append(MethodCall(oid, "Select"))
    elif tipo == "set_focus":
        out.append(MethodCall(oid, "SetFocus"))
    elif tipo == "set_checkbox":
        out.append(PropertySet(oid, "Selected", bool(a.get("selected", True))))
    elif tipo == "send_vkey":
        out.append(MethodCall(oid, "SendVKey", [int(a.get("vkey", 0))]))
    elif tipo == "select_node":
        out.append(MethodCall(oid, "SelectNode", [str(a.get("key", ""))]))
    elif tipo == "set_current_cell":
        out.append(
            MethodCall(oid, "SetCurrentCell", [int(a.get("row", 0)), str(a.get("column", ""))])
        )
    elif tipo == "set_selected_rows":
        out.append(PropertySet(oid, "SelectedRows", str(a.get("rows", ""))))
    elif tipo == "selection_interval":
        out.append(PropertySet(oid, "selectionInterval", str(a.get("value", ""))))
    elif tipo == "set_combo_key":
        out.append(PropertySet(oid, "Key", str(a.get("key", ""))))
    elif tipo == "property_set":
        out.append(PropertySet(oid, str(a.get("property", "")), a.get("value")))
    elif tipo == "method_call":
        out.append(
            MethodCall(
                oid,
                str(a.get("method", "")),
                list(a.get("args", [])),
            )
        )
    elif tipo == "maximize":
        out.append(MethodCall(oid, "Maximize"))
    elif tipo == "comment":
        out.append(Comment(str(a.get("text", ""))))
    elif tipo == "raw":
        out.append(Raw(str(a.get("code", ""))))
    elif tipo == "win32_dialog":
        controls = [
            Win32Control(control=c.get("control", ""), text=c.get("text", ""))
            for c in a.get("controls", [])
        ]
        out.append(
            Win32Dialog(
                title=str(a.get("title", "")),
                win_class=str(a.get("class", "#32770")),
                controls=controls,
                button=str(a.get("button", "")),
                timeout=int(a.get("timeout", 10)),
            )
        )
    else:
        out.append(Comment(f"[ação não suportada: {tipo}] {a}"))

    return out


def _effect_key(acao: Acao) -> tuple[str, str, str] | None:
    """Chave normalizada do *efeito* de uma ação que atribui valor a um campo.

    Unifica as variações que descrevem a MESMA alteração de estado, venham elas
    do ``CommandArray`` (``property_set`` com o nome de propriedade que o SAP usa)
    ou do fallback de leitura do componente (``set_text``/``set_combo_key``/
    ``set_checkbox``). Retorna ``None`` para ações que **não** devem ser
    deduplicadas (botões, navegação, métodos, células de grid etc.).
    """
    a = acao.args
    if acao.tipo == "set_text":
        return (acao.obj_id, "text", str(a.get("text", "")))
    if acao.tipo == "set_combo_key":
        return (acao.obj_id, "key", str(a.get("key", "")))
    if acao.tipo == "set_checkbox":
        return (acao.obj_id, "selected", str(bool(a.get("selected", False))))
    if acao.tipo == "property_set":
        return (acao.obj_id, str(a.get("property", "")).lower(), str(a.get("value", "")))
    return None


def dedupe_consecutive(acoes: list[Acao]) -> list[Acao]:
    """Remove ações de atribuição redundantes e **adjacentes** com o mesmo efeito.

    O evento ``ISapSessionEvents.Change`` pode disparar duas vezes para uma única
    alteração do usuário (uma via ``CommandArray``, outra via leitura direta do
    componente), gerando duas linhas equivalentes no script. Esta passagem mantém
    apenas a primeira de um par adjacente idêntico em efeito.

    Conservadora por construção: só compara ações *vizinhas* (qualquer outra ação
    entre elas reinicia a cadeia) e só colapsa quando o valor é igual — reedições
    legítimas e valores distintos são preservados.
    """
    out: list[Acao] = []
    last_key: tuple[str, str, str] | None = None
    for acao in acoes:
        key = _effect_key(acao)
        if key is not None and key == last_key:
            continue
        out.append(acao)
        last_key = key
    return out


def _origem_label(acao: Acao) -> str:
    """Rótulo de comentário descrevendo origem/timestamp da ação."""
    ts = f"{acao.timestamp} " if acao.timestamp else ""
    origem = {
        "com_event": "evento COM",
        "polling": "GuiShell",
        "campo": "Campo SAP",
        "tab": "Seleção de aba",
        "nav": "NAVEGAÇÃO — verifique se o trigger correto é Enter/F-key/botão",
        "nav_trans": "Transação inferida — ajuste se o acesso foi por menu/F-key",
        "win32": "Diálogo Win32 detectado",
    }.get(acao.origem, acao.origem)
    return f"── Ação gravada: {ts}── {origem} ──"

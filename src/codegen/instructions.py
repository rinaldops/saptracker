"""Instruções intermediárias, neutras de linguagem.

Uma :class:`Acao` semântica é traduzida (por :func:`translate`) em uma lista de
instruções neutras (``MethodCall``, ``PropertySet``, ``Comment``, ``Raw``,
``Win32Dialog``). Cada gerador de linguagem apenas renderiza essas instruções
com sua sintaxe — então adicionar uma linguagem nunca precisa reimplementar o
mapeamento semântico de cada tipo de ação.
"""

from __future__ import annotations

import re
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

#: Prefixo absoluto da sessão (``/app/con[N]/ses[M]/``) removido dos IDs no
#: código gerado — o gravador nativo do SAP GUI usa IDs relativos a ``wnd[N]``.
_SESSION_PREFIX = re.compile(r"^/app/con\[\d+\]/ses\[\d+\]/")


def relative_id(obj_id: str) -> str:
    """Torna o ID relativo a ``wnd[N]`` removendo o prefixo da sessão.

    ``/app/con[0]/ses[0]/wnd[0]/tbar[0]/okcd`` → ``wnd[0]/tbar[0]/okcd``. O
    ``session.FindById`` aceita IDs relativos à sessão, então o script gerado fica
    mais limpo. IDs já relativos ou sem o prefixo são devolvidos intactos.
    """
    return _SESSION_PREFIX.sub("", obj_id)


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
    oid = relative_id(acao.obj_id)
    out: list[Instruction] = []

    ctx = _context_comment(acao)
    if ctx is not None:
        out.append(ctx)

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


#: Comandos do okcd que NÃO são transações (não geram comentário de navegação).
_OKCD_NAO_TRANSACAO: frozenset[str] = frozenset({"END", "EX", "I", "BACK"})


def _parse_transaction(okcd_text: str) -> str | None:
    """Extrai o código da transação de um valor de okcd (``/nMIGO`` → ``MIGO``).

    Retorna ``None`` para comandos que não abrem transação (``/n`` sozinho —
    volta ao menu —, funções iniciadas por ``=``, ``/i`` para encerrar etc.).
    """
    t = okcd_text.strip()
    if not t or t.startswith("="):
        return None
    if t.startswith("/"):
        # Prefixos de navegação que abrem transação: /n, /o, /*.
        m = re.match(r"^/[no*](.+)$", t)
        if not m:
            return None
        code = m.group(1).strip()
    else:
        code = t
    code = code.upper()
    if not code or code in _OKCD_NAO_TRANSACAO:
        return None
    return code


def _okcd_text(acao: Acao) -> str | None:
    """Texto atribuído ao campo de comando (okcd), via ``set_text`` ou ``property_set``."""
    if not acao.obj_id.endswith("/okcd"):
        return None
    if acao.tipo == "set_text":
        return str(acao.args.get("text", ""))
    if acao.tipo == "property_set" and str(acao.args.get("property", "")).lower() == "text":
        return str(acao.args.get("value", ""))
    return None


def _is_select(acao: Acao) -> bool:
    """``True`` se a ação seleciona um objeto (aba, menu, rádio)."""
    if acao.tipo == "select":
        return True
    return acao.tipo == "method_call" and str(acao.args.get("method", "")).lower() == "select"


def _context_comment(acao: Acao) -> Comment | None:
    """Comentário de contexto para ajudar a localizar-se no script gerado.

    Cobre três mudanças de contexto: entrar numa transação (okcd), trocar de aba
    (``tabp…``) e selecionar item de menu (``…/mbar/…``). Retorna ``None`` quando
    a ação não representa uma dessas transições.
    """
    okcd = _okcd_text(acao)
    if okcd is not None:
        code = _parse_transaction(okcd)
        return Comment(f"NAVEGANDO para a transação: {code}") if code else None

    if _is_select(acao):
        oid = acao.obj_id
        leaf = oid.rsplit("/", 1)[-1]
        if leaf.startswith("tabp"):
            nome = acao.label or leaf[len("tabp"):]
            return Comment(f"SELEÇÃO de aba: {nome}")
        if "/mbar/" in oid or leaf.startswith("menu["):
            nome = acao.label or leaf
            return Comment(f"SELEÇÃO de item de Menu: {nome}")
    return None


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

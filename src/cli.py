"""Interface de linha de comando (headless) da SAP GUI Scripting Tool.

Permite obter a árvore de objetos de uma sessão SAP, inspecionar um objeto por
ID, destacá-lo (``Visualize``) e selecionar um nó de ``GuiTree`` pela chave —
sem abrir a interface Qt. Pensada para ser chamada por agentes de IA/automação
em vez de captura de tela — ver a skill ``app-devs/_skills/sap-gui-snapshot``.

Registrada em ``pyproject.toml`` como o script de console
``sap-scripting-tool-cli``.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from src.core.analyser import Analyser
from src.core.sap_connection import SapConnection, SapConnectionError
from src.utils.export import save_json, to_json


def _ensure_utf8_stdio() -> None:
    """Força UTF-8 em stdout/stderr.

    O codepage do console do Windows (ex.: cp1252) não é UTF-8 por padrão;
    sem isso, texto acentuado (nomes/textos de tela SAP) sai corrompido de
    forma irrecuperável quando o stdout é capturado ou redirecionado.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def _get_session(args: argparse.Namespace) -> Any:
    return SapConnection().get_session(args.connection, args.session)


def cmd_snapshot(args: argparse.Namespace) -> int:
    """Exporta a árvore de objetos da sessão (JSON no stdout ou em arquivo)."""
    tree = Analyser(_get_session(args)).build_tree()
    data = tree.to_dict()
    if args.out:
        path = save_json(data, args.out)
        print(str(path))
    else:
        print(to_json(data))
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    """Detalha um objeto por ID (inclui introspecção de GuiShell, se houver)."""
    details = Analyser(_get_session(args)).inspect(args.id)
    print(to_json(details))
    return 0


def cmd_highlight(args: argparse.Namespace) -> int:
    """Desenha (ou remove, com ``--off``) a moldura vermelha em um objeto."""
    on = not args.off
    ok = Analyser(_get_session(args)).highlight(args.id, on=on)
    print(to_json({"id": args.id, "on": on, "ok": ok}))
    return 0 if ok else 1


def cmd_select_node(args: argparse.Namespace) -> int:
    """Seleciona (e rola até) um nó de uma GuiTree pela chave."""
    ok = Analyser(_get_session(args)).select_node(args.id, args.key)
    print(to_json({"id": args.id, "key": args.key, "ok": ok}))
    return 0 if ok else 1


def _add_session_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--connection", type=int, default=0, help="Índice da conexão SAP (padrão: 0)."
    )
    parser.add_argument(
        "--session", type=int, default=0, help="Índice da sessão SAP (padrão: 0)."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sap-scripting-tool-cli",
        description="Acesso headless à árvore de objetos de uma sessão SAP GUI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_snapshot = sub.add_parser("snapshot", help="Exporta a árvore de objetos da sessão em JSON.")
    _add_session_args(p_snapshot)
    p_snapshot.add_argument("--out", help="Arquivo JSON de saída (padrão: imprime no stdout).")
    p_snapshot.set_defaults(func=cmd_snapshot)

    p_inspect = sub.add_parser("inspect", help="Detalha um objeto por ID.")
    _add_session_args(p_inspect)
    p_inspect.add_argument("id", help="ID completo do objeto (ex.: wnd[0]/usr/txtFIELD).")
    p_inspect.set_defaults(func=cmd_inspect)

    p_highlight = sub.add_parser("highlight", help="Destaca (ou remove destaque de) um objeto.")
    _add_session_args(p_highlight)
    p_highlight.add_argument("id", help="ID completo do objeto.")
    p_highlight.add_argument(
        "--off", action="store_true", help="Remove o destaque em vez de aplicá-lo."
    )
    p_highlight.set_defaults(func=cmd_highlight)

    p_select_node = sub.add_parser(
        "select-node", help="Seleciona um nó de uma GuiTree pela chave."
    )
    _add_session_args(p_select_node)
    p_select_node.add_argument("id", help="ID completo do controle GuiTree.")
    p_select_node.add_argument("key", help="Chave do nó (campo 'name'/'chave' no snapshot).")
    p_select_node.set_defaults(func=cmd_select_node)

    return parser


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdio()
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except SapConnectionError as e:
        print(f"Erro de conexão SAP: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

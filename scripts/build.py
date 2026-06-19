"""Empacotamento standalone via PyInstaller (Fase 11).

Gera um executável único para Windows a partir de ``sap_scripting_tool.spec``.

A arquitetura do executável é a do interpretador Python em uso: para um build
**x86**, rode este script com um Python 32-bit; para **x64**, com um Python
64-bit. O SAP GUI 64-bit (8.00+) é o alvo principal — use um Python x64.

Uso:
    python scripts/build.py            # limpa build/ e dist/ e empacota
    python scripts/build.py --no-clean # mantém artefatos anteriores
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPEC_FILE = PROJECT_ROOT / "sap_scripting_tool.spec"
BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"
EXE_NAME = "SAPScriptingTool.exe"


def current_arch() -> str:
    """Rótulo de arquitetura do interpretador atual (``x64`` ou ``x86``)."""
    return "x64" if sys.maxsize > 2**32 else "x86"


def clean() -> None:
    """Remove artefatos de builds anteriores (``build/`` e ``dist/``)."""
    for d in (BUILD_DIR, DIST_DIR):
        if d.exists():
            shutil.rmtree(d)
            print(f"Removido: {d}")


def build(*, clean_first: bool = True) -> int:
    """Executa o PyInstaller sobre a spec.

    Args:
        clean_first: Se ``True``, apaga ``build/`` e ``dist/`` antes.

    Returns:
        Código de saída do PyInstaller (0 = sucesso).
    """
    if not SPEC_FILE.exists():
        print(f"Spec não encontrada: {SPEC_FILE}", file=sys.stderr)
        return 1
    if clean_first:
        clean()

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        str(SPEC_FILE),
    ]
    print(f"Empacotando ({current_arch()}): {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))  # noqa: S603
    if result.returncode == 0:
        print(f"\nOK — executável em: {DIST_DIR / EXE_NAME}")
    else:
        print(f"\nFalha no empacotamento (código {result.returncode}).", file=sys.stderr)
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    """CLI do empacotador."""
    parser = argparse.ArgumentParser(description="Build standalone (PyInstaller).")
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Não limpar build/ e dist/ antes de empacotar.",
    )
    args = parser.parse_args(argv)

    if platform.system() != "Windows":
        print(
            "Aviso: o alvo é Windows; empacotar em outra plataforma não produz "
            "um .exe utilizável.",
            file=sys.stderr,
        )
    return build(clean_first=not args.no_clean)


if __name__ == "__main__":
    raise SystemExit(main())

"""Configuração do Sphinx para a documentação da SAP GUI Scripting Tool.

Usa autodoc + napoleon (docstrings Google Style) e myst-parser (arquivos .md).
As dependências de plataforma (pywin32) e de UI/COM são *mockadas* para que a
documentação possa ser construída em qualquer ambiente de CI, inclusive sem o
SAP GUI instalado.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permite ao autodoc importar o pacote ``src`` a partir da raiz do projeto.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# -- Informações do projeto ------------------------------------------------- #
project = "SAP GUI Scripting Tool"
author = "SAP GUI Scripting Tool Contributors"
release = "1.0.0"
version = "1.0"

# -- Configuração geral ----------------------------------------------------- #
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "myst_parser",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
language = "pt_BR"

# Módulos indisponíveis no ambiente de docs: mockados para o autodoc importar.
autodoc_mock_imports = [
    "win32com",
    "win32gui",
    "win32api",
    "win32con",
    "pythoncom",
    "pywintypes",
    "autoit",
    "PyQt6",
    "jinja2",
]
autodoc_typehints = "description"
autodoc_member_order = "bysource"
napoleon_google_docstring = True
napoleon_numpy_docstring = False

intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}

# -- Saída HTML ------------------------------------------------------------- #
html_theme = "alabaster"
html_static_path = ["_static"]

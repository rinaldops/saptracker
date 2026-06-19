"""Ponto de entrada da SAP GUI Scripting Tool.

Cria o ``QApplication``, aplica o tema e abre a janela principal. Registrado em
``pyproject.toml`` como o script de console ``sap-scripting-tool``.
"""

from __future__ import annotations

import sys

from src.utils.logger import configure_logging, get_logger

logger = get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Inicializa a aplicação Qt e executa o loop de eventos.

    Returns:
        Código de saída do processo.
    """
    configure_logging()
    from PyQt6.QtWidgets import QApplication

    from src.ui.main_window import MainWindow
    from src.ui.style import apply_theme

    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    apply_theme(app)  # type: ignore[arg-type]

    window = MainWindow()
    window.show()
    logger.info("SAP GUI Scripting Tool iniciada.")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

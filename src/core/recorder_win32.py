"""Motor de gravação de diálogos Win32 nativos.

Algumas ações no SAP GUI abrem janelas **nativas do Windows** (classe de diálogo
``#32770``) — "Salvar como", seleção de arquivo, impressão — que não fazem parte
da árvore de objetos COM do SAP e, portanto, são invisíveis aos outros dois
motores. Esta thread enumera essas janelas via ``win32gui`` e, quando uma nova
aparece, captura seus controles e emite uma :class:`Acao` do tipo
``win32_dialog`` (que o :mod:`src.codegen` traduz em chamadas AutoItX).

A construção da ação (:func:`dialog_to_acao`) e a derivação de identificadores
``ClassNN`` (:func:`classnn_map`) são puras e testáveis sem Windows.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from src.codegen.base import Acao
from src.utils.logger import get_logger

logger = get_logger(__name__)

ActionSink = Callable[[Acao], None]

#: Classe de janela dos diálogos padrão do Windows.
DIALOG_CLASS = "#32770"

#: Intervalo padrão entre varreduras de janelas nativas (segundos).
DEFAULT_SCAN_INTERVAL = 0.4


def classnn_map(classes: list[str]) -> list[str]:
    """Converte uma lista de nomes de classe em identificadores ``ClassNN``.

    O AutoItX referencia controles por ``ClassNN`` — o nome da classe seguido do
    índice 1-based de ocorrência (``Edit1``, ``Edit2``, ``Button1`` ...).

    Args:
        classes: Nomes de classe dos controles na ordem de enumeração.

    Returns:
        Lista paralela de ``ClassNN``.
    """
    contador: dict[str, int] = {}
    out: list[str] = []
    for cls in classes:
        contador[cls] = contador.get(cls, 0) + 1
        out.append(f"{cls}{contador[cls]}")
    return out


def dialog_to_acao(
    title: str,
    controls: list[tuple[str, str]],
    button: str = "",
    *,
    win_class: str = DIALOG_CLASS,
    timeout: int = 10,
) -> Acao:
    """Monta a :class:`Acao` ``win32_dialog`` a partir do estado capturado.

    Args:
        title: Título da janela do diálogo.
        controls: Pares ``(classnn, texto)`` dos controles a preencher (em geral
            campos de edição).
        button: ``ClassNN`` (ou texto) do botão a acionar; vazio se nenhum.
        win_class: Classe da janela (default ``#32770``).
        timeout: Tempo máximo de espera pela janela, em segundos.

    Returns:
        Ação pronta para o buffer do Recorder.
    """
    return Acao(
        tipo="win32_dialog",
        obj_id="",
        args={
            "title": title,
            "class": win_class,
            "controls": [{"control": c, "text": t} for c, t in controls],
            "button": button,
            "timeout": timeout,
        },
        origem="win32",
    )


class Win32Recorder:
    """Thread que detecta e captura diálogos Win32 nativos.

    Args:
        sink: Callback chamado com cada :class:`Acao` capturada.
        scan_interval: Segundos entre varreduras de janelas.
        own_pid_only: Se ``True``, ignora diálogos de outros processos que não o
            SAP (heurística desabilitada por padrão — capturamos todos os
            ``#32770`` que surgirem durante a gravação).
    """

    def __init__(
        self,
        sink: ActionSink,
        *,
        scan_interval: float = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        self._sink = sink
        self._scan_interval = scan_interval
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        #: Handles de diálogos já capturados (para não emitir em duplicidade).
        self._seen: set[int] = set()

    # ------------------------------------------------------------------ #
    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        if not self._win32_available():
            logger.warning("Win32Recorder inativo: win32gui indisponível.")
            return
        self._stop.clear()
        self._seen.clear()
        self._thread = threading.Thread(target=self._run, name="Win32Recorder", daemon=True)
        self._thread.start()
        logger.info("Win32Recorder iniciado (intervalo=%.2fs).", self._scan_interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._scan_interval * 4 + 1.0)
            self._thread = None
        logger.info("Win32Recorder parado.")

    # ------------------------------------------------------------------ #
    def _run(self) -> None:
        while not self._stop.wait(self._scan_interval):
            self.scan_once()

    def scan_once(self) -> list[Acao]:
        """Varre as janelas, captura diálogos novos e emite suas ações."""
        detectadas: list[Acao] = []
        hwnds = self._enumerate_dialogs()
        atuais = set(hwnds)
        # Remove handles que sumiram (diálogo fechado) para permitir recaptura
        # caso o mesmo tipo de diálogo reabra com handle reciclado.
        self._seen &= atuais
        for hwnd in hwnds:
            if hwnd in self._seen:
                continue
            self._seen.add(hwnd)
            acao = self._capture(hwnd)
            if acao is not None:
                detectadas.append(acao)
                self._sink(acao)
        return detectadas

    # ------------------------------------------------------------------ #
    # Camada dependente de plataforma (isolada para testes)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _win32_available() -> bool:
        try:
            import win32gui  # noqa: F401

            return True
        except Exception:  # noqa: BLE001
            return False

    def _enumerate_dialogs(self) -> list[int]:
        """Retorna os handles de janelas visíveis de classe ``#32770``."""
        try:
            import win32gui
        except Exception:  # noqa: BLE001
            return []

        hwnds: list[int] = []

        def _cb(hwnd: int, _: Any) -> bool:
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                if win32gui.GetClassName(hwnd) == DIALOG_CLASS:
                    hwnds.append(hwnd)
            except Exception:  # noqa: BLE001 - janela pode fechar durante a enum
                pass
            return True

        try:
            win32gui.EnumWindows(_cb, None)
        except Exception as e:  # noqa: BLE001
            logger.debug("EnumWindows falhou: %s", e)
        return hwnds

    def _capture(self, hwnd: int) -> Acao | None:
        """Captura título, campos de edição e botão padrão de um diálogo."""
        try:
            import win32gui
        except Exception:  # noqa: BLE001
            return None

        try:
            title = win32gui.GetWindowText(hwnd)
            child_classes: list[str] = []
            child_texts: list[str] = []
            child_hwnds: list[int] = []

            def _cb(child: int, _: Any) -> bool:
                try:
                    child_classes.append(win32gui.GetClassName(child))
                    child_texts.append(win32gui.GetWindowText(child))
                    child_hwnds.append(child)
                except Exception:  # noqa: BLE001
                    pass
                return True

            win32gui.EnumChildWindows(hwnd, _cb, None)
        except Exception as e:  # noqa: BLE001
            logger.debug("Captura do diálogo %s falhou: %s", hwnd, e)
            return None

        nn = classnn_map(child_classes)
        controls: list[tuple[str, str]] = [
            (nn[i], child_texts[i])
            for i, cls in enumerate(child_classes)
            if "Edit" in cls
        ]
        # Botão padrão: primeira classe Button com texto (heurística).
        button = next(
            (nn[i] for i, cls in enumerate(child_classes) if "Button" in cls),
            "",
        )
        return dialog_to_acao(title, controls, button)

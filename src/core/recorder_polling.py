"""Motor de gravação por *polling* (snapshot/diff) para controles GuiShell.

O SAP GUI **não emite eventos COM** para interações dentro de controles GuiShell
(GuiGridView, GuiTree, GuiTextEdit, GuiCalendar) — ver SAP Note 587202. Logo, a
única forma de gravá-las é tirar *snapshots* periódicos do estado de cada shell
e comparar com o snapshot anterior; cada mudança vira uma :class:`Acao`.

A lógica de diff (:func:`diff_to_acoes`) é pura e independente de COM/threads,
para ser testável sem um SAP real. A classe :class:`PollingRecorder` apenas
orquestra a thread, a descoberta dos shells e a coleta de snapshots.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from src.codegen.base import Acao
from src.core.analyser import Analyser
from src.core.com_utils import safe_com_call
from src.core.shell_handlers import get_handler
from src.utils.logger import get_logger

logger = get_logger(__name__)

#: Assinatura do callback que recebe cada ação capturada.
ActionSink = Callable[[Acao], None]

#: Intervalo padrão entre ciclos de polling (segundos).
DEFAULT_POLL_INTERVAL = 0.5


def diff_to_acoes(obj_id: str, antes: dict[str, Any], depois: dict[str, Any]) -> list[Acao]:
    """Compara dois snapshots de um GuiShell e devolve as ações resultantes.

    Mapeia mudanças de estado para os tipos de :class:`Acao` que o pacote
    :mod:`src.codegen` sabe traduzir. Função pura — não toca em COM.

    Args:
        obj_id: ID completo do controle (``wnd[0]/usr/.../shell``).
        antes: Snapshot anterior (``handler.tirar_snapshot``).
        depois: Snapshot atual.

    Returns:
        Lista de ações (vazia se nada relevante mudou).
    """
    tipo = depois.get("tipo", "")
    out: list[Acao] = []

    if tipo == "GuiGridView":
        cell_changed = antes.get("celula_atual_linha") != depois.get(
            "celula_atual_linha"
        ) or antes.get("celula_atual_coluna") != depois.get("celula_atual_coluna")
        if cell_changed and int(depois.get("celula_atual_linha", -1)) >= 0:
            out.append(
                Acao(
                    tipo="set_current_cell",
                    obj_id=obj_id,
                    args={
                        "row": int(depois.get("celula_atual_linha", 0)),
                        "column": str(depois.get("celula_atual_coluna", "")),
                    },
                    origem="polling",
                )
            )
        sel = depois.get("linhas_selecionadas", "")
        if sel and sel != antes.get("linhas_selecionadas", ""):
            out.append(
                Acao(
                    tipo="set_selected_rows",
                    obj_id=obj_id,
                    args={"rows": str(sel)},
                    origem="polling",
                )
            )

    elif tipo == "GuiTree":
        sel = depois.get("no_selecionado", "")
        if sel and sel != antes.get("no_selecionado", ""):
            out.append(
                Acao(
                    tipo="select_node",
                    obj_id=obj_id,
                    args={"key": str(sel)},
                    origem="polling",
                )
            )

    elif tipo == "GuiTextEdit":
        conteudo = depois.get("conteudo", "")
        if conteudo != antes.get("conteudo", ""):
            out.append(
                Acao(
                    tipo="set_text",
                    obj_id=obj_id,
                    args={"text": str(conteudo)},
                    origem="polling",
                )
            )

    elif tipo == "GuiCalendar":
        sel = depois.get("selecao", "")
        if sel and sel != antes.get("selecao", ""):
            out.append(
                Acao(
                    tipo="selection_interval",
                    obj_id=obj_id,
                    args={"value": str(sel)},
                    origem="polling",
                )
            )

    return out


def collect_shells(session: Any) -> list[tuple[str, Any]]:
    """Descobre os controles GuiShell da sessão.

    Returns:
        Lista de ``(obj_id, obj_com)`` para cada shell encontrado. Erros COM são
        absorvidos (o shell some quando a tela muda).
    """
    analyser = Analyser(session)
    pares: list[tuple[str, Any]] = []
    try:
        tree = analyser.build_tree()
    except Exception as e:  # noqa: BLE001 - travessia é best-effort
        logger.debug("Falha ao percorrer árvore para polling: %s", e)
        return pares
    for node in tree.flatten():
        if not node.is_shell or not node.id:
            continue
        obj = analyser.find_by_id(node.id)
        if obj is not None:
            pares.append((node.id, obj))
    return pares


class PollingRecorder:
    """Thread que grava interações com GuiShell por snapshot/diff.

    Args:
        session: Objeto COM ``GuiSession`` a observar.
        sink: Callback chamado com cada :class:`Acao` capturada.
        poll_interval: Segundos entre ciclos de polling.
    """

    def __init__(
        self,
        session: Any,
        sink: ActionSink,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> None:
        self._session = session
        self._sink = sink
        self._poll_interval = poll_interval
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        #: Último snapshot por obj_id.
        self._snapshots: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------ #
    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Inicia a thread de polling (no-op se já estiver rodando)."""
        if self.is_running:
            return
        self._stop.clear()
        self._snapshots.clear()
        self._thread = threading.Thread(
            target=self._run, name="PollingRecorder", daemon=True
        )
        self._thread.start()
        logger.info("PollingRecorder iniciado (intervalo=%.2fs).", self._poll_interval)

    def stop(self) -> None:
        """Sinaliza parada e aguarda a thread encerrar."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._poll_interval * 4 + 1.0)
            self._thread = None
        logger.info("PollingRecorder parado.")

    # ------------------------------------------------------------------ #
    def _run(self) -> None:
        """Loop principal da thread: inicializa COM e cicla até parar."""
        co_initialized = self._co_initialize()
        try:
            # Primeiro ciclo apenas estabelece a linha de base (sem emitir).
            self.poll_once(emit=False)
            while not self._stop.wait(self._poll_interval):
                self.poll_once(emit=True)
        finally:
            if co_initialized:
                self._co_uninitialize()

    def poll_once(self, *, emit: bool = True) -> list[Acao]:
        """Executa um ciclo de polling: snapshot de cada shell e diff.

        Exposto separadamente da thread para facilitar testes determinísticos.

        Args:
            emit: Se ``True``, envia as ações ao ``sink``; se ``False``, apenas
                atualiza a linha de base (primeiro ciclo).

        Returns:
            As ações detectadas neste ciclo.
        """
        detectadas: list[Acao] = []
        for obj_id, obj in collect_shells(self._session):
            handler = get_handler(obj)
            snap = safe_com_call(handler.tirar_snapshot, obj)
            if snap is None:
                continue
            anterior = self._snapshots.get(obj_id)
            self._snapshots[obj_id] = snap
            if anterior is None or not emit:
                continue
            for acao in diff_to_acoes(obj_id, anterior, snap):
                detectadas.append(acao)
                self._sink(acao)
        return detectadas

    # ------------------------------------------------------------------ #
    @staticmethod
    def _co_initialize() -> bool:
        """Inicializa o apartamento COM da thread (Windows). Tolerante a falha."""
        try:
            import pythoncom

            pythoncom.CoInitialize()
            return True
        except Exception as e:  # noqa: BLE001 - ausente fora do Windows
            logger.debug("CoInitialize indisponível: %s", e)
            return False

    @staticmethod
    def _co_uninitialize() -> None:
        try:
            import pythoncom

            pythoncom.CoUninitialize()
        except Exception as e:  # noqa: BLE001
            logger.debug("CoUninitialize falhou: %s", e)

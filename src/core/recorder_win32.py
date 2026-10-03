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

import re
import threading
from collections.abc import Callable
from typing import Any

from src.codegen.base import Acao
from src.core.com_utils import com_item, com_len, safe_get
from src.utils.logger import get_logger

logger = get_logger(__name__)

ActionSink = Callable[[Acao], None]

#: Classe de janela dos diálogos padrão do Windows.
DIALOG_CLASS = "#32770"

#: Intervalo padrão entre varreduras de janelas nativas (segundos).
# Diálogos "Salvar como" são interativos: o usuário pode preencher o nome e
# confirmar antes do próximo ciclo. Um intervalo de 400 ms perde esse estado.
# 50 ms mantém a captura confiável sem alterar o polling SAP/GuiShell.
DEFAULT_SCAN_INTERVAL = 0.05

#: Títulos de janelas Win32 que devem ser IGNORADOS pelo recorder.
#: Diálogos de erro interno do SAP (sapfewdbg, crash handlers, Windows Script
#: Host) não fazem parte do fluxo de trabalho do usuário e não devem ser
#: reproduzidos em automação — capturá-los polui o script gerado.
_IGNORED_TITLES: frozenset[str] = frozenset({
    "Sapfewdbg: crash in saplogon.exe",
    "Sapfewdbg Exception",
    "Sapfewdbg",
    "Windows Script Host",
    "SAP GUI Scripting",
    "SAPGUI",
})


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
        session: Sessão COM ``GuiSession`` em gravação. Quando informada, o
            recorder consulta a árvore SAP para **ignorar** janelas modais do
            próprio SAP GUI (``wnd[1]``, ``wnd[2]`` …) — elas são capturadas via
            COM como ``wnd[0]``. O AutoItX só deve atuar em janelas nativas do SO
            que **não** pertencem ao SAP GUI. Se omitida, captura todo ``#32770``
            (comportamento legado).
    """

    def __init__(
        self,
        sink: ActionSink,
        *,
        scan_interval: float = DEFAULT_SCAN_INTERVAL,
        session: Any | None = None,
        is_sap_modal_open: Callable[[], bool] | None = None,
        is_sap_window: Callable[[str], bool] | None = None,
    ) -> None:
        self._sink = sink
        self._scan_interval = scan_interval
        self._session = session
        #: Predicado externo (ex.: do PollingRecorder) que informa se há janela
        #: modal SAP aberta. É a fonte preferida — vem de um thread COM confiável.
        self._is_sap_modal_open = is_sap_modal_open
        #: Predicado externo que informa se um TÍTULO pertence a uma janela SAP.
        #: Mais confiável que a contagem de modais (cobre popups de sistema cujo
        #: ``Children.Count`` não os conta, ex.: SAPMSSY0 "Exibir logs").
        self._is_sap_window = is_sap_window
        #: Sessão re-adquirida dentro da thread de scan (apartamento COM próprio).
        self._thread_session: Any | None = None
        self._conn_idx, self._sess_idx = self._extract_indices(session)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        #: Handles de diálogos já capturados (para não emitir em duplicidade).
        self._seen: set[int] = set()
        #: Diálogos vistos UMA vez, aguardando 1 ciclo antes da decisão — dá
        #: tempo para a árvore COM refletir o ``wnd[N]`` de um modal SAP (corrida).
        self._pending: set[int] = set()
        #: Estado mais recente dos diálogos ``Salvar como``. Esses diálogos
        #: precisam ser emitidos somente ao fechar: o nome do arquivo costuma
        #: ser digitado depois que a janela é detectada.
        self._deferred: dict[int, Acao] = {}

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
        # Pré-popula _seen com os diálogos JÁ visíveis antes de iniciar o scan,
        # para que apenas diálogos que APARECEREM durante a gravação sejam capturados.
        # Sem isso, "SAP Logon 800" (sempre aberto) é capturado como se fosse novo.
        pre_existentes = self._enumerate_dialogs()
        self._seen = set(pre_existentes)
        self._pending = set()
        self._deferred = {}
        if pre_existentes:
            titulos = [self._title_safe(h) for h in pre_existentes]
            logger.debug(
                "Win32Recorder: %d diálogo(s) pré-existente(s) ignorados: %s",
                len(pre_existentes),
                titulos,
            )
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
        co_initialized = self._co_initialize()
        try:
            # Re-adquire a sessão neste apartamento COM (evita marshaling
            # cross-STA com a thread Qt, que torna session.Children inacessível).
            self._thread_session = self._acquire_thread_session() or self._session
            while not self._stop.wait(self._scan_interval):
                self.scan_once()
        finally:
            self._thread_session = None
            if co_initialized:
                self._co_uninitialize()

    def scan_once(self) -> list[Acao]:
        """Varre as janelas, captura diálogos novos e emite suas ações."""
        detectadas: list[Acao] = []
        hwnds = self._enumerate_dialogs()
        atuais = set(hwnds)
        # Remove handles que sumiram (diálogo fechado) para permitir recaptura
        # caso o mesmo tipo de diálogo reabra com handle reciclado.
        self._seen &= atuais
        self._pending &= atuais
        # O desaparecimento confirma que o usuário concluiu o diálogo. Só
        # então emitimos a última leitura, já contendo o nome digitado.
        for hwnd in set(self._deferred) - atuais:
            acao = self._deferred.pop(hwnd)
            detectadas.append(acao)
            self._sink(acao)
        for hwnd in hwnds:
            if hwnd in self._seen:
                continue
            # Primeira aparição: adia a decisão por um ciclo. Isso evita a corrida
            # em que o #32770 de um modal SAP é enumerado antes de a árvore COM
            # registrar o wnd[N] — capturando-o erroneamente via AutoItX.
            if hwnd not in self._pending:
                self._pending.add(hwnd)
                logger.debug(
                    "Win32Recorder.scan_once: diálogo novo '%s' adiado 1 ciclo.",
                    self._title_safe(hwnd),
                )
                continue
            # Segunda aparição consecutiva: COM já estabilizou — decide agora.
            self._pending.discard(hwnd)
            self._seen.add(hwnd)
            # Verifica título antes de capturar (filtra diálogos SAP internos)
            titulo = self._title_safe(hwnd)
            if titulo in _IGNORED_TITLES or any(titulo.startswith(p) for p in ("Sapfewdbg",)):
                logger.info(
                    "Win32Recorder: diálogo '%s' IGNORADO (diálogo interno SAP/WScript).",
                    titulo,
                )
                continue
            # Janela do PRÓPRIO SAP GUI (modal wnd[1+] ou popup de sistema):
            # aparece como #32770 nativo mas é uma janela SAP, capturada via COM.
            # O AutoItX só deve atuar em janelas do SO de fato externas ao SAP GUI.
            if self._belongs_to_sap(titulo):
                logger.info(
                    "Win32Recorder: '%s' é janela do SAP GUI — ignorada pelo "
                    "AutoItX (capturada via COM).",
                    titulo,
                )
                continue
            acao = self._capture(hwnd)
            if acao is not None:
                if titulo.casefold() in {"salvar como", "save as"}:
                    self._deferred[hwnd] = acao
                    logger.debug(
                        "Win32Recorder: diálogo '%s' aguardando fechamento para "
                        "capturar o nome final.",
                        titulo,
                    )
                    continue
                logger.info(
                    "Win32Recorder: diálogo '%s' capturado (%d controle(s)).",
                    acao.args.get("title", "?"),
                    len(acao.args.get("controls", [])),
                )
                detectadas.append(acao)
                self._sink(acao)
        # Atualiza o estado dos diálogos adiados a cada ciclo, após a digitação.
        for hwnd in set(self._deferred) & atuais:
            acao = self._capture(hwnd)
            if acao is not None:
                self._deferred[hwnd] = acao
                logger.debug(
                    "Win32Recorder: estado de '%s' atualizado: %s",
                    self._title_safe(hwnd),
                    acao.args.get("controls", []),
                )
        return detectadas

    # ------------------------------------------------------------------ #
    # Distinção SAP modal × diálogo do SO (via árvore COM)
    # ------------------------------------------------------------------ #
    def _belongs_to_sap(self, titulo: str) -> bool:
        """``True`` se o ``#32770`` é, na verdade, uma janela do SAP GUI.

        Combina sinais independentes (qualquer um positivo basta), do mais
        confiável ao de reserva:

        1. **Título ∈ janelas SAP** (predicado do polling) — casa o título do
           diálogo com ``ActiveWindow``/filhas; cobre popups de sistema que a
           contagem de filhos não vê.
        2. **Flag de modal** (predicado do polling) — ``Children.Count > 1``.
        3. **Leitura síncrona própria** — varre a sessão re-adquirida na própria
           thread no instante da decisão (sem lag do polling).
        """
        if self._is_sap_window is not None:
            try:
                if self._is_sap_window(titulo):
                    return True
            except Exception:  # noqa: BLE001 - predicado é best-effort
                pass
        if self._sap_modal_open():
            return True
        return self._own_title_match(titulo)

    def _own_title_match(self, titulo: str) -> bool:
        """Casa ``titulo`` com ``ActiveWindow``/filhas da sessão re-adquirida."""
        session = self._thread_session
        alvo = titulo.strip()
        if session is None or not alvo:
            return False
        try:
            active_text = str(safe_get(safe_get(session, "ActiveWindow"), "Text", "") or "").strip()
            if active_text == alvo:
                return True
            children = safe_get(session, "Children")
            for i in range(com_len(children)):
                janela = com_item(children, i)
                if str(safe_get(janela, "Text", "") or "").strip() == alvo:
                    return True
        except Exception:  # noqa: BLE001 - fronteira COM, best-effort
            return False
        return False

    def _sap_modal_open(self) -> bool:
        """``True`` se a sessão SAP tem uma janela modal aberta (``wnd[1]`` …).

        A sessão expõe as janelas em ``Children``: ``wnd[0]`` é a janela
        principal; qualquer filho adicional é um ``GuiModalWindow`` (popup do
        próprio SAP). Logo ``Children.Count > 1`` indica um modal SAP ativo, que
        deve ser capturado via COM e **não** pelo AutoItX.

        Prefere o predicado externo (``is_sap_modal_open``), atualizado por um
        thread COM confiável (PollingRecorder). Sem ele, recorre à leitura COM
        própria. Best-effort: sem sessão nem predicado, retorna ``False`` —
        preservando o comportamento legado de capturar o ``#32770``.
        """
        if self._is_sap_modal_open is not None:
            try:
                return bool(self._is_sap_modal_open())
            except Exception:  # noqa: BLE001 - predicado é best-effort
                pass
        session = self._thread_session
        if session is None:
            return False
        try:
            return com_len(safe_get(session, "Children")) > 1
        except Exception:  # noqa: BLE001 - fronteira COM, best-effort
            return False

    def _acquire_thread_session(self) -> Any | None:
        """Obtém a sessão no apartamento COM desta thread (via GetObject)."""
        if self._session is None:
            return None
        try:
            import win32com.client

            sap = win32com.client.GetObject("SAPGUI")
            engine = sap.GetScriptingEngine
            return engine.Children(self._conn_idx).Children(self._sess_idx)
        except Exception as e:  # noqa: BLE001 - best-effort
            logger.debug("Win32Recorder: re-aquisição de sessão falhou — %s.", e)
            return None

    @staticmethod
    def _extract_indices(session: Any | None) -> tuple[int, int]:
        """Extrai ``con[N]`` e ``ses[N]`` do ID absoluto da sessão (default 0,0)."""
        if session is None:
            return (0, 0)
        session_id = str(safe_get(session, "Id", "") or "")
        parent_id = str(safe_get(safe_get(session, "Parent"), "Id", "") or "")
        conn = re.search(r"con\[(\d+)]", session_id) or re.search(r"con\[(\d+)]", parent_id)
        sess = re.search(r"ses\[(\d+)]", session_id)
        return (int(conn.group(1)) if conn else 0, int(sess.group(1)) if sess else 0)

    @staticmethod
    def _co_initialize() -> bool:
        try:
            import pythoncom

            pythoncom.CoInitialize()
            return True
        except Exception as e:  # noqa: BLE001 - ausente fora do Windows
            logger.debug("Win32Recorder: CoInitialize indisponível — %s.", e)
            return False

    @staticmethod
    def _co_uninitialize() -> None:
        try:
            import pythoncom

            pythoncom.CoUninitialize()
        except Exception as e:  # noqa: BLE001
            logger.debug("Win32Recorder: CoUninitialize falhou — %s.", e)

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

    def _title_safe(self, hwnd: int) -> str:
        """Retorna o título da janela sem propagar exceções."""
        try:
            import win32gui
            return win32gui.GetWindowText(hwnd) or f"hwnd:{hwnd}"
        except Exception:  # noqa: BLE001
            return f"hwnd:{hwnd}"

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
            logger.debug("Win32Recorder._capture: hwnd=%d título='%s'", hwnd, title)
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
        # Prefere o botão de confirmação pelo rótulo. Na janela padrão do
        # Windows, ``Button1`` pode ser "Abrir como somente leitura" e não
        # "Salvar".
        button = next(
            (
                nn[i]
                for i, cls in enumerate(child_classes)
                if "Button" in cls
                and child_texts[i].strip().replace("&", "").casefold()
                in {"salvar", "save", "ok", "abrir"}
            ),
            "",
        )
        if not button:
            button = next(
                (nn[i] for i, cls in enumerate(child_classes) if "Button" in cls),
                "",
            )
        return dialog_to_acao(title, controls, button)

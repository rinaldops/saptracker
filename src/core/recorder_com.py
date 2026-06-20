"""Motor de gravação por eventos COM (objetos GuiComponent "normais").

Para os controles que **não** são GuiShell (campos de texto, checkboxes, botões,
combos, etc.), o SAP GUI emite o evento ``GuiSession.Change`` sempre que o
usuário altera um valor. Este módulo conecta um *event sink* COM à sessão e
traduz cada componente alterado em uma :class:`Acao`.

A tradução componente → ação (:func:`acao_from_component`) é pura e testável com
um objeto falso que apenas exponha as propriedades lidas; a fiação COM
(``WithEvents``) fica isolada em :class:`ComRecorder` e degrada graciosamente
quando o pywin32 não está disponível.
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

#: Interface de eventos ``ISapSessionEvents`` registrada por ``sapfewse.ocx``.
SAP_SESSION_EVENTS_IID = "{67A71FA4-9381-4061-B3BB-74A545C75874}"

#: DISPIDs lidos diretamente da type library SAP GUI Scripting API 1.0.
_EVENT_DISPIDS: dict[int, str] = {
    1280: "Change",
    514: "StartRequest",
    515: "EndRequest",
    1283: "Destroy",
    516: "Error",
    1281: "Hit",
    1282: "ContextMenu",
    1284: "AutomationFCode",
    1285: "Activated",
    1286: "FocusChanged",
    1287: "HistoryOpened",
    1288: "ProgressIndicator",
    1289: "AbapScriptingEvent",
}

#: Propriedades emitidas pelo ``CommandArray`` que NÃO têm efeito funcional na
#: automação — apenas poluem o script gerado. ``caretPosition`` indica somente a
#: posição do cursor no campo; o conteúdo já é definido por ``text``, então
#: reproduzi-la é inútil para o desenvolvedor. Comparação é *case-insensitive*.
_IGNORED_COMMAND_PROPERTIES: frozenset[str] = frozenset({"caretposition"})

#: Mapa tipo SAP → (tipo de ação, propriedade lida). Para tipos cujo valor não
#: importa (botões), a propriedade é ``None``.
_TYPE_MAP: dict[str, tuple[str, str | None]] = {
    "GuiTextField": ("set_text", "Text"),
    "GuiCTextField": ("set_text", "Text"),
    "GuiPasswordField": ("set_text", "Text"),
    "GuiOkCodeField": ("set_text", "Text"),
    "GuiComboBox": ("set_combo_key", "Key"),
    "GuiCheckBox": ("set_checkbox", "Selected"),
    "GuiRadioButton": ("select", None),
    "GuiButton": ("press", None),
    "GuiMenu": ("select", None),
    "GuiTab": ("select", None),
}


def acao_from_component(
    component: Any, *, origem: str = "com_event", timestamp: str = ""
) -> Acao | None:
    """Traduz um GuiComponent alterado em uma :class:`Acao`.

    Args:
        component: Objeto COM (ou *fake* em testes) do componente que mudou.
        origem: Rótulo de origem da ação (default ``"com_event"``).
        timestamp: Marca de tempo opcional.

    Returns:
        A ação correspondente, ou ``None`` se o tipo não for capturável por
        eventos (ex.: GuiShell, tratado pelo motor de polling).
    """
    oid = str(safe_get(component, "Id", "") or "")
    if not oid:
        logger.debug("acao_from_component: Id vazio — componente ignorado.")
        return None
    sap_type = str(safe_get(component, "Type", "") or "")
    mapeado = _TYPE_MAP.get(sap_type)
    if mapeado is None:
        logger.debug(
            "acao_from_component: tipo '%s' não mapeado (Id=%s) — ignorado pelo motor COM.",
            sap_type,
            oid,
        )
        return None

    tipo_acao, _prop = mapeado
    args: dict[str, Any] = {}
    if tipo_acao == "set_text":
        args = {"text": str(safe_get(component, "Text", "") or "")}
    elif tipo_acao == "set_combo_key":
        args = {"key": str(safe_get(component, "Key", "") or "")}
    elif tipo_acao == "set_checkbox":
        args = {"selected": bool(safe_get(component, "Selected", False))}

    # Rótulo legível para comentários de contexto (aba/menu): o id do menu é
    # opaco (`menu[3]`), então o texto visível é capturado aqui na gravação.
    label = ""
    if sap_type in ("GuiTab", "GuiMenu"):
        label = str(safe_get(component, "Text", "") or "")

    acao = Acao(
        tipo=tipo_acao, obj_id=oid, args=args, origem=origem,
        timestamp=timestamp, label=label,
    )
    logger.debug(
        "acao_from_component: capturado [%s] %s em '%s'.", origem, tipo_acao, oid
    )
    return acao


class _SessionEventSink:
    """Sink de eventos do ``GuiSession`` para uso com ``win32com WithEvents``.

    O pywin32 invoca o método cujo nome corresponde ao evento. Dependendo da
    versão/typelib o nome pode vir como ``Change`` ou ``OnChange``; ambos são
    fornecidos e delegam ao mesmo tratador.
    """

    #: Preenchido por :meth:`ComRecorder._attach` após a instância ser criada
    #: pelo pywin32 (que não nos deixa passar argumentos ao construtor).
    _sink: ActionSink | None = None

    def __init__(self, sink: ActionSink | None = None) -> None:
        self._sink = sink

    def _on_change(self, component: Any, command_array: Any = None, *_: Any) -> None:
        logger.debug("_SessionEventSink._on_change: evento recebido.")
        if self._sink is None:
            logger.debug("_on_change: sink é None — evento descartado.")
            return
        component = _as_dispatch(component)
        actions = acoes_from_command_array(component, command_array)
        if not actions:
            action = acao_from_component(component)
            actions = [action] if action is not None else []
        for action in actions:
            logger.info(
                "ComRecorder: ação capturada via evento COM — %s em '%s'.",
                action.tipo,
                action.obj_id,
            )
            self._sink(action)

    # Variantes de nome de evento que o pywin32 pode chamar.
    def OnChange(self, _session: Any, component: Any, *rest: Any) -> None:  # noqa: N802
        logger.debug("_SessionEventSink.OnChange disparado.")
        self._on_change(component, *rest)

    def Change(self, _session: Any, component: Any, *rest: Any) -> None:  # noqa: N802
        logger.debug("_SessionEventSink.Change disparado.")
        self._on_change(component, *rest)


class _DirectSessionEventSink(_SessionEventSink):
    """Implementa ``ISapSessionEvents`` sem wrappers gerados pelo makepy."""

    _public_methods_ = list(_EVENT_DISPIDS.values())
    _dispid_to_func_ = _EVENT_DISPIDS

    def _query_interface_(self, iid: Any) -> Any:
        """Expõe o gateway IDispatch quando o connection point pede o IID SAP."""
        import pywintypes
        import win32com.server.util

        if iid == pywintypes.IID(SAP_SESSION_EVENTS_IID):
            return win32com.server.util.wrap(self)
        return None

    def Hit(self, _session: Any, component: Any, inner_object: Any = None) -> None:  # noqa: N802
        """Captura interações transitórias que não deixam estado persistente."""
        if self._sink is None:
            return
        action = acao_from_hit(_as_dispatch(component), inner_object)
        if action is not None:
            logger.info(
                "ComRecorder: ação capturada via Hit — %s em '%s'.",
                action.tipo,
                action.obj_id,
            )
            self._sink(action)

    def StartRequest(self, _session: Any) -> None:  # noqa: N802
        logger.debug("ISapSessionEvents.StartRequest")

    def EndRequest(self, _session: Any) -> None:  # noqa: N802
        logger.debug("ISapSessionEvents.EndRequest")

    def AutomationFCode(self, _session: Any, function_code: Any) -> None:  # noqa: N802
        logger.debug("ISapSessionEvents.AutomationFCode=%r", function_code)

    def FocusChanged(self, _session: Any, control: Any) -> None:  # noqa: N802
        logger.debug("ISapSessionEvents.FocusChanged=%r", safe_get(control, "Id", ""))

    def Destroy(self, _session: Any) -> None:  # noqa: N802
        logger.info("ISapSessionEvents.Destroy")

    def Error(self, *_args: Any) -> None:  # noqa: N802
        logger.debug("ISapSessionEvents.Error=%r", _args)

    def ContextMenu(self, *_args: Any) -> None:  # noqa: N802
        logger.debug("ISapSessionEvents.ContextMenu")

    def Activated(self, *_args: Any) -> None:  # noqa: N802
        logger.debug("ISapSessionEvents.Activated")

    def HistoryOpened(self, *_args: Any) -> None:  # noqa: N802
        logger.debug("ISapSessionEvents.HistoryOpened")

    def ProgressIndicator(self, *_args: Any) -> None:  # noqa: N802
        logger.debug("ISapSessionEvents.ProgressIndicator=%r", _args)

    def AbapScriptingEvent(self, *_args: Any) -> None:  # noqa: N802
        logger.debug("ISapSessionEvents.AbapScriptingEvent=%r", _args)


def acao_from_hit(component: Any, inner_object: Any = None) -> Acao | None:
    """Traduz eventos ``Hit`` em ações transitórias."""
    sap_type = str(safe_get(component, "Type", "") or "")
    if sap_type in ("GuiButton", "GuiMenu", "GuiRadioButton", "GuiTab"):
        return acao_from_component(component, origem="com_hit")
    if sap_type in ("GuiGridView", "GuiShell"):
        row = int(safe_get(component, "CurrentCellRow", -1) or -1)
        column = str(safe_get(component, "CurrentCellColumn", "") or "")
        oid = str(safe_get(component, "Id", "") or "")
        if oid and row >= 0 and column:
            return Acao(
                tipo="set_current_cell",
                obj_id=oid,
                args={"row": row, "column": column, "inner": str(inner_object or "")},
                origem="com_hit",
            )
    return None


def _command_array_values(command_array: Any) -> list[str]:
    """Normaliza o Variant ``CommandArray`` para diagnóstico e decodificação."""
    if command_array is None:
        return []
    if isinstance(command_array, str):
        return [command_array]
    if isinstance(command_array, (list, tuple)):
        return [str(value) for value in command_array]
    values: list[str] = []
    for index in range(com_len(command_array)):
        value = com_item(command_array, index)
        if value is not None:
            values.append(str(value))
    return values


def _as_sequence(value: Any) -> list[Any]:
    """Converte SAFEARRAY/coleção COM em lista, preservando tipos.

    Valores escalares (``str``, ``bytes``, números, ``bool``) são argumentos
    atômicos — **não** coleções COM. Iterá-los via :func:`com_len`/:func:`com_item`
    quebraria uma string como ``"4900000618"`` caractere a caractere (``com_len``
    cai no ``len()`` da string e ``com_item`` no indexador ``s[i]``), e o chamador
    acabaria pegando apenas ``s[0]``. Por isso são devolvidos intactos como um
    único elemento.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, (str, bytes, bool, int, float)):
        return [value]
    values: list[Any] = []
    for index in range(com_len(value)):
        values.append(com_item(value, index))
    return values


def _as_dispatch(value: Any) -> Any:
    """Envolve ``PyIDispatch`` cru sem consultar ou gerar type libraries."""
    if value is None or safe_get(value, "Id") is not None:
        return value
    try:
        import win32com.client.dynamic

        return win32com.client.dynamic.Dispatch(value)
    except Exception:  # noqa: BLE001 - valor pode não ser IDispatch
        return value


def _command_lines(command_array: Any) -> list[list[Any]]:
    """Normaliza as linhas ``(tipo, nome[, argumentos])`` do Change.

    Aceita ``len >= 2`` porque métodos **sem argumento** (``doubleClickCurrentCell``,
    ``pressButton`` sem parâmetro etc.) chegam como uma linha de 2 elementos
    ``("M", "nome")``. Exigir ``>= 3`` descartava silenciosamente esses comandos —
    foi o que sumia com o duplo-clique em célula de grid. Linhas ``SP`` sem valor
    são descartadas adiante (em :func:`acoes_from_command_array`).
    """
    values = _as_sequence(command_array)
    if len(values) >= 2 and str(values[0]).upper() in {"M", "SP"}:
        return [values]
    lines: list[list[Any]] = []
    for value in values:
        line = _as_sequence(value)
        if len(line) >= 2 and str(line[0]).upper() in {"M", "SP"}:
            lines.append(line)
    return lines


def _command_args(value: Any) -> list[Any]:
    """Normaliza o terceiro membro de uma linha do CommandArray."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    sequence = _as_sequence(value)
    return sequence if sequence else [value]


def acoes_from_command_array(component: Any, command_array: Any) -> list[Acao]:
    """Traduz comandos oficiais emitidos pelo modo de gravação do SAP."""
    object_id = str(safe_get(component, "Id", "") or "")
    if not object_id:
        return []
    actions: list[Acao] = []
    for line in _command_lines(command_array):
        command_type, command_name = line[:2]
        name = str(command_name or "")
        raw_args = line[2:]
        args = (
            _command_args(raw_args[0])
            if len(raw_args) == 1
            else list(raw_args)
        )
        if not name:
            continue
        if str(command_type).upper() == "SP":
            if not args:
                continue
            if name.lower() in _IGNORED_COMMAND_PROPERTIES:
                logger.debug(
                    "acoes_from_command_array: propriedade '%s' ignorada (sem efeito funcional).",
                    name,
                )
                continue
            actions.append(
                Acao(
                    tipo="property_set",
                    obj_id=object_id,
                    args={"property": name, "value": args[0]},
                    origem="com_event",
                )
            )
        elif str(command_type).upper() == "M":
            actions.append(
                Acao(
                    tipo="method_call",
                    obj_id=object_id,
                    args={"method": name, "args": args},
                    origem="com_event",
                )
            )
    logger.debug("ISapSessionEvents.Change CommandArray=%r", _command_array_values(command_array))
    return actions


class ComRecorder:
    """Grava interações com componentes normais via evento ``GuiSession.Change``.

    Args:
        session: Objeto COM ``GuiSession``.
        sink: Callback chamado com cada :class:`Acao` capturada.
    """

    def __init__(self, session: Any, sink: ActionSink) -> None:
        self._session = session
        self._sink = sink
        self._handler: Any | None = None
        self._connection: Any | None = None
        self._active = False
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._record_before: bool | None = None
        self._connection_index, self._session_index = self._extract_indices(session)

    @property
    def is_running(self) -> bool:
        return self._active

    def start(self) -> None:
        """Conecta o event sink à sessão (degrada se pywin32 ausente)."""
        if self._active:
            return
        self._stop.clear()
        self._ready.clear()
        self._thread = threading.Thread(
            target=self._run_event_loop,
            name="SapSessionEvents",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait(timeout=3.0)
        if self._active:
            logger.info(
                "ComRecorder: conectado diretamente ao ISapSessionEvents."
            )
        else:
            logger.warning(
                "ComRecorder INATIVO: connection point ISapSessionEvents indisponível."
            )

    def stop(self) -> None:
        """Desconecta o event sink (descarta a referência ao handler)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        self._handler = None
        self._connection = None
        self._active = False
        logger.info("ComRecorder parado.")

    # ------------------------------------------------------------------ #
    def _run_event_loop(self) -> None:
        """Mantém connection point e bombeamento COM em uma thread STA."""
        try:
            import pythoncom
            import pywintypes
            import win32com.client
            from win32com.client.connect import SimpleConnection
        except ImportError:
            self._ready.set()
            return
        pythoncom.CoInitialize()
        try:
            session = self._acquire_thread_session(win32com.client)
            if session is None:
                return
            handler = _DirectSessionEventSink(self._sink)
            connection = SimpleConnection(
                session,
                handler,
                pywintypes.IID(SAP_SESSION_EVENTS_IID),
            )
            self._handler = handler
            self._connection = connection
            self._record_before = bool(safe_get(session, "Record", False))
            session.Record = True
            self._active = True
            self._ready.set()
            while not self._stop.wait(0.01):
                pythoncom.PumpWaitingMessages()
        except Exception as exc:  # noqa: BLE001 - fronteira COM
            logger.warning(
                "ComRecorder: falha ao conectar diretamente ao ISapSessionEvents — %s",
                exc,
            )
        finally:
            self._ready.set()
            if "session" in locals() and session is not None and self._record_before is not None:
                try:
                    session.Record = self._record_before
                    pythoncom.PumpWaitingMessages()
                except Exception:  # noqa: BLE001 - teardown best-effort
                    pass
            self._record_before = None
            if self._connection is not None:
                try:
                    self._connection.Disconnect()
                except Exception:  # noqa: BLE001 - teardown best-effort
                    pass
            self._connection = None
            self._handler = None
            self._active = False
            pythoncom.CoUninitialize()

    def _acquire_thread_session(self, client: Any) -> Any | None:
        """Obtém a sessão no apartamento COM da thread de eventos."""
        sap = None
        for acquire in (
            lambda: client.GetObject("SAPGUI"),
            lambda: client.GetActiveObject("SAPGUI"),
        ):
            try:
                sap = acquire()
                break
            except Exception:  # noqa: BLE001 - tenta estratégia seguinte
                continue
        if sap is None:
            return None
        engine = safe_get(sap, "GetScriptingEngine")
        if engine is None:
            return None
        try:
            return engine.Children(self._connection_index).Children(self._session_index)
        except Exception:  # noqa: BLE001 - variação de coleção COM
            try:
                return engine.Children.ElementAt(self._connection_index).Children.ElementAt(
                    self._session_index
                )
            except Exception:  # noqa: BLE001
                return None

    @staticmethod
    def _extract_indices(session: Any) -> tuple[int, int]:
        """Extrai ``con[N]`` e ``ses[N]`` do ID absoluto da sessão."""
        session_id = str(safe_get(session, "Id", "") or "")
        parent_id = str(safe_get(safe_get(session, "Parent"), "Id", "") or "")
        connection_match = re.search(r"con\[(\d+)]", session_id)
        if connection_match is None:
            connection_match = re.search(r"con\[(\d+)]", parent_id)
        session_match = re.search(r"ses\[(\d+)]", session_id)
        return (
            int(connection_match.group(1)) if connection_match else 0,
            int(session_match.group(1)) if session_match else 0,
        )

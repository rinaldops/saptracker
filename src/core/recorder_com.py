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

from collections.abc import Callable
from typing import Any

from src.codegen.base import Acao
from src.core.com_utils import safe_get
from src.utils.logger import get_logger

logger = get_logger(__name__)

ActionSink = Callable[[Acao], None]

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
        return None
    sap_type = str(safe_get(component, "Type", "") or "")
    mapeado = _TYPE_MAP.get(sap_type)
    if mapeado is None:
        return None

    tipo_acao, _prop = mapeado
    args: dict[str, Any] = {}
    if tipo_acao == "set_text":
        args = {"text": str(safe_get(component, "Text", "") or "")}
    elif tipo_acao == "set_combo_key":
        args = {"key": str(safe_get(component, "Key", "") or "")}
    elif tipo_acao == "set_checkbox":
        args = {"selected": bool(safe_get(component, "Selected", False))}

    return Acao(tipo=tipo_acao, obj_id=oid, args=args, origem=origem, timestamp=timestamp)


class _SessionEventSink:
    """Sink de eventos do ``GuiSession`` para uso com ``win32com WithEvents``.

    O pywin32 invoca o método cujo nome corresponde ao evento. Dependendo da
    versão/typelib o nome pode vir como ``Change`` ou ``OnChange``; ambos são
    fornecidos e delegam ao mesmo tratador.
    """

    #: Preenchido por :meth:`ComRecorder._attach` após a instância ser criada
    #: pelo pywin32 (que não nos deixa passar argumentos ao construtor).
    _sink: ActionSink | None = None

    def _on_change(self, component: Any, *_: Any) -> None:
        if self._sink is None:
            return
        acao = acao_from_component(component)
        if acao is not None:
            self._sink(acao)

    # Variantes de nome de evento que o pywin32 pode chamar.
    def OnChange(self, _session: Any, component: Any, *rest: Any) -> None:  # noqa: N802
        self._on_change(component, *rest)

    def Change(self, _session: Any, component: Any, *rest: Any) -> None:  # noqa: N802
        self._on_change(component, *rest)


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
        self._active = False

    @property
    def is_running(self) -> bool:
        return self._active

    def start(self) -> None:
        """Conecta o event sink à sessão (degrada se pywin32 ausente)."""
        if self._active:
            return
        self._active = self._attach()
        if self._active:
            logger.info("ComRecorder conectado ao evento GuiSession.Change.")
        else:
            logger.warning(
                "ComRecorder inativo: eventos COM indisponíveis nesta plataforma."
            )

    def stop(self) -> None:
        """Desconecta o event sink (descarta a referência ao handler)."""
        if self._handler is not None:
            # Soltar a referência faz o pywin32 desconectar o sink na coleta.
            self._handler._sink = None
            self._handler = None
        self._active = False
        logger.info("ComRecorder parado.")

    # ------------------------------------------------------------------ #
    def _attach(self) -> bool:
        """Tenta conectar ``WithEvents`` à sessão. Retorna sucesso."""
        try:
            import win32com.client
        except ImportError:
            return False
        try:
            handler = win32com.client.WithEvents(self._session, _SessionEventSink)
            handler._sink = self._sink
            self._handler = handler
            return True
        except Exception as e:  # noqa: BLE001 - sessão pode não expor typelib de eventos
            logger.debug("WithEvents falhou: %s", e)
            return False

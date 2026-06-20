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
import time as _time
from collections.abc import Callable
from typing import Any

from src.codegen.base import Acao
from src.core.analyser import Analyser
from src.core.com_utils import com_item, com_len, safe_com_call, safe_get
from src.core.shell_handlers import get_handler
from src.utils.logger import get_logger

logger = get_logger(__name__)

#: Assinatura do callback que recebe cada ação capturada.
ActionSink = Callable[[Acao], None]

#: Intervalo padrão entre ciclos de polling (segundos).
DEFAULT_POLL_INTERVAL = 0.25

#: Tipos de campo interativo "normal" (não GuiShell) que o PollingRecorder
#: captura por snapshot/diff quando o motor COM (WithEvents) não está disponível.
_FIELD_TYPES: dict[str, str] = {
    "GuiTextField":     "set_text",
    "GuiCTextField":    "set_text",
    "GuiOkCodeField":   "set_text",
    "GuiPasswordField": "set_text",
    "GuiComboBox":      "set_combo_key",
    "GuiCheckBox":      "set_checkbox",
    "GuiRadioButton":   "select",
    # GuiTabStrip — detecta qual aba está selecionada (não tem valor, usa SelectedTab).
    "GuiTabStrip":      "select",
}


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


def snapshot_field(obj: Any, sap_type: str) -> dict[str, Any]:
    """Captura o estado atual de um campo interativo normal (não-shell).

    Função pura em relação ao buffer — não toca em threads.

    Args:
        obj: Objeto COM do campo.
        sap_type: Tipo SAP do campo (ex.: ``"GuiTextField"``).

    Returns:
        Dicionário com a chave ``"tipo"`` e o valor relevante do campo.
    """
    snap: dict[str, Any] = {"tipo": sap_type}
    if sap_type in ("GuiTextField", "GuiCTextField", "GuiOkCodeField", "GuiPasswordField"):
        snap["text"] = str(safe_get(obj, "Text", "") or "")
    elif sap_type == "GuiComboBox":
        snap["key"] = str(safe_get(obj, "Key", "") or "")
    elif sap_type in ("GuiCheckBox", "GuiRadioButton"):
        snap["selected"] = bool(safe_get(obj, "Selected", False))
    elif sap_type == "GuiTabStrip":
        sel = safe_get(obj, "SelectedTab")
        snap["selected_tab_id"] = str(safe_get(sel, "Id", "") or "") if sel is not None else ""
    return snap


def diff_field(
    obj_id: str, sap_type: str, antes: dict[str, Any], depois: dict[str, Any]
) -> list[Acao]:
    """Compara dois snapshots de um campo normal e devolve as ações resultantes.

    Função pura — não toca em COM nem em threads.

    Args:
        obj_id: ID completo do campo SAP.
        sap_type: Tipo SAP do campo.
        antes: Snapshot anterior.
        depois: Snapshot atual.

    Returns:
        Lista de ações (vazia se nada relevante mudou).
    """
    out: list[Acao] = []
    if sap_type in ("GuiTextField", "GuiCTextField", "GuiOkCodeField", "GuiPasswordField"):
        if antes.get("text") != depois.get("text"):
            out.append(Acao(
                tipo="set_text",
                obj_id=obj_id,
                args={"text": str(depois.get("text", ""))},
                origem="campo",
            ))
    elif sap_type == "GuiComboBox":
        if antes.get("key") != depois.get("key"):
            out.append(Acao(
                tipo="set_combo_key",
                obj_id=obj_id,
                args={"key": str(depois.get("key", ""))},
                origem="campo",
            ))
    elif sap_type == "GuiCheckBox":
        if antes.get("selected") != depois.get("selected"):
            out.append(Acao(
                tipo="set_checkbox",
                obj_id=obj_id,
                args={"selected": bool(depois.get("selected", False))},
                origem="campo",
            ))
    elif sap_type == "GuiRadioButton":
        # Emite apenas quando o radio PASSA a estar selecionado.
        if not antes.get("selected", False) and depois.get("selected", False):
            out.append(Acao(tipo="select", obj_id=obj_id, args={}, origem="campo"))
    elif sap_type == "GuiTabStrip":
        new_tab = str(depois.get("selected_tab_id", ""))
        if new_tab and antes.get("selected_tab_id") != new_tab:
            out.append(Acao(tipo="select", obj_id=new_tab, args={}, origem="campo"))
    return out


def collect_fields(session: Any) -> list[tuple[str, Any, str]]:
    """Descobre campos interativos normais (não-shell) via travessia direta do COM.

    Usa travessia direta (sem ``Analyser.build_tree()``) para evitar a
    introspecção de GuiShell, que é cara e desnecessária para campos simples.

    Returns:
        Lista de ``(obj_id, obj_com, sap_type)`` para cada campo interativo
        encontrado na hierarquia de janelas da sessão.
    """
    pares: list[tuple[str, Any, str]] = []
    ignorados_readonly: list[str] = []
    ignorados_tab_inativo: list[str] = []

    # Tipos de contêiner cujas sub-árvores NUNCA contêm campos de entrada
    # interativos e podem ser muito grandes.
    #   - GuiMenubar / GuiMenu / GuiMenuItem: a barra de menus do SESSION_MANAGER
    #     tem 600+ nós.  Pular elimina ~600 chamadas COM por ciclo (era ~0.67 s).
    #   - GuiShell: seus dados são tratados pelo collect_shells (Analyser); não
    #     tem filhos do tipo GuiTextField etc. — pular evita traversal redundante.
    #   - GuiTitlebar: barra de título, sem campos editáveis.
    # NÃO incluir GuiToolbar: o campo okcd (GuiOkCodeField) fica dentro de tbar[0].
    _SKIP_SUBTREE = frozenset({
        "GuiMenubar", "GuiMenu", "GuiMenuItem",
        "GuiShell", "GuiTitlebar",
    })

    def _traverse(obj: Any, depth: int) -> None:
        if obj is None or depth > 20:
            return
        sap_type = str(safe_get(obj, "Type", "") or "")

        # Pula sub-árvores sem campos de entrada — barra de menus, toolbars etc.
        if sap_type in _SKIP_SUBTREE:
            return

        # GuiTab inativo (aba não selecionada) tem Changeable=False.
        # Diagnóstico ao vivo confirmou: abas inativas têm Changeable=False;
        # abas ativas têm Changeable=True. Pular a sub-árvore inteira evita
        # capturar campos de abas não visíveis ao usuário.
        # IMPORTANTE: Changeable só é lido para GuiTab/campos — não para todo
        # objeto genérico, pois alguns containers SAP causam cascade COM no
        # pywin32 quando acessamos propriedades inexistentes via dispatch tardio.
        if sap_type == "GuiTab":
            oid_tab = str(safe_get(obj, "Id", "") or "")
            if safe_get(obj, "Changeable", None) is False:
                ignorados_tab_inativo.append(oid_tab)
                return
        if sap_type in _FIELD_TYPES:
            oid = str(safe_get(obj, "Id", "") or "")
            if oid:
                # GuiTabStrip não tem Changeable; campos de texto/combo têm.
                # Se Changeable=False o campo é somente-leitura → pula.
                if sap_type != "GuiTabStrip":
                    if safe_get(obj, "Changeable", None) is False:
                        ignorados_readonly.append(f"{sap_type}:{oid.split('/')[-1]}")
                    else:
                        pares.append((oid, obj, sap_type))
                else:
                    pares.append((oid, obj, sap_type))
        children = safe_get(obj, "Children")
        if children is not None:
            for i in range(com_len(children)):
                child = com_item(children, i)
                if child is not None:
                    _traverse(child, depth + 1)

    try:
        top = safe_get(session, "Children")
        if top is None:
            return pares
        for i in range(com_len(top)):
            child = com_item(top, i)
            if child is not None:
                _traverse(child, 0)
    except Exception as e:  # noqa: BLE001 - travessia é best-effort
        logger.warning("collect_fields: erro na travessia COM — %s", e)

    if pares:
        logger.info(
            "collect_fields: %d campo(s) encontrado(s) | %d read-only ignorados "
            "| %d abas inativas puladas",
            len(pares), len(ignorados_readonly), len(ignorados_tab_inativo),
        )
        for oid, obj, sap_type in pares:
            val = snapshot_field(obj, sap_type)
            val_str = (
                val.get("text") or val.get("key")
                or val.get("selected_tab_id") or str(val.get("selected", ""))
            )
            logger.debug("  CAMPO %-20s %-60s = %r", sap_type, oid.split("/")[-1], val_str)
        if ignorados_readonly:
            logger.debug("  READ-ONLY ignorados: %s", ignorados_readonly)
        if ignorados_tab_inativo:
            logger.debug(
                "  TABS INATIVAS puladas: %s",
                [t.split("/")[-1] for t in ignorados_tab_inativo],
            )
    else:
        logger.info("collect_fields: nenhum campo interativo na tela atual.")
    return pares


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
        logger.debug("collect_shells: falha ao percorrer árvore SAP — %s", e)
        return pares
    for node in tree.flatten():
        if not node.is_shell or not node.id:
            continue
        obj = analyser.find_by_id(node.id)
        if obj is not None:
            pares.append((node.id, obj))
    if pares:
        logger.debug(
            "collect_shells: %d GuiShell(s) encontrado(s): %s",
            len(pares),
            [p[0] for p in pares],
        )
    else:
        logger.debug("collect_shells: nenhum GuiShell encontrado na tela atual.")
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
        capture_fields: bool = True,
        capture_shells: bool = True,
    ) -> None:
        self._session = session
        self._sink = sink
        self._poll_interval = poll_interval
        self._capture_fields = capture_fields
        self._capture_shells = capture_shells
        #: Última leitura de "há janela modal SAP aberta?" (``wnd[1]`` …).
        #: Atualizada a cada ciclo a partir do thread COM confiável do polling;
        #: consumida pelo Win32Recorder para não capturar modais SAP via AutoItX.
        self._modal_open = False
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        #: Último snapshot de GuiShell por obj_id.
        self._snapshots: dict[str, dict[str, Any]] = {}
        #: Snapshot do ciclo anterior de cada campo normal.
        self._field_snapshots: dict[str, dict[str, Any]] = {}
        #: Snapshot no momento em que o campo foi visto PELA PRIMEIRA VEZ durante
        #: esta gravação. Usado para detectar mudança líquida real vs. ruído de
        #: refresh do SAP (que faz campos voltarem ao valor original).
        self._field_baselines: dict[str, dict[str, Any]] = {}
        #: Mudanças de campo aguardando confirmação (debounce de 1 ciclo).
        #: Chave: obj_id; valor: (ação a emitir, snapshot que deve se confirmar).
        self._pending_field: dict[str, tuple[Acao, dict[str, Any]]] = {}
        #: Referência à sessão re-adquirida dentro da thread de polling.
        self._thread_session: Any | None = None
        #: Índices da conexão e sessão extraídos da sessão original.
        self._conn_idx, self._sess_idx = self._extract_session_indices(session)
        #: Chave da tela SAP atual para detectar transições de tela.
        self._screen_key: str = ""
        #: Cache de GuiShell encontrados na tela atual.  Evita chamar
        #: Analyser.build_tree() a cada ciclo (pode levar 2-3 s em telas com
        #: grandes árvores de navegação como SESSION_MANAGER).
        #: None = cache inválido, precisa re-escanear.
        self._cached_shells: list[tuple[str, Any]] | None = None
        #: Cache de campos interativos da tela atual (oid, obj_ref, sap_type).
        #: Evita re-traversal da árvore COM a cada ciclo — os objetos COM
        #: permanecem válidos enquanto a tela não muda.  None = cache inválido.
        self._cached_fields: list[tuple[str, Any, str]] | None = None
        #: Transação SAP do último ciclo estável (ex.: "MIGO", "SESSION_MANAGER").
        #: Usada para inferir o comando de navegação no okcd quando o usuário digita
        #: e pressiona Enter mais rápido do que o ciclo de polling consegue capturar.
        self._last_transaction: str = ""
        #: True se o okcd desta tela já foi emitido explicitamente pelo polling.
        #: Evita emitir também o nav_trans (inferido), que geraria duplo set_text.
        self._okcd_emitted: bool = False
        #: Shells que falharam ao serem lidas (COM error) — suprime logs repetidos.
        self._broken_shell_oids: set[str] = set()

    # ------------------------------------------------------------------ #
    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def modal_window_open(self) -> bool:
        """``True`` se a última leitura viu uma janela modal SAP (``wnd[1]`` …)."""
        return self._modal_open

    def set_capture_fields(self, enabled: bool) -> None:
        """Habilita campos normais apenas como fallback quando COM falha."""
        self._capture_fields = enabled

    def set_capture_shells(self, enabled: bool) -> None:
        """Habilita a captura de GuiShell apenas como fallback quando COM falha.

        Quando o motor COM (``ISapSessionEvents`` + ``Record=True``) está ativo,
        ele já grava as interações com GuiShell de forma completa via
        ``CommandArray`` — inclusive ações transitórias (duplo-clique, expandir nó,
        pressionar botão de toolbar) que o snapshot/diff **não** consegue observar.
        Nesse caso o polling de shells é redundante e geraria linhas duplicadas.
        """
        self._capture_shells = enabled

    def start(self) -> None:
        """Inicia a thread de polling (no-op se já estiver rodando)."""
        if self.is_running:
            return
        self._stop.clear()
        self._snapshots.clear()
        self._field_snapshots.clear()
        self._field_baselines.clear()
        self._pending_field.clear()
        self._screen_key = ""
        self._last_transaction = ""
        self._cached_shells = None
        self._cached_fields = None
        self._okcd_emitted = False
        self._broken_shell_oids = set()
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
        # Drena mudanças pendentes que ainda não se confirmaram mas representam
        # o estado final (campo ficou com novo valor quando gravação foi parada).
        self._flush_pending_fields(emit=True)
        logger.info("PollingRecorder parado.")

    # ------------------------------------------------------------------ #
    def _run(self) -> None:
        """Loop principal da thread: inicializa COM e cicla até parar."""
        co_initialized = self._co_initialize()
        try:
            # Re-adquire a sessão neste apartamento COM para evitar cross-STA
            # marshaling com a thread Qt (que causava session.Children inacessível).
            self._thread_session = self._acquire_thread_session() or self._session
            logger.info(
                "PollingRecorder._run: usando sessão %s.",
                "re-adquirida via GetObject(SAPGUI)"
                if self._thread_session is not self._session
                else "original (fallback)",
            )
            # Primeiro ciclo apenas estabelece a linha de base (sem emitir).
            self.poll_once(emit=False)
            while not self._stop.wait(self._poll_interval):
                self.poll_once(emit=True)
        finally:
            self._thread_session = None
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
        t_ciclo = _time.monotonic()
        detectadas: list[Acao] = []
        # Usa a sessão re-adquirida na thread (sem cross-STA), se disponível.
        session = self._thread_session if self._thread_session is not None else self._session

        # Atualiza o flag de janela modal SAP (wnd[1] …) lido pelo Win32Recorder.
        # Feito SEMPRE (independe de capturar campos/shells) — é barato e o
        # Win32Recorder depende dele para não capturar modais SAP via AutoItX.
        self._modal_open = self._detect_modal(session)

        # ── GuiShell: usa cache para evitar build_tree() a cada ciclo ────────
        # collect_shells() chama Analyser.build_tree() que percorre TODA a árvore
        # de objetos SAP — em telas com grandes trees (SESSION_MANAGER) isso leva
        # 2-3 s e torna o polling inútil. A lista de shells só muda quando a tela
        # muda, então cacheamos e invalidamos apenas na detecção de screen_change.
        t0 = _time.monotonic()
        if not self._capture_shells:
            # COM ativo: GuiShell é gravado pelo CommandArray (mais completo).
            shells = []
        elif self._cached_shells is None:
            shells = collect_shells(session)
            self._cached_shells = shells
            logger.info(
                "collect_shells: %d shell(s) escaneados (%.2fs) — cache estabelecido.",
                len(shells), _time.monotonic() - t0,
            )
        else:
            shells = self._cached_shells
            logger.debug("collect_shells: %d shell(s) (cache).", len(shells))

        for obj_id, obj in shells:
            # Shell COM inválida (já falhou antes): suprime log repetido.
            if obj_id in self._broken_shell_oids:
                continue
            handler = get_handler(obj)
            snap = safe_com_call(handler.tirar_snapshot, obj)
            if snap is None:
                self._broken_shell_oids.add(obj_id)
                logger.info(
                    "poll_once: shell '%s' inacessível via COM — "
                    "ignorada até próxima mudança de tela.",
                    obj_id.split("/")[-1],
                )
                continue
            anterior = self._snapshots.get(obj_id)
            self._snapshots[obj_id] = snap
            if anterior is None:
                logger.debug("poll_once: baseline de shell estabelecida para '%s'.", obj_id)
                continue
            if not emit:
                continue
            acoes = diff_to_acoes(obj_id, anterior, snap)
            if acoes:
                logger.info(
                    "PollingRecorder (shell): %d ação(ões) em '%s': %s",
                    len(acoes), obj_id, [a.tipo for a in acoes],
                )
            for acao in acoes:
                detectadas.append(acao)
                self._sink(acao)

        # ── Detecção de troca de tela ────────────────────────────────────────────
        # Usa Program + título da janela ativa como chave estável.
        # Requer AMBOS para evitar falsos positivos durante o carregamento da
        # tela, quando o SAP exibe briefly título vazio ("SAPLMIGO/") antes do
        # título real — o que gerava duplo SendVKey por ciclo.
        # Info.Screen/Dynpro não estão disponíveis no SAP GUI Scripting padrão.
        info_obj = safe_get(session, "Info")
        current_transaction = str(safe_get(info_obj, "Transaction", "") or "")
        current_screen_key = self._get_screen_key(session)
        screen_changed = (
            bool(self._screen_key)
            and bool(current_screen_key)
            and current_screen_key != self._screen_key
        )

        if screen_changed:
            logger.info(
                "PollingRecorder: tela mudou\n  de: '%s'\n  para: '%s'",
                self._screen_key, current_screen_key,
            )
            # ID do campo okcd (campo de comando SAP).
            okcd_oid = (
                f"/app/con[{self._conn_idx}]/ses[{self._sess_idx}]/wnd[0]/tbar[0]/okcd"
            )
            # Verifica se o okcd foi capturado diretamente pelo polling (ANTES do
            # flush que limpa _pending_field).  Dois casos cobertos:
            #   1. okcd estava PENDENTE (capturado mas não confirmado ainda)
            #   2. okcd já foi EMITIDO nesta tela (_okcd_emitted=True, removido de pending)
            # Sem verificar o caso 2, o usuário que digita devagar (polling captura
            # o valor, emite, Enter chega depois) ainda recebe nav_trans duplicado.
            okcd_capturado = (
                self._okcd_emitted
                or (
                    okcd_oid in self._pending_field
                    and self._snap_has_value(self._pending_field[okcd_oid][1])
                )
            )
            # Drena pendentes da tela anterior (são mudanças legítimas).
            self._flush_pending_fields(emit=emit)
            # Limpa snapshots: nova tela = novo baseline.
            self._snapshots.clear()
            self._field_snapshots.clear()
            self._field_baselines.clear()
            self._cached_shells = None   # Força re-scan de shells na nova tela
            self._cached_fields = None   # Força re-traversal de campos na nova tela
            self._okcd_emitted = False   # Reset do flag de okcd explícito
            self._broken_shell_oids.clear()  # Shells podem se recuperar na nova tela
            if emit and not okcd_capturado:
                logger.debug(
                    "PollingRecorder: troca de tela sem comando explícito; "
                    "nenhuma navegação será inferida."
                )

        # Atualiza chave de tela APENAS quando a tela tem título completo.
        # Quando vazia (SAP ainda carregando), mantém a chave anterior para
        # não perder referência e não gerar falso screen_changed no próximo ciclo.
        if current_screen_key:
            self._screen_key = current_screen_key
        # Mantém a transação conhecida mais recente (nunca regride para "").
        if current_transaction:
            self._last_transaction = current_transaction

        # ── Campos normais (GuiTextField, GuiComboBox, GuiCheckBox, …) ──────────
        # Estratégia de debounce: só emite uma mudança quando o campo ESTABILIZA
        # (valor igual por 2 ciclos consecutivos) E o valor estável é diferente
        # do baseline original.  Isso elimina o ruído de refresh do SAP que
        # faz campos oscilar ""→"valor"→"" ou "valor"→""→"valor".
        # ── Campos: usa cache para evitar re-traversal da árvore COM a cada ciclo.
        # Os objetos COM (obj_ref) permanecem válidos enquanto a tela não muda.
        # O cache é invalidado em _cached_fields = None no bloco de screen_change.
        if not self._capture_fields:
            return detectadas

        visible_ids: set[str] = set()
        t_f = _time.monotonic()
        if self._cached_fields is None:
            campos_desta_rodada = collect_fields(session)
            if campos_desta_rodada:
                self._cached_fields = campos_desta_rodada
            logger.debug("collect_fields: traversal %.2fs", _time.monotonic() - t_f)
        else:
            campos_desta_rodada = self._cached_fields
            logger.debug("collect_fields: %d campo(s) (cache).", len(campos_desta_rodada))

        logger.info(
            "poll_once: %d campo(s) visíveis | %d pendentes | emit=%s | tela='%s'",
            len(campos_desta_rodada), len(self._pending_field), emit,
            (self._screen_key or "?")[-60:],
        )
        for obj_id, obj, sap_type in campos_desta_rodada:
            visible_ids.add(obj_id)
            snap_f = snapshot_field(obj, sap_type)
            anterior_f = self._field_snapshots.get(obj_id)
            self._field_snapshots[obj_id] = snap_f

            if anterior_f is None:
                # Primeira aparição: estabelece baseline e não emite.
                self._field_baselines[obj_id] = snap_f
                val_str = (snap_f.get("text") or snap_f.get("key")
                           or snap_f.get("selected_tab_id") or str(snap_f.get("selected", "")))
                logger.info(
                    "  BASELINE %-20s %-40s = %r",
                    sap_type, obj_id.split("/")[-1], val_str,
                )
                continue

            val_antes = (
                anterior_f.get("text") or anterior_f.get("key")
                or anterior_f.get("selected_tab_id")
                or str(anterior_f.get("selected", ""))
            )
            val_depois = (
                snap_f.get("text") or snap_f.get("key")
                or snap_f.get("selected_tab_id") or str(snap_f.get("selected", ""))
            )

            if snap_f == anterior_f:
                # Campo ESTÁVEL neste ciclo → confirma pendente, se existir.
                if obj_id in self._pending_field:
                    pending_acao, pending_snap = self._pending_field.pop(obj_id)
                    baseline = self._field_baselines.get(obj_id)
                    val_base = (baseline or {}).get("text") or (baseline or {}).get("key") or ""
                    val_pend = (
                        pending_snap.get("text") or pending_snap.get("key")
                        or pending_snap.get("selected_tab_id")
                        or str(pending_snap.get("selected", ""))
                    )
                    if (
                        baseline is not None
                        and pending_snap != baseline
                        and self._snap_has_value(pending_snap)
                    ):
                        # Mudança líquida real com valor não-vazio: emite.
                        if emit:
                            logger.info(
                                "  EMIT %-20s %-40s  %r → %r  (era baseline %r)",
                                sap_type, obj_id.split("/")[-1], val_antes, val_pend, val_base,
                            )
                            detectadas.append(pending_acao)
                            self._sink(pending_acao)
                            # Marca se o okcd foi emitido explicitamente para
                            # suprimir nav_trans duplicado na screen_change.
                            if sap_type == "GuiOkCodeField":
                                self._okcd_emitted = True
                        else:
                            logger.debug(
                                "  EMIT(bloqueado emit=False) %-40s %r → %r",
                                obj_id.split("/")[-1], val_base, val_pend,
                            )
                    else:
                        logger.info(
                            "  DESCARTADO %-20s %-40s  pend=%r base=%r (voltou ou vazio)",
                            sap_type, obj_id.split("/")[-1], val_pend, val_base,
                        )
                else:
                    logger.debug(
                        "  estável    %-20s %-40s = %r",
                        sap_type, obj_id.split("/")[-1], val_depois,
                    )
            else:
                # Campo MUDOU neste ciclo → coloca (ou atualiza) no debounce.
                acoes_f = diff_field(obj_id, sap_type, anterior_f, snap_f)
                if acoes_f:
                    self._pending_field[obj_id] = (acoes_f[-1], snap_f)
                    logger.info(
                        "  MUDOU %-20s %-40s  %r → %r  [PENDENTE]",
                        sap_type, obj_id.split("/")[-1], val_antes, val_depois,
                    )
                else:
                    logger.debug(
                        "  mudou(sem ação) %-20s %-40s  %r → %r",
                        sap_type, obj_id.split("/")[-1], val_antes, val_depois,
                    )

        # Campos que desapareceram da tela (ex.: troca de aba sem mudar dynpro).
        # Drena pendentes cujo valor é diferente do baseline (mudança real).
        desaparecidos = set(self._pending_field) - visible_ids
        if desaparecidos:
            logger.info(
                "poll_once: %d campo(s) desapareceram da tela: %s",
                len(desaparecidos), [k.split("/")[-1] for k in desaparecidos],
            )
        for obj_id in desaparecidos:
            pending_acao, pending_snap = self._pending_field.pop(obj_id)
            baseline = self._field_baselines.get(obj_id)
            val_base = (baseline or {}).get("text") or (baseline or {}).get("key") or ""
            val_pend = (
                pending_snap.get("text") or pending_snap.get("key")
                or pending_snap.get("selected_tab_id")
                or str(pending_snap.get("selected", ""))
            )
            if (
                baseline is not None
                and pending_snap != baseline
                and self._snap_has_value(pending_snap)
            ):
                if emit:
                    logger.info(
                        "  EMIT(desapareceu) %-40s  %r → %r",
                        obj_id.split("/")[-1], val_base, val_pend,
                    )
                    detectadas.append(pending_acao)
                    self._sink(pending_acao)
            else:
                logger.info(
                    "  DESCARTADO(desapareceu) %-40s  pend=%r base=%r",
                    obj_id.split("/")[-1], val_pend, val_base,
                )

        t_total = _time.monotonic() - t_ciclo
        if t_total > 0.5:
            logger.warning(
                "poll_once LENTO: %.2fs (ciclo deveria ser ~%.2fs). "
                "Possível contenção COM ou tela com muitos objetos.",
                t_total, self._poll_interval,
            )
        else:
            logger.debug("poll_once: %.2fs total.", t_total)

        return detectadas

    # ------------------------------------------------------------------ #
    @staticmethod
    def _get_screen_key(session: Any) -> str:
        """Retorna uma chave estável que identifica a tela SAP atual.

        Exige AMBOS o programa ABAP (``Info.Program``) E o título da janela
        (``ActiveWindow.Text``) preenchidos. Durante a navegação o SAP exibe
        brevemente uma tela com título vazio; nesse estado a função retorna ""
        e o chamador NÃO atualiza ``_screen_key``, evitando falsos positivos
        de troca de tela (que geravam duplo ``SendVKey`` por navegação).

        ``Info.Screen``/``Info.Dynpro`` não estão disponíveis via COM no SAP GUI
        Scripting padrão, portanto não são usados.
        """
        info = safe_get(session, "Info")
        prog = str(safe_get(info, "Program", "") or "")
        wnd = safe_get(session, "ActiveWindow")
        title = str(safe_get(wnd, "Text", "") or "")
        if prog and title:
            return f"{prog}/{title}"
        return ""

    def _detect_modal(self, session: Any) -> bool:
        """``True`` se a sessão tem janela modal aberta (``Children.Count > 1``).

        ``wnd[0]`` é a janela principal; qualquer filho adicional é um
        ``GuiModalWindow`` (popup do próprio SAP). Em erro COM, preserva o último
        valor conhecido para não oscilar durante o loop modal do SAP.
        """
        try:
            children = safe_get(session, "Children")
            count = com_len(children)
            return count > 1 if count else self._modal_open
        except Exception:  # noqa: BLE001 - fronteira COM, best-effort
            return self._modal_open

    @staticmethod
    def _snap_has_value(snap: dict[str, Any]) -> bool:
        """True se o snapshot tem um valor significativo (não-vazio).

        Transições *para vazio* (text="", key="") quase sempre indicam
        artefatos de navegação SAP (sub-tela voltando ao estado inicial),
        não ações do usuário. Checkboxes (selected) e seleção de aba
        (selected_tab_id) são sempre significativos.
        """
        if "text" in snap:
            return bool(str(snap["text"]).strip())
        if "key" in snap:
            return bool(str(snap["key"]).strip())
        return True  # selected (checkbox/radio) e selected_tab_id

    def _flush_pending_fields(self, *, emit: bool) -> None:
        """Emite (ou descarta) todas as mudanças de campo que aguardavam confirmação.

        Chamado em dois momentos:
        * Troca de tela: emite mudanças legítimas da tela anterior antes de limpar.
        * Parada da gravação: drena o que ficou pendente como estado final.

        Uma mudança é emitida se:
        1. O snapshot pendente difere do baseline do campo (mudança líquida).
        2. O snapshot pendente tem um valor não-vazio (evita ruído de sub-tela).
        """
        for obj_id, (acao, pending_snap) in list(self._pending_field.items()):
            baseline = self._field_baselines.get(obj_id)
            if (
                baseline is not None
                and pending_snap != baseline
                and self._snap_has_value(pending_snap)
            ):
                if emit:
                    logger.info(
                        "PollingRecorder flush: emitindo campo pendente '%s' (%r ≠ baseline %r).",
                        obj_id, pending_snap, baseline,
                    )
                    self._sink(acao)
                    # Também marca okcd se foi flushed no screen_change
                    if acao.tipo == "set_text" and acao.obj_id.endswith("/okcd"):
                        self._okcd_emitted = True
            else:
                logger.debug(
                    "PollingRecorder flush: campo '%s' descartado (voltou ao baseline ou vazio).",
                    obj_id,
                )
        self._pending_field.clear()

    @staticmethod
    def _extract_session_indices(session: Any) -> tuple[int, int]:
        """Extrai (conn_idx, sess_idx) do ID do objeto sessão SAP.

        O ID de ``GuiSession`` segue o formato ``"ses[N]"`` e o ID da conexão
        pai segue ``"con[M]"``. Se não for possível parsear, retorna ``(0, 0)``.
        """
        def _parse_idx(id_str: str, default: int = 0) -> int:
            try:
                return int(id_str.split("[")[1].rstrip("]"))
            except (IndexError, ValueError):
                return default

        sess_id = str(safe_get(session, "Id", "ses[0]") or "ses[0]")
        sess_idx = _parse_idx(sess_id)

        parent = safe_get(session, "Parent")
        conn_id = str(safe_get(parent, "Id", "con[0]") or "con[0]")
        conn_idx = _parse_idx(conn_id)

        logger.debug(
            "PollingRecorder: sessão em con[%d]/ses[%d] (ids: %r, %r).",
            conn_idx, sess_idx, conn_id, sess_id,
        )
        return conn_idx, sess_idx

    def _acquire_thread_session(self) -> Any | None:
        """Obtém uma referência à sessão válida no apartamento COM desta thread.

        Chama ``GetObject("SAPGUI")`` diretamente na thread de polling para
        criar um proxy COM no apartamento STA desta thread, evitando o problema
        de cross-STA marshaling com a thread Qt (que tornava ``session.Children``
        inacessível quando a referência original era criada na thread Qt).

        IMPORTANTE: esta chamada ocorre na PRÓPRIA thread de polling (depois do
        CoInitialize) para que o objeto COM criado fique no mesmo apartamento
        que será usado no loop de polling. Usar uma thread auxiliar causaria
        CoUninitialize prematuro, invalidando o objeto.
        """
        t0 = _time.monotonic()
        try:
            import win32com.client
            sap = win32com.client.GetObject("SAPGUI")
            engine = sap.GetScriptingEngine
            sess = engine.Children(self._conn_idx).Children(self._sess_idx)
            elapsed = _time.monotonic() - t0
            logger.info(
                "PollingRecorder._acquire_thread_session: sessão re-adquirida "
                "em con[%d]/ses[%d] (%.2fs).",
                self._conn_idx, self._sess_idx, elapsed,
            )
            return sess
        except Exception as e:  # noqa: BLE001 - best-effort
            elapsed = _time.monotonic() - t0
            logger.warning(
                "PollingRecorder._acquire_thread_session: falhou em %.2fs — %s. "
                "Usando referência original — travessia COM pode não funcionar.",
                elapsed, e,
            )
            return None

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

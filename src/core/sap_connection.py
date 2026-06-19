"""Conexão COM com o SAP GUI Scripting Engine.

Encapsula a obtenção do ``GuiApplication`` via COM e oferece navegação pela
hierarquia ``Connection -> Session``. Toda a interação COM é isolada aqui para
que o restante da aplicação trabalhe com um modelo de objetos previsível.

A árvore de objetos do SAP GUI Scripting é:

    GuiApplication
      └── GuiConnection (Children)
            └── GuiSession (Children)
                  └── GuiFrameWindow (wnd[0], wnd[1], ...)
                        └── GuiUserArea / GuiToolbar / ... (controles)
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.core.com_utils import safe_com_call, safe_get
from src.utils.logger import get_logger

logger = get_logger(__name__)

#: ProgID/identificador do objeto SAP GUI registrado no Windows.
SAP_GUI_OBJECT = "SAPGUI"

#: Janela total (s) de tentativas de reconexão antes de desistir (NFR seção 9).
RECONNECT_TIMEOUT_S = 30.0
#: Intervalo (s) entre tentativas de reconexão.
RECONNECT_INTERVAL_S = 1.0


class SapConnectionError(RuntimeError):
    """Erro ao conectar ou interagir com o SAP GUI Scripting Engine."""


@dataclass(frozen=True)
class SessionInfo:
    """Resumo de uma sessão SAP para exibição na UI.

    Attributes:
        connection_index: Índice da conexão dentro do ``GuiApplication``.
        session_index: Índice da sessão dentro da conexão.
        system: Sistema/ID (ex: ``"NSP"``).
        client: Mandante (ex: ``"800"``).
        user: Usuário logado.
        transaction: Transação atual.
        title: Título da janela principal.
    """

    connection_index: int
    session_index: int
    system: str
    client: str
    user: str
    transaction: str
    title: str

    @property
    def label(self) -> str:
        """Rótulo curto para ComboBoxes: ``SYS/CLNT - USER``."""
        sys_part = self.system or "?"
        clnt_part = self.client or "?"
        user_part = self.user or "?"
        return f"{sys_part}/{clnt_part} - {user_part}"


class SapConnection:
    """Gerencia a conexão COM com o SAP GUI e o acesso às sessões.

    Não abre o SAP GUI nem faz logon — assume que o usuário já está logado em
    um SAP GUI for Windows com Scripting habilitado (cliente e servidor).
    """

    def __init__(self) -> None:
        self._application: Any | None = None

    # ------------------------------------------------------------------ #
    # Conexão
    # ------------------------------------------------------------------ #
    @property
    def is_connected(self) -> bool:
        """Indica se há um ``GuiApplication`` válido em cache."""
        if self._application is None:
            return False
        # Acessar uma propriedade barata confirma que o COM ainda responde.
        return safe_get(self._application, "Children") is not None

    def connect(self) -> Any:
        """Obtém (ou revalida) o ``GuiApplication`` via COM.

        Returns:
            O objeto COM ``GuiApplication``.

        Raises:
            SapConnectionError: Se o SAP GUI não estiver acessível.
        """
        if self.is_connected:
            return self._application

        app = self._acquire_application()
        if app is None:
            raise SapConnectionError(
                "Não foi possível obter o SAP GUI Scripting Engine. "
                "Verifique se o SAP GUI for Windows está aberto, com uma sessão "
                "logada e o Scripting habilitado no cliente e no servidor."
            )
        self._application = app
        logger.info("Conectado ao SAP GUI Scripting Engine.")
        return app

    def _acquire_application(self) -> Any | None:
        """Tenta obter o GuiApplication por diferentes estratégias COM."""
        # Estratégia 1: objeto SAPGUI já em execução -> GetScriptingEngine.
        try:
            import win32com.client

            sap_gui_auto = win32com.client.GetObject(SAP_GUI_OBJECT)
            engine = safe_get(sap_gui_auto, "GetScriptingEngine")
            if engine is not None and self._looks_like_application(engine):
                return engine
        except ImportError:
            logger.error("pywin32 (win32com) não está instalado.")
            return None
        except Exception as e:  # noqa: BLE001 - GetObject falha se SAP não roda
            logger.debug("GetObject('SAPGUI') falhou: %s", e)

        # Estratégia 2: objeto ativo na ROT via Marshal/GetActiveObject.
        try:
            import win32com.client

            sap_gui_auto = win32com.client.GetActiveObject(SAP_GUI_OBJECT)
            engine = safe_get(sap_gui_auto, "GetScriptingEngine")
            if engine is not None and self._looks_like_application(engine):
                return engine
        except Exception as e:  # noqa: BLE001
            logger.debug("GetActiveObject('SAPGUI') falhou: %s", e)

        return None

    @staticmethod
    def _looks_like_application(obj: Any) -> bool:
        """Heurística: o objeto expõe ``Children`` como um GuiApplication."""
        return safe_get(obj, "Children") is not None

    def ensure_connected(
        self,
        *,
        timeout: float = RECONNECT_TIMEOUT_S,
        interval: float = RECONNECT_INTERVAL_S,
        _sleep: Callable[[float], None] = time.sleep,
        _clock: Callable[[], float] = time.monotonic,
    ) -> Any:
        """Garante um ``GuiApplication`` válido, reconectando se necessário.

        Se a conexão em cache já responde, retorna imediatamente. Caso contrário,
        descarta a referência morta e tenta readquirir o engine repetidamente por
        até ``timeout`` segundos, aguardando ``interval`` entre as tentativas.

        Args:
            timeout: Janela total de tentativas, em segundos.
            interval: Pausa entre tentativas, em segundos.
            _sleep: Função de espera (injetável em testes).
            _clock: Relógio monotônico (injetável em testes).

        Returns:
            O ``GuiApplication`` reconectado.

        Raises:
            SapConnectionError: Se não reconectar dentro de ``timeout``.
        """
        if self.is_connected:
            return self._application

        # Referência possivelmente morta: limpa antes de tentar readquirir.
        self._application = None
        deadline = _clock() + timeout
        while True:
            app = self._acquire_application()
            if app is not None:
                self._application = app
                logger.info("Reconectado ao SAP GUI Scripting Engine.")
                return app
            if _clock() >= deadline:
                break
            logger.debug("Reconexão falhou; nova tentativa em %.1fs.", interval)
            _sleep(interval)

        raise SapConnectionError(
            f"Não foi possível reconectar ao SAP GUI após {timeout:.0f}s. "
            "Verifique se o SAP GUI for Windows segue aberto com uma sessão logada."
        )

    def disconnect(self) -> None:
        """Libera a referência ao ``GuiApplication`` (não fecha o SAP)."""
        self._application = None
        logger.info("Referência ao SAP GUI liberada.")

    # ------------------------------------------------------------------ #
    # Navegação
    # ------------------------------------------------------------------ #
    @property
    def application(self) -> Any:
        """Retorna o ``GuiApplication``, conectando se necessário."""
        return self.connect()

    def iter_sessions(self) -> list[Any]:
        """Retorna a lista de objetos ``GuiSession`` de todas as conexões."""
        app = self.connect()
        sessions: list[Any] = []
        connections = safe_get(app, "Children")
        n_conn = safe_get(connections, "Count", 0) or 0
        for ci in range(int(n_conn)):
            conn = safe_com_call(connections.ElementAt, ci)
            if conn is None:
                continue
            conn_children = safe_get(conn, "Children")
            n_sess = safe_get(conn_children, "Count", 0) or 0
            for si in range(int(n_sess)):
                sess = safe_com_call(conn_children.ElementAt, si)
                if sess is not None:
                    sessions.append(sess)
        return sessions

    def get_session(self, connection_index: int = 0, session_index: int = 0) -> Any:
        """Retorna um ``GuiSession`` específico por índices.

        Raises:
            SapConnectionError: Se a conexão ou sessão não existir.
        """
        app = self.connect()
        connections = safe_get(app, "Children")
        conn = safe_com_call(connections.ElementAt, connection_index)
        if conn is None:
            raise SapConnectionError(f"Conexão {connection_index} não encontrada.")
        sess = safe_com_call(conn.Children.ElementAt, session_index)
        if sess is None:
            raise SapConnectionError(
                f"Sessão {session_index} da conexão {connection_index} não encontrada."
            )
        return sess

    def active_session(self) -> Any | None:
        """Retorna a primeira sessão disponível, ou ``None`` se não houver."""
        sessions = self.iter_sessions()
        return sessions[0] if sessions else None

    def list_sessions_info(self) -> list[SessionInfo]:
        """Coleta metadados de todas as sessões para exibição na UI."""
        app = self.connect()
        result: list[SessionInfo] = []
        connections = safe_get(app, "Children")
        n_conn = safe_get(connections, "Count", 0) or 0
        for ci in range(int(n_conn)):
            conn = safe_com_call(connections.ElementAt, ci)
            if conn is None:
                continue
            conn_children = safe_get(conn, "Children")
            n_sess = safe_get(conn_children, "Count", 0) or 0
            for si in range(int(n_sess)):
                sess = safe_com_call(conn_children.ElementAt, si)
                if sess is None:
                    continue
                result.append(self._describe_session(ci, si, sess))
        return result

    @staticmethod
    def _describe_session(ci: int, si: int, sess: Any) -> SessionInfo:
        """Extrai um ``SessionInfo`` de um ``GuiSession`` via ``Info``."""
        info = safe_get(sess, "Info")
        return SessionInfo(
            connection_index=ci,
            session_index=si,
            system=str(safe_get(info, "SystemName", "") or ""),
            client=str(safe_get(info, "Client", "") or ""),
            user=str(safe_get(info, "User", "") or ""),
            transaction=str(safe_get(info, "Transaction", "") or ""),
            title=str(safe_get(sess, "ActiveWindow.Text", "") or ""),
        )

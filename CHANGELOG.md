# Changelog

Todas as mudanças relevantes deste projeto são documentadas aqui. O formato
segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/) e o projeto
adota [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Adicionado
- **CLI headless (`sap-scripting-tool-cli`).** Comandos `snapshot`, `inspect`,
  `highlight` e `select-node` expõem o `Analyser` sem abrir a interface Qt,
  para uso por agentes de IA/automação (ver skill
  `app-devs/_skills/sap-gui-snapshot`). `select-node` seleciona um nó de
  `GuiTree` pela chave (`SelectNode` + confirmação via `GetSelectedNodes`) —
  o equivalente real da API a "destacar" um nó, já que `GuiTree` não expõe
  `Visualize` por nó.

### Corrigido
- **Encoding do stdout da CLI.** `snapshot`/`inspect`/`highlight` forçam
  UTF-8 em stdout/stderr; sem isso, o codepage do console Windows corrompia
  texto acentuado ao capturar/redirecionar a saída.
- **`PollingRecorder.stop()` não avisava quando a thread não encerrava a
  tempo.** `test_start_stop_thread` iniciava uma thread real que, com um SAP
  GUI de verdade aberto na máquina, podia ultrapassar o timeout do `join()` e
  ficar órfã, causando `CO_E_NOTINITIALIZED` no encerramento do processo. O
  teste agora isola `_acquire_thread_session`; `stop()` registra um aviso se
  a thread não encerrar dentro do timeout.

## [1.3.0] - 2026-06-20

### Adicionado
- **Aba "Referência da API" expandida.** De 10 para **21 objetos** SAP GUI
  Scripting, incluindo `GuiComboBox`, `GuiCheckBox`, `GuiRadioButton`,
  `GuiOkCodeField`, `GuiTab/GuiTabStrip`, `GuiCalendar`, `GuiToolbarControl`,
  `GuiPasswordField`, `GuiMenu`, `GuiLabel` e `GuiSessionInfo`. Cada objeto
  passou a suportar **múltiplos exemplos rotulados** (`ApiEntry.examples`) —
  31 exemplos no total, com escape de HTML nos blocos de código.

## [1.2.0] - 2026-06-20

### Adicionado
- **Comentários de contexto no código gerado.** Três transições de tela viram
  comentários que ajudam o desenvolvedor a se localizar: entrar numa transação
  (`' NAVEGANDO para a transação: XXX`, a partir do okcd), trocar de aba
  (`' SELEÇÃO de aba: XXX`) e selecionar item de menu (`' SELEÇÃO de item de
  Menu: XXX`). O rótulo legível de aba/menu é capturado na gravação (novo campo
  `Acao.label`). Lógica neutra de linguagem (em `translate`).

### Alterado
- **IDs relativos a `wnd[N]` no código gerado.** O prefixo da sessão
  (`/app/con[N]/ses[M]/`) é removido na renderização — como faz o gravador
  nativo do SAP GUI —, deixando o script mais limpo (`session.FindById("wnd[0]/…")`).
  O `Acao.obj_id` interno permanece absoluto (usado por `FindById`/highlight e
  pela deduplicação).

### Corrigido
- **Popup de sistema do SAP capturado via AutoItX** (ex.: SAPMSSY0 "Exibir
  logs"). Esses popups aparecem no `ActiveWindow` mas **não** na contagem
  `Children.Count`, então a detecção por contagem falhava e o AutoItX os
  capturava. A decisão passou a casar o **título** do `#32770` com as janelas
  SAP atuais (`ActiveWindow` + filhas) — sinal confiável —, combinando o conjunto
  de títulos do polling, o flag de modal e uma leitura síncrona própria.

## [1.1.0] - 2026-06-20

### Adicionado
- **Conexão direta via `ISapSessionEvents`.** O Recorder passou a se conectar
  diretamente ao *connection point* `ISapSessionEvents` (com `Record = True`),
  capturando as interações com objetos normais e GuiShell pelo `CommandArray`
  oficial do SAP — a mesma base que o gravador nativo usa. O *polling* de
  GuiShell e de campos vira *fallback*, ativado apenas quando o motor COM não
  está disponível.

### Corrigido
- **Texto digitado vinha truncado no 1º caractere.** O valor-string do
  `CommandArray` (ex.: `"4900000618"`) era tratado como coleção COM e iterado
  caractere a caractere, sobrando só `"4"`. `_as_sequence` agora trata escalares
  (`str`/`bytes`/números/`bool`) como argumentos atômicos. O mesmo corrigiu
  `method_call` com um único argumento string.
- **Linhas duplicadas no script gerado.** O evento `Change` dispara duas vezes
  para a mesma alteração (uma via `CommandArray`, outra via leitura do
  componente). Nova passagem `dedupe_consecutive` colapsa ações adjacentes de
  efeito idêntico, normalizando `property_set` × `set_text`/`set_combo_key`/
  `set_checkbox`.
- **Métodos sem argumento eram descartados** (ex.: `doubleClickCurrentCell` no
  duplo-clique de célula de grid). A linha do `CommandArray` tem 2 elementos
  `("M", "nome")`; `_command_lines` exigia `len >= 3` — passou a aceitar `>= 2`.
- **Modais do próprio SAP GUI capturados via AutoItX.** Popups SAP (`wnd[1]`,
  `wnd[2]` …) surgem como `#32770` nativos mas existem na árvore COM. O
  Win32Recorder agora consulta um flag de modal mantido pelo *thread* de polling
  e adia a decisão por um ciclo, ignorando modais SAP (capturados via COM) e
  reservando o AutoItX a janelas do SO de fato externas ao SAP GUI.
- **GuiShell duplicado entre polling e COM.** Com o motor COM ativo, o
  *polling* de GuiShell é desligado: o `CommandArray` já grava essas interações
  de forma completa, inclusive ações transitórias (`doubleClickCurrentCell`,
  `pressButton`, `expandNode`) que o snapshot/diff não consegue observar.
- **`caretPosition` poluía o script.** A propriedade só indica a posição do
  cursor (sem efeito funcional) e passou a ser descartada na decodificação do
  `CommandArray`.
- **GuiGridView com colunas e linhas vazias.** A camada COM agora aceita
  coleções SAP baseadas em `Count`/`Length` e também `SAFEARRAY` convertidos
  pelo pywin32 em listas ou tuplas. Quando o SAP não expõe a coleção, a coluna
  atual é usada como fallback para evitar linhas vazias (`{}`).
- **Destaques acumulados no SAP GUI.** O destaque passou a acompanhar o botão
  direito do mouse diretamente sobre a árvore: pressionar destaca o objeto e
  soltar remove a moldura, sem botões intermediários ou resíduos visuais.
- **Barra de análise sem progresso real.** O percurso da hierarquia agora
  reporta objetos processados/total e mantém a interface responsiva durante a
  atualização da barra.
- **GuiShell não era reconhecido pelo SubType real do SAP.** Os controles
  reportam `Type == "GuiShell"` e o tipo em `SubType` **sem o prefixo `Gui`**
  (ex.: `"Tree"`, `"GridView"`) — a resolução só casava `"GuiTree"`, então caía
  no handler genérico (`introspeccao: false`). Adicionado `normalize_shell_type`
  (alias + prefixo `Gui`), usado por `get_handler` e pelo Analyser. *Verificado
  contra um SAP real: GuiTree de 25 nós passou a listar a hierarquia.*
- **Conteúdo de GuiShell agora é listado na árvore do Analyser.** Colunas e
  linhas de `GuiGridView`, hierarquia de `GuiTree`, linhas de `GuiTextEdit`,
  botões de `GuiToolbarControl` e dados de `GuiCalendar` aparecem como nós-filhos
  do controle (antes só surgiam no painel de detalhes). O conteúdo completo
  continua no painel; a árvore mostra uma amostra de até 50 itens por shell.
- **Leitura de coleções COM robustecida** (`com_len`/`com_item`): aceita tanto
  `Count` quanto `Length`, e `ElementAt`/`Item`, cobrindo as variações de
  `GuiComponentCollection` e `GuiCollection`.

### Adicionado (diagnóstico)
- **Log em arquivo por padrão**: `%LOCALAPPDATA%/SAPScriptingTool/logs/sap_tool.log`
  (nível DEBUG). Nível do console via `SAPTOOL_LOG_LEVEL` (ex.: `DEBUG`).
- Logging detalhado no Analyser: detecção de cada shell (Type/SubType/tipo
  resolvido/suportado), resumo da árvore e contagem de nós de conteúdo por shell.
- `get_handler` passa a resolver controles que reportam `Type == "GuiShell"`
  pelo `SubType` (ex.: `GuiGridView`), garantindo introspecção rica também no
  painel de detalhes e no *polling* do Recorder.

### Adicionado
- Busca incremental no **Analisador** por nome, texto, tipo ou ID, com navegação
  cíclica e expansão automática da hierarquia até o resultado.
- Sinalização explícita **CONECTADO** na sessão SAP usada pela aplicação, com
  seleção automática da primeira sessão encontrada.
- Seleção de linha mais visível na árvore e proporção inicial de 2/3 para
  **Objeto** e 1/3 para **Tipo**.
- Interface principal integralmente em português: **Analisador**, **Gravador** e
  **Referência da API**, além de títulos e mensagens associados.
- Abas **Referência da API** (referência pesquisável da API SAP GUI Scripting) e
  **Notas** (bloco de anotações com copiar/abrir/salvar) na janela principal.
- Atalhos de teclado globais: `F5` (atualizar árvore), `F9` (gravar),
  `Shift+F9` (parar gravação) e `Ctrl+C` (copiar ID, no Analyser).
- Reconexão automática COM por até 30 s (`SapConnection.ensure_connected`).
- Empacotamento standalone via PyInstaller: `sap_scripting_tool.spec` e
  `scripts/build.py` (gera `SAPScriptingTool.exe`, onefile, sem console).
- Integração contínua (GitHub Actions): `ruff`, `mypy`, `pytest` em uma matriz
  Python 3.10–3.12, mais build da documentação Sphinx.
- Documentação Sphinx (`docs/`) com autodoc, napoleon e `architecture.md`.

## [1.0.0]

### Adicionado
- **Analyser**: percurso da árvore de objetos da sessão SAP, inspeção,
  *highlight* (moldura vermelha) e exportação JSON/CSV.
- **Shell Handlers**: `GuiGridView`, `GuiTree`, `GuiTextEdit`, `GuiCalendar`,
  `GuiToolbarControl` e *fallback* genérico.
- **Recorder** com três motores: eventos COM, *polling* de `GuiShell` e
  diálogos Win32 nativos (AutoItX).
- **Codegen**: geradores VBA, Python, VBScript, PowerShell, AutoIt e Java a
  partir de uma `CodeGenerator` abstrata extensível.
- Interface PyQt6 com abas, editor QScintilla e tema escuro.
- Conexão COM ao SAP GUI Scripting Engine e seleção de sessão.
- Suíte de testes `pytest`/`pytest-qt` com *mocks* COM.

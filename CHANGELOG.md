# Changelog

Todas as mudanças relevantes deste projeto são documentadas aqui. O formato
segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/) e o projeto
adota [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Corrigido
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

# Changelog

Todas as mudanças relevantes deste projeto são documentadas aqui. O formato
segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/) e o projeto
adota [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Adicionado
- Abas **API Reference** (referência pesquisável da API SAP GUI Scripting) e
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

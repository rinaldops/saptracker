# SAP GUI Scripting Tool

[![Versão](https://img.shields.io/badge/vers%C3%A3o-1.3.0-2E75B6)](CHANGELOG.md)
[![Licença](https://img.shields.io/badge/licen%C3%A7a-MIT-375623)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-1F3864)](pyproject.toml)
[![CI](https://github.com/rinaldops/saptracker/actions/workflows/ci.yml/badge.svg)](.github/workflows/ci.yml)

Esta é uma solução para Windows de **análise e gravação de SAP GUI Scripting**, desenvolvida como uma alternativa de código aberto em relação ao descontinuado *Scripting Tracker* (Stefan Schnell, 2024). Percorre a árvore de objetos de uma sessão SAP, grava interações do usuário e gera scripts de automação prontos em **seis linguagens**.

![Captura de tela da interface da SAP GUI Scripting Tool](docs/_static/screenshot.png)

## O que faz de diferente do Scripting Tracker

O Scripting Tracker era cego para os controles modernos de SAP. Esta ferramenta
resolve exatamente as lacunas que ele nunca cobriu:

| Funcionalidade | Scripting Tracker | SAP GUI Scripting Tool |
| --- | :---: | :---: |
| Analisador de objetos SAP normais | ✅ | ✅ |
| Analisador de controles `GuiShell`/`GuiTree` | ❌ | ✅ Handler especializado |
| Gravador por eventos COM | ✅ | ✅ |
| Gravador de interações com `GuiShell` | ❌ | ✅ Polling por *snapshot* |
| Captura de diálogos Win32 nativos | ❌ | ✅ *Thread* `win32gui` + AutoItX |
| Código híbrido SAP + Win32 | ❌ | ✅ Intercalado automaticamente |
| Geração de código | ✅ VBA, Python, VBScript, PowerShell, AutoIt, Java | ✅ VBA, Python, VBScript, PowerShell, AutoIt, Java |
| Exportação da árvore | ✅ | ✅ JSON + CSV + área de transferência |
| Código aberto | ❌ | ✅ Licença MIT |

## Pré-requisitos

- **Windows** com **SAP GUI for Windows** instalado (suporte a 64-bit / versão 8.00+).
- **SAP GUI Scripting habilitado** no servidor e no cliente
  (`Opções → Acessibilidade & Scripting → Scripting`).
- **Python 3.10+** (para rodar a partir do código-fonte).
- **AutoItX3** registrado (`AutoItX3.dll`) — necessário apenas para gravar e
  executar a automação de diálogos Win32 nativos.

> A ferramenta opera exclusivamente com o SAP GUI for Windows. Não há suporte a
> SAP Web GUI, SAP Fiori ou plataformas não-Windows.

## Instalação

### Opção A — A partir do código-fonte

```bash
git clone https://github.com/rinaldops/saptracker.git
cd saptracker

python -m venv .venv
.venv\Scripts\activate

pip install -e .
sap-scripting-tool
```

Para desenvolvimento (lint, tipos, testes, docs e empacotamento):

```bash
pip install -e ".[dev,docs,build]"
```

### Opção B — Executável standalone

Gere um executável que roda sem instalação de Python:

```bash
python scripts/build.py
```

O binário é produzido em `dist/SAPScriptingTool.exe`. A arquitetura (x86/x64)
acompanha a do interpretador Python usado no build.

## Primeiros passos

1. **Abra o SAP GUI** e faça logon em uma sessão, com Scripting habilitado.
2. **Inicie a ferramenta** (`sap-scripting-tool` ou o `.exe`).
3. Na aba **Conexão**, clique em **Conectar / Atualizar sessões**. A primeira
   sessão é selecionada automaticamente e recebe o marcador **CONECTADO**;
   clique em outra sessão para trocar a conexão usada pela aplicação.
4. Na aba **Analisador**, clique em **Analisar sessão** (ou pressione **F5**).
   A barra de progresso acompanha os objetos processados. Use a busca para
   localizar por nome, texto, tipo ou ID e pressione **Próximo** para percorrer
   os resultados, expandindo automaticamente a hierarquia. Pressione o botão
   direito sobre uma linha para destacar o objeto no SAP; ao soltá-lo, a
   moldura desaparece. **Copiar ID** ou **Ctrl+C** envia o ID para a área de
   transferência.
5. Na aba **Gravador**, escolha a **linguagem** (VBA vem primeiro), clique em
   **Gravar** (**F9**), interaja com o SAP e clique em **Parar** (**Shift+F9**).
6. Clique em **Gerar código** — o script aparece na aba **Código**, pronto para
   **Copiar** ou **Salvar** com a extensão correta.

### Atalhos de teclado

| Atalho | Ação |
| --- | --- |
| `F5` | Atualizar a árvore de objetos |
| `F9` | Iniciar gravação |
| `Shift+F9` | Parar gravação |
| `Ctrl+C` | Copiar ID do objeto selecionado (aba Analisador) |

## Suporte a GuiShell

O grande diferencial da ferramenta. Cada tipo de `GuiShell` tem um handler
dedicado em [`src/core/shell_handlers/`](src/core/shell_handlers/) que faz a
introspecção do conteúdo interno e detecta mudanças para o Gravador:

| Tipo SAP | O que é inspecionado |
| --- | --- |
| `GuiGridView` (ALV Grid) | Colunas, linhas, valores de célula, célula atual, linhas selecionadas e primeira linha visível; aceita coleções COM e `SAFEARRAY` |
| `GuiTree` | Chaves de nós, texto por chave, hierarquia de filhos, colunas e *item text* |
| `GuiTextEdit` | Número de linhas, primeira linha visível, texto selecionado, conteúdo atual |
| `GuiCalendar` | Data de foco, intervalo de seleção, primeiro e último dia visível |
| `GuiToolbarControl` | Botões disponíveis, *tooltips* e estado de habilitação |
| *Demais tipos* | *Fallback* genérico: ID, tipo e *SubType* (sem introspecção de conteúdo) |

Como o SAP **não emite eventos COM para `GuiShell`** (*SAP Note 587202*), esses
controles são gravados por *polling* de *snapshots* em vez de *event listeners*.

## Geração de código

O Gravador converte as ações capturadas em scripts idiomáticos. Linguagens
suportadas (na ordem de exibição da UI):

| Linguagem | Identificador | Saída |
| --- | --- | --- |
| **VBA** (Excel/Access) | `vba` | `.bas` |
| Python (pywin32) | `python` | `.py` |
| VBScript | `vbscript` | `.vbs` |
| PowerShell | `powershell` | `.ps1` |
| AutoIt | `autoit` | `.au3` |
| Java (Jacob) | `java` | `.java` |

A mesma ação (*selecionar um nó em um `GuiTree`*) em três linguagens:

```vb
' VBA
session.FindById("wnd[0]/usr/cntlTREE1/shellcont/shell").SelectNode "000042"
```

```python
# Python
session.FindById("wnd[0]/usr/cntlTREE1/shellcont/shell").SelectNode("000042")
```

```powershell
# PowerShell
$session.FindById("wnd[0]/usr/cntlTREE1/shellcont/shell").SelectNode('000042')
```

Quando um **diálogo Win32 nativo** (ex.: *Salvar como*, `CLASS:#32770`) aparece
durante a gravação, um bloco AutoItX é **intercalado automaticamente** no script,
com o título e a classe da janela e *placeholders* para os valores dos campos.

## Contribuição

PRs são bem-vindos. O CI (GitHub Actions) precisa passar em `ruff` (lint),
`mypy` (tipos) e `pytest` (testes); toda nova funcionalidade deve trazer
*docstrings* e uma entrada no [CHANGELOG.md](CHANGELOG.md).

### Adicionar um novo handler GuiShell

1. Crie `src/core/shell_handlers/<tipo>.py`.
2. Implemente uma classe herdando de `GuiShellHandler` com os três métodos:
   `inspecionar()`, `tirar_snapshot()` e `gerar_codigo()`.
3. Registre-o no dicionário `HANDLERS` em
   [`src/core/shell_handlers/__init__.py`](src/core/shell_handlers/__init__.py).
4. Escreva testes unitários em `tests/` usando *mocks* COM.

### Adicionar uma nova linguagem de geração

1. Crie `src/codegen/<linguagem>.py` herdando de `CodeGenerator`.
2. Registre a classe na tupla `_GENERATORS` em
   [`src/codegen/__init__.py`](src/codegen/__init__.py) — ela passa a aparecer
   automaticamente na lista da aba Gravador.
3. Escreva testes cobrindo as ações principais (`set_text`, `press`,
   `select_node`, etc.).

Mais detalhes de arquitetura em [docs/architecture.md](docs/architecture.md).

## Licença

Distribuído sob a licença [MIT](LICENSE).

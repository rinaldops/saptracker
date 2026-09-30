# Arquitetura

> Referência estática conferida em 2026-09-30 (inclui a camada CLI headless,
> validada contra SAP GUI real). Versão/entrypoint e limites de execução
> estão no [README](../README.md). Testes com fakes validam contratos locais;
> compatibilidade com uma versão de SAP GUI exige teste no ambiente.

Este documento resume as decisões de design da SAP GUI Scripting Tool. A
especificação completa está em `doc/SAP_GUI_Scripting_Tool_Especificacao.docx`.

## Camadas

```
┌─────────────────────────────────────────────────────────┐
│                    Interface (PyQt6)                     │
│   Conexão · Analisador · Gravador · Código ·            │
│   Referência da API · Notas                              │
├─────────────────────────────────────────────────────────┤
│                         Core                             │
│   analyser  ·  recorder (com / polling / win32)         │
│   shell_handlers (registry + handlers por GuiShell)     │
├─────────────────────────────────────────────────────────┤
│                  Integração (COM/Win32)                  │
│   SAP GUI COM (pywin32) · win32gui · AutoItX            │
└─────────────────────────────────────────────────────────┘
```

## Decisões de design

### CLI headless (`src/cli.py`, `sap-scripting-tool-cli`)

Segunda interface sobre o mesmo `Core`, sem abrir `QApplication` — pensada
para agentes de IA/automação lerem a tela do SAP GUI como JSON estruturado em
vez de captura de tela. Decisões:

- **Zero duplicação de lógica.** Cada comando (`snapshot`, `inspect`,
  `highlight`, `select-node`, `select-row`, `copy-table`) é um `argparse`
  fino sobre métodos que já existiam (ou foram adicionados) em `Analyser` —
  a UI e a CLI compartilham exatamente o mesmo código de introspecção COM.
- **UTF-8 forçado em stdout/stderr** (`_ensure_utf8_stdio`). O codepage do
  console do Windows (cp1252) não é UTF-8 por padrão; sem isso, texto
  acentuado (nomes/textos de tela SAP) sai corrompido de forma irrecuperável
  ao capturar/redirecionar a saída — só apareceu num teste real com o SAP GUI
  aberto, não nos testes com fakes (que não passam pelo console de verdade).
- **`highlight` cobre campos simples; `select-node`/`select-row` cobrem
  `GuiTree`/`GuiGridView`.** Nenhum dos dois controles expõe `Visualize` por
  nó/linha — só o controle inteiro tem posição própria. `select-node`
  (`SelectNode`) e `select-row` (`SetCurrentCell` + `SelectedRows`) são o
  equivalente real da API para apontar um nó/linha específico.
- **`copy-table` e `full_grid_data` são ações explícitas, nunca automáticas
  no caminho de *polling*.** Ver "Colunas incompletas em GuiGridView" abaixo.

### Motores de gravação (COM primário, polling como *fallback*)

O Recorder usa três motores independentes que empurram `Acao` para um buffer
único e cronológico:

- **`recorder_com`** — conecta-se diretamente ao *connection point*
  `ISapSessionEvents` com `Record = True` e traduz o `CommandArray` oficial do
  SAP (o mesmo do gravador nativo). Captura tanto objetos normais quanto as
  interações com `GuiShell` — inclusive ações transitórias (`doubleClickCurrentCell`,
  `pressButton`, `expandNode`) que o snapshot/diff **não** observa.
- **`recorder_polling`** — *fallback* por *snapshots*/`diffs` (intervalo padrão
  200 ms, alvo &lt; 3% de CPU). Quando o motor COM está ativo, a captura de
  campos e de `GuiShell` é desligada (o `CommandArray` já as grava, e duplicaria);
  o *thread* permanece vivo apenas para detectar troca de tela e manter o flag
  de janela modal SAP. Historicamente o *polling* era a única via para
  `GuiShell` (*SAP Note 587202* — sem eventos COM no modelo antigo).
- **`recorder_win32`** — *thread* `win32gui` que detecta diálogos `#32770`
  nativos e injeta blocos AutoItX. Para **não** capturar janelas do próprio SAP
  GUI (que surgem como `#32770` mas são dirigidas via COM), casa o **título** do
  diálogo com as janelas SAP atuais (`ActiveWindow` + filhas) — sinal confiável
  que cobre tanto modais `wnd[1+]` quanto popups de sistema (SAPMSSY0, ex.:
  "Exibir logs") cujo `Children.Count` não os conta. Combina o conjunto de
  títulos do *polling*, o flag de modal e uma leitura síncrona própria, com
  adiamento de um ciclo. O AutoItX fica reservado a janelas do SO externas ao SAP.

### Thread safety

Toda atualização de *widget* PyQt6 ocorre na *thread* principal via
`signals/slots`; *threads* de background nunca tocam *widgets* diretamente.
Cada *thread* que usa COM chama `pythoncom.CoInitialize()`/`CoUninitialize()`.

### Tolerância a falhas COM

Chamadas ao SAP GUI são encapsuladas em utilitários seguros
(`src/core/com_utils.py`) que registram falhas em DEBUG e retornam um valor
padrão. A conexão tenta **reconexão automática por 30 s**
(`SapConnection.ensure_connected`) antes de exibir erro.

As coleções retornadas pelo SAP não têm uma representação única no
pywin32. Os helpers `com_len` e `com_item` aceitam `Count`, `Length`,
`ElementAt`, `Item`, indexadores Python e `SAFEARRAY` convertidos em listas ou
tuplas. Essa normalização é usada pelos handlers de `GuiGridView` e `GuiTree`.

### Análise e destaque

O `Analyser` faz uma contagem leve da hierarquia COM antes do percurso completo
para alimentar a barra de progresso com objetos processados/total. O destaque
usa `Visualize(True)` enquanto o botão direito permanece pressionado sobre uma
linha da árvore e `Visualize(False)` quando o botão é solto.

### Codegen extensível

`CodeGenerator` é uma classe abstrata; cada linguagem é uma subclasse
registrada em `src/codegen/__init__.py`. Adicionar uma linguagem não exige
alterar código existente — basta criar o gerador e registrá-lo. O gerador
**VBA** é prioritário (público-alvo principal) e aparece primeiro na UI.

## Limitações conhecidas e lições aprendidas

Descobertas ao validar a CLI headless contra um SAP GUI real (Project
Builder/cProjects, 2026-09-30) — nenhuma tinha aparecido nos testes com fakes,
o que reforça a importância de testar contra SAP real antes de fechar uma
funcionalidade de introspecção.

### Colunas incompletas em `GuiGridView`

Alguns grids ALV (ex.: o "worklist" do Project Builder, hospedado num
`GuiContainerShell`) **não implementam** `GetColumnOrder()`/`GetColumnNames()`
via Scripting — confirmado com `AttributeError` numa chamada COM direta,
embora `ColumnCount` reporte corretamente o total de colunas. O handler
(`GuiGridViewHandler._column_names`) cai então no fallback de 1 coluna
(`CurrentCellColumn`), e sem sinalizar isso, a maior parte da tabela some do
snapshot/busca em silêncio — parecendo um grid de fato incompleto, e não uma
limitação da API.

**Correção em duas camadas**: (1) `colunas_completas`/`total_colunas` no
retorno do handler tornam a lacuna visível (nó `GuiGridColumnsAviso` na
árvore) em vez de escondida; (2) quando os nomes técnicos não são
enumeráveis, os **dados continuam recuperáveis** via a mesma ação de
"Selecionar tudo → Copiar" que o próprio SAP GUI oferece no menu de contexto
do grid (`SelectAll` + `ContextMenu` + `SelectContextMenuItemByPosition` +
leitura do clipboard) — contorna a ausência de nomes por completo, sem
adivinhar nada.

Essa técnica de clipboard **não foi inventada do zero**: foi confirmada por
uma automação VBA anterior do usuário (`tests/modPrincipal.bas`, `Sub
ExtraiEquipamentos`), que já resolvia exatamente esse tipo de limitação da API
selecionando coluna(s)/tudo e copiando via menu de contexto. **Lição**: antes
de concluir que uma limitação de API não tem contorno, vale procurar
automações/scripts já existentes que tenham lidado com o mesmo problema — a
solução prática já pode existir, só não documentada como tal.

### Paginação de ALV Grids

O SAP GUI só busca do servidor 1-2 "páginas" de linhas por vez; ler ou copiar
sem antes forçar o carregamento de todas (rolando `FirstVisibleRow` por toda
a extensão do grid — também confirmado pela mesma automação VBA de
referência) deixa linhas além da primeira página vazias em grids grandes.
Um teste com um grid pequeno (25 linhas) **não expôs esse problema** — só
apareceu ao raciocinar sobre grids de milhares de linhas. **Lição**: um teste
que passa contra um dataset pequeno não prova que a lógica está correta para
o caso geral quando a correção depende do tamanho dos dados (paginação,
*streaming*, limites de página) — vale considerar explicitamente o
comportamento no limite (poucas linhas vs. muitas) antes de declarar uma
funcionalidade validada.

### Efeitos colaterais nunca automáticos no caminho de *polling*

`ensure_grid_rows_loaded` (paginação) e a recuperação via clipboard
(`full_grid_data`) rolam a tela e usam a área de transferência do Windows —
efeitos colaterais aceitáveis numa ação deliberada (`copy-table`, "Analisar
sessão", `snapshot --full-grids`), mas **inaceitáveis** no
`GuiGridViewHandler.inspecionar()` compartilhado, chamado a cada ciclo
(~250ms) pelo `PollingRecorder` durante gravação ao vivo — rolaria a tela sob
o usuário e degradaria a gravação em tempo real. Por isso `full_grid_data`
é um parâmetro opt-in (`False` por padrão) propagado explicitamente por
`build_tree`/`_append_children`/`_append_shell_content`, nunca ligado
implicitamente no handler em si.

### Busca/árvore precisam de dados semanticamente completos, não só visíveis

Dois bugs distintos, mesmo padrão: o rótulo de um `GuiTreeNode` só incluía o
`texto` visível, descartando os valores de `colunas` (onde o código real de
um objeto de projeto SAP PS — rede/atividade/elemento de tarefa — costuma
estar, ex.: `TECH_KEY`); e o de um `GuiGridRow` dependia inteiramente de
`GetColumnOrder`/`GetColumnNames` funcionarem. Em ambos os casos, a busca da
UI e o `snapshot` da CLI indexam apenas `id`/`type`/`name`/`text` — qualquer
dado relevante que não chegue a um desses campos é, na prática, invisível e
"não encontrado". **Lição para novos handlers/campos**: se uma introspecção
tem um caminho *best-effort*/parcial, garanta que o resultado (completo ou
parcial) chegue ao `text` do nó — não só a um campo estruturado separado que
só aparece via `inspect`.

### Testes não podem depender de o SAP GUI estar (ou não) aberto na máquina

`test_start_stop_thread` iniciava uma thread real do `PollingRecorder` com
`session=object()` — inofensivo sem SAP GUI aberto (a thread falha rápido ao
tentar `GetObject("SAPGUI")` e não faz mais nada), mas com um SAP GUI real
aberto na máquina (cenário validado nesta revisão), a thread passa a varrer
uma sessão de verdade e pode ultrapassar o timeout do `join()` em `stop()`,
ficando órfã e gerando `CO_E_NOTINITIALIZED` no encerramento do processo —
ruído intermitente na suíte que só aparecia dependendo do estado do ambiente
de quem rodava os testes. Corrigido isolando `_acquire_thread_session` no
teste (hermético independente do ambiente) e fazendo `stop()` registrar um
aviso em vez de descartar em silêncio uma thread que não encerrou a tempo.
**Lição**: um teste que só é determinístico "se o SAP GUI não estiver aberto"
não é determinístico — vale isolar explicitamente qualquer chamada que possa
ter sucesso contra um recurso externo real, mesmo quando o *happy path* do
teste não pressupõe esse recurso.

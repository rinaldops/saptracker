# Arquitetura

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

Nós sintéticos de `GuiShell` podem carregar texto adicional em `search_text`.
Esse campo entra no índice da busca do Analisador, mas não altera o rótulo
exibido na árvore. Em `GuiTree`, isso permite localizar valores de colunas como
`TECH_KEY` da CJ20N. Ao navegar por um resultado, o painel de detalhes em JSON
também seleciona e rola até a ocorrência encontrada, quando ela está presente.

### Codegen extensível

`CodeGenerator` é uma classe abstrata; cada linguagem é uma subclasse
registrada em `src/codegen/__init__.py`. Adicionar uma linguagem não exige
alterar código existente — basta criar o gerador e registrá-lo. O gerador
**VBA** é prioritário (público-alvo principal) e aparece primeiro na UI.

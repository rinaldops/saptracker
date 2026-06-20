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

### Polling para GuiShell

O SAP **não emite eventos COM** para controles `GuiShell`/`GuiGridView`
(documentado na *SAP Note 587202*). Por isso o Recorder usa três motores
independentes:

- **`recorder_com`** — escuta `GuiSession.Change` para objetos normais.
- **`recorder_polling`** — tira *snapshots* periódicos e calcula *diffs* dos
  `GuiShell` (intervalo configurável; padrão 200 ms, alvo &lt; 3% de CPU).
- **`recorder_win32`** — *thread* `win32gui` que detecta diálogos Win32 nativos
  e injeta blocos AutoItX no script.

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

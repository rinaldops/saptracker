# Exportação de `GuiTextEdit` no SAP GUI com menu nativo e AutoItX3

## Contexto

Durante a análise da transação `CJ20N`, na aba `LTCT`, o conteúdo de texto é apresentado por um editor nativo do SAP GUI. O controle aparece na API SAP GUI Scripting como `GuiShell` com `SubType = TextEdit`, mas a janela nativa tem a classe `SAP TextEdit`.

ID validado no cenário de teste:

```text
wnd[0]/usr/subDETAIL_AREA:SAPLCNPB_M:1010/subVIEW_AREA:SAPLCJWB:3998/tabsPTABSCR/tabpLTCT/ssubSUBSCR2:SAPLCJWB:0660/cntlTEXTEDITOR1/shell
```

O teste foi realizado na conexão `02 PEP - SAP S/4HANA Produção (SAP SCRIPT)` e no projeto `IN-3668-20-001`. A sessão foi usada somente para consulta e exportação local; não houve gravação de dados no SAP.

## Descobertas e sequência validada

- `SetSelectionIndexes` só posiciona o cursor; não exporta.
- O menu não aparece como botão SAP nem foi confiável via `ShowContextMenu()`.
- O clique direito deve ocorrer na janela nativa classe `SAP TextEdit`.
- O menu é uma janela Win32, normalmente classe `#32768`.
- A última opção deve ser selecionada com `End`; em seguida, após 0,3–0,5 s, enviar `Enter` em chamada separada. A combinação em uma única chamada falhou em teste.
- Isso abre `Salvar como`, que deve ser tratado como diálogo Win32.

Fluxo:

```text
SAP TextEdit -> clique direito -> menu #32768 -> End -> espera -> Enter
-> Salvar como -> preencher Edit1 -> Salvar -> validar arquivo
```

Usar `End` em vez de `Down` fixo, pois o menu varia por release, idioma e permissões.

## Teste sem registro administrativo

O AutoItX3 não estava registrado como COM e o computador não permitia instalação administrativa. A DLL x64 local funcionou diretamente via `ctypes`:

```text
C:\Users\EAQU\Utils\AutoItX3\AutoItX\AutoItX3_x64.dll
```

Python x64 carregou a DLL e o teste criou um arquivo local de 2282 bytes contendo o texto exportado. Exemplo reduzido:

```python
from ctypes import WinDLL, c_int, c_wchar_p
from pathlib import Path
import time

dll = WinDLL(r"C:\Users\EAQU\Utils\AutoItX3\AutoItX\AutoItX3_x64.dll")
dll.AU3_Init()
dll.AU3_Send.argtypes = [c_wchar_p, c_int]
dll.AU3_ControlSetText.argtypes = [c_wchar_p, c_wchar_p, c_wchar_p, c_wchar_p]
dll.AU3_ControlClick.argtypes = [c_wchar_p, c_wchar_p, c_wchar_p]

dll.AU3_Send("{END}", 0)
time.sleep(0.5)
dll.AU3_Send("{ENTER}", 0)
out = Path(r"C:\temp\NomeDoArquivo.txt")
dll.AU3_ControlSetText("Salvar como", "", "Edit1", str(out))
dll.AU3_ControlClick("Salvar como", "", "Button2")
for _ in range(100):
    if out.exists() and out.stat().st_size > 0:
        break
    time.sleep(0.1)
else:
    raise TimeoutError(out)
```

Em produção, o caminho deve ser configurável; não gravar credenciais, tokens ou caminhos pessoais em código versionado. A arquitetura da DLL deve coincidir com o processo hospedeiro.

## Por que o texto digitado não aparece no script

A edição do `Edit1` ocorre fora da árvore SAP, portanto o gravador SAP não captura o texto literal digitado. A reprodução deve definir explicitamente o caminho:

```vb
Set autoit = CreateObject("AutoItX3.Control")
autoit.WinWait "Salvar como", "", 10
autoit.ControlSetText "Salvar como", "", "Edit1", "C:\temp\NomeDoArquivo.txt"
autoit.ControlClick "Salvar como", "", "Button2"
```

`Button2` é o ClassNN observado no diálogo testado; localizar o botão por texto (`Salvar`/`Save`) é mais resiliente.

## Falhas e recomendações

Não funcionaram: usar apenas `SetSelectionIndexes`; procurar o menu como objeto SAP; depender de `ShowContextMenu()`; contar `Down` fixo; enviar `End` e `Enter` juntos; assumir que o arquivo existe imediatamente após o clique; exigir registro COM.

O SAPTRACKER deve manter a captura COM SAP separada do polling Win32, registrar cada etapa (editor, menu, `End`, `Enter`, diálogo, preenchimento, salvamento, validação), capturar o diálogo de forma diferida e verificar existência/tamanho do arquivo após o salvamento.

A orientação específica para a futura melhoria do GAPS está em [`../../GAPS/docs/exportacao-textos-cj20n.md`](../../GAPS/docs/exportacao-textos-cj20n.md).

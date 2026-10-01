## Diagnóstico da latência ao selecionar uma coluna

A seleção da coluna foi validada na conexão `02 PEP - SAP S/4HANA Produção (SAP SCRIPT)`. A sequência COM abaixo respondeu em dezenas de milissegundos:

```python
table = session.FindById(table_id)
table.Columns.ElementAt(column_index).Selected = True
table.Visualize(True)
```

A demora vinha do painel de detalhes: `GuiTableColumn` é um nó sintético cujo ID é o da tabela-pai. Ao selecionar o item, o painel chamava `inspect(table_id)` novamente. Essa inspeção relia os filhos da tabela e levava aproximadamente 10 segundos antes da seleção.

A correção não reinspeciona a tabela para nós sintéticos `GuiTableColumn`; usa o nome e o texto já mapeados. A seleção COM e `Visualize(True)` continuam ocorrendo, preservando a piscada esperada.

Lição: separar detalhes de controles reais, detalhes de nós sintéticos e ações de seleção; uma ação não deve ser precedida por nova captura completa.

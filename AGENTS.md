# Instruções para agentes

- No ambiente corporativo Petrobras, operações de publicação GitHub devem usar SSH.
- Não tente `git push` via HTTPS para este repositório; a operação pode falhar com HTTP 403.
- Para publicar branches, use o endpoint SSH, por exemplo:
  `git push -u git@github.com:rinaldops/saptracker.git <branch>`.

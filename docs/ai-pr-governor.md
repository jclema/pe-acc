# AI PR Governor (Claude Code)

Fluxo conservador para review, aprovação e auto-merge de PRs internas no `main`.

## Objetivo

- Avaliar PRs com Claude Code (`claude-opus-4-6`) usando saída estruturada.
- Aplicar política determinística (`scripts/claude_merge_gate.py`) antes de qualquer merge.
- Aprovar formalmente e fazer squash merge só quando todos os gates passarem.

## Arquivos principais

- Workflow: `.github/workflows/claude-pr-governor.yml`
- Política: `.github/claude-automerge-policy.json`
- Scanner de injeção: `scripts/prompt_injection_scan.py`
- Gate determinístico: `scripts/claude_merge_gate.py`

## Pré-requisitos

### Secrets

1. `CLAUDE_CODE_OAUTH_TOKEN`
   - Gere localmente via `claude setup-token` com sua conta Max.

### Variables

1. `CLAUDE_AUTOMERGE_ENABLED`
   - `false` para shadow mode
   - `true` para ativar merge automático
2. `CLAUDE_AUTOFIX_ENABLED`
   - recomendado: `true`

### GitHub Actions setting obrigatório

No repositório, habilite:

- **Actions can approve pull request reviews** = `true`

Sem isso, o passo `gh pr review --approve` pode falhar.

## Comportamento do fluxo

1. **Preflight**
   - bloqueia forks
   - roda scanner de prompt injection
   - aplica allowlist/denylist e thresholds de churn
2. **Claude evaluation**
   - exige schema com campos: `useful`, `necessary`, `safe`, `confidence`, `risk_level`, `blocking_findings`, `summary`
3. **Required checks gate**
   - espera checks obrigatórios até timeout (45 min por padrão)
   - se falhar, tenta auto-fix 1x apenas para checks técnicos elegíveis
4. **Approve + merge**
   - só com kill switch ativo (`CLAUDE_AUTOMERGE_ENABLED=true`)
   - aprovação formal + squash merge

## Preparação de cada PR

Antes de entregar uma PR para revisão, execute scanner e preflight local com
título, descrição, comentários e diff atuais. A coleta de contexto está no passo
`Run preflight policy` do workflow. Use a base real da PR para contar arquivos e
adições + remoções; numa pilha, não conte novamente as alterações da dependência.
Registre o SHA, a base, as métricas e todas as razões de bloqueio na descrição.

Um job verde significa que o comando executou; consulte `eligible` e `reasons`
no JSON. CI verde e preflight elegível não substituem a avaliação de Claude nem
autorizam merge. Drafts, forks, caminhos sensíveis e limites continuam bloqueados.

A allowlist inclui sete arquivos explícitos de procedência em ETL/API; isso não
libera diretórios inteiros. Outros arquivos de backend continuam fora do escopo
automático. Alterar política ou scanner exige revisão humana, pois esses caminhos
permanecem fora da allowlist e na denylist quando aplicável.

O scanner mantém as regras e pontuações existentes. Apenas o identificador Python
`encoded`, numa linha sintaticamente válida de um hunk `.py`, não conta como
linguagem de ofuscação. Strings, comentários, prosa, contexto desconhecido e outras
regras seguem sendo analisados. Não há exceção por número de PR ou autor.
Regressões de política e scanner rodam no job `Repository Contracts`:
```bash
python3 -m unittest discover -s scripts/tests
```

O workflow atual só atende PRs com base em `main`. Em pilhas, avalie e integre
as dependências por ordem; depois atualize a base, recalcule o diff e valide
novamente. Não troque antecipadamente a base de todas para `main`: isso pode
incluir alterações das dependências e exceder os limites. Mantenha o kill switch
desativado durante a revisão destas mudanças de manutenção.

## Kill switch e rollback

### Kill switch imediato

Defina:

- `CLAUDE_AUTOMERGE_ENABLED=false`

O workflow continua auditando/comentando, mas não faz merge.

### Rollback total

1. Desabilitar workflow `Claude PR Governor` no GitHub Actions.
2. Reverter o arquivo `.github/workflows/claude-pr-governor.yml`.

## Troubleshooting

### Não aprovou PR

- Verifique se `can_approve_pull_request_reviews` está habilitado no repo.
- Verifique permissões do `GITHUB_TOKEN` no workflow.

### Não fez merge

- Confirme `CLAUDE_AUTOMERGE_ENABLED=true`.
- Revise comentário final no PR e `decision` calculada.
- Verifique se houve novo commit concorrente.

## Rollout recomendado

1. **Fase Shadow (3-5 dias)**
   - `CLAUDE_AUTOMERGE_ENABLED=false`
2. **Ativação controlada**
   - ligar kill switch (`true`) mantendo política conservadora
3. **Ajuste fino**
   - calibrar allowlist/denylist e thresholds conforme dados reais

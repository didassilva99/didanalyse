# DidAnalyze — atualização de 10/08/2026

## O que mudou

- Removida toda a área pública **Desafios** e o respetivo painel de administração.
- A navegação passa a ter **Prognósticos** e **Jogadores**.
- Adicionada **Scottish Premiership (Escócia)**. A **Pro League (Bélgica)** mantém-se e passa a ser sincronizada pelo mesmo processo das restantes ligas.
- Adicionado `season_sync.py`, que obtém calendário 2026/27, resultados concluídos, estatísticas coletivas e estatísticas individuais quando a fonte tem cobertura.
- Adicionadas tabelas `players` e `player_match_stats` e o identificador `sofascore_event_id` nos jogos.
- A página **Jogadores** calcula automaticamente médias de nota, minutos, golos, assistências, xG/xA, precisão de passe e métricas por 90 minutos.
- Na primeira sincronização da Escócia, se não existir histórico suficiente, o script importa automaticamente 2025/26 para alimentar o modelo.
- Incluído workflow GitHub Actions para sincronização diária automática.

## Primeira atualização manual

Na pasta do projeto, com o ambiente Python ativo:

```bat
python -m pip install -r requirements.txt
python season_sync.py --refresh
```

Para testar só uma competição:

```bat
python season_sync.py --league "Scottish Premiership" --refresh
python season_sync.py --league "Pro League" --refresh
```

## Se a base pública está no Turso

O site público pode continuar com um token **read-only**. Para executar a sincronização é necessário usar temporariamente um token de **escrita** no computador onde corre `season_sync.py`, ou guardar esse token no GitHub como secret `TURSO_WRITE_TOKEN`.

O script usa automaticamente `TURSO_DATABASE_URL` e `TURSO_AUTH_TOKEN` quando existem. No GitHub Actions, o workflow usa:

- `TURSO_DATABASE_URL`
- `TURSO_WRITE_TOKEN`

Não coloques o token diretamente no código.

## Atualização automática diária

O ficheiro `.github/workflows/atualizar_dados.yml` corre todos os dias e também pode ser executado manualmente em **GitHub → Actions → Atualizar dados DidAnalyze → Run workflow**.

## Ficheiros a substituir no repositório atual

- `app.py`
- `database.py`
- `historical_import.py`
- `season_sync.py` (novo)
- `.github/workflows/atualizar_dados.yml` (novo)

Mantém os restantes ficheiros do projeto, especialmente a tua base atual. **Não substituas `data/apostas.db` por uma cópia antiga.**

O ficheiro `desafios.json`, se ainda estiver no GitHub, pode ser apagado: o novo `app.py` já não o usa.

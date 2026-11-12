# Arquitetura

## Estrutura implementada

- `src/localclip/app.py`: FastAPI, API de projetos, jobs, edição, mídia e provedores; frontend estático servido após build.
- `schemas.py`: validação Pydantic de opções, intervalos, palavras, edições e provedores.
- `storage.py`: SQLite com transações, diretórios XDG, jobs e documentos JSON.
- `jobs.py`: worker em processo separado, um job pesado por vez, cache de análise e orquestração.
- `media.py` / `visual.py`: processamento local e render (ver VIDEO_PIPELINE.md).
- `ranking.py`: candidatos e score (ver VIRALITY_RANKING.md).
- `providers.py`: adapters, cache semântico e Secret Service.
- `web/`: frontend React/TypeScript.

A aplicação inicia em `127.0.0.1:8765`. Não há Redis, microsserviços, cloud obrigatória ou CUDA presumida. O servidor atende UI enquanto worker usa CPU. Jobs são retirados em transação `BEGIN IMMEDIATE`. O aplicativo destina-se a uma única instância por diretório de dados.

O bootstrap informa arquitetura da CPU, threads lógicas, memória física e GPU observada por `lspci` (detecção cacheada por processo). Identificação não implica aceleração funcional: o encoder precisa passar pelo seu smoke real.

## Fluxo

Importação → probe → job de processamento → fingerprint SHA-256 → extração/transcrição/análise local → timeline persistida → candidatos/ranking → edição → job de render → download. URLs usam job de ingestão. Arquivos enviados pelo navegador são copiados para armazenamento privado; o original do usuário nunca é alterado.

Cache de análise identificado por conteúdo, intervalo, autorização de imagens e versão do pipeline. Ranking é recalculado com as opções atuais; chamadas semânticas têm cache próprio. Timeline usa referência temporal absoluta do vídeo original. Render considera revisão de edição e remapeia os trechos removidos.

Versão do cache de análise: 2, invalidando timelines anteriores que podiam conter timestamps interpolados. Em falha/cancelamento antes da conclusão do ranking, opções, candidatos e timeline publicados anteriormente são preservados. A nova análise só substitui esses artefatos após gerar resultados.

## Concorrência e falhas

API não executa análise pesada no event loop. Worker separado faz chamadas síncronas e FFmpeg. Cancelamento é persistido; operações locais cooperam com flag. Chamadas HTTP externas dependem de timeout e podem atrasar o cancelamento. Na inicialização, jobs anteriormente em execução passam a interrompidos. Não são marcados como sucesso nem retomados silenciosamente.

Edição e exclusão não são permitidas enquanto houver job ativo no projeto. Novo processamento substitui candidatos anteriores apenas após produzir novos resultados. Renders usam nome com revisão; alteração invalida o link exportável. Artefatos antigos podem permanecer em disco e precisam de política de limpeza futura explicitamente documentada.

## Evolução: identidade e retomada

`projects.display_name` é o título editável único; `name` legado permanece preservado para compatibilidade, enquanto `original_filename` e `source_title` registram proveniência. `jobs.checkpoint` (JSON), `attempts` e `failed_provider` são adicionados por migração aditiva em `storage.initialize()`. O worker grava a timeline analisada no cache identificado por conteúdo e somente publica a timeline e os candidatos do projeto após ranking bem-sucedido. `POST /api/jobs/{jid}/retry` retoma o mesmo job falho/interrompido: a etapa de análise concluída é reutilizada e a configuração atual de provedores é consultada novamente. Uma interrupção em execução não é retomada silenciosamente após reinício.

Thumbnails persistem em `projects/<id>/thumbnail.jpg`; a API gera imagem sob demanda para projetos antigos quando há mídia acessível. Rotas de leitura usam identificadores internos; o título exibido nunca altera o arquivo original.

## Dependências e validação

Python 3.12 isolado por uv; versões exatas em uv.lock. FFmpeg/ffprobe são dependências do sistema. Node é necessário para compilar web/dist, não para servir a aplicação compilada. Consulte TESTING.md e CURRENT_STATUS.md para evidências, sem inferir validação a partir deste desenho.

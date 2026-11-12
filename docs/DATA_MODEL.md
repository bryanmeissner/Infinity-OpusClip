# Modelo de dados

Banco: `${XDG_DATA_HOME:-~/.local/share}/localclip/localclip.sqlite3`, SQLite WAL, foreign keys ativas. `LOCALCLIP_DATA_DIR` permite diretório isolado. `storage.initialize()` aplica migrações aditivas por introspecção (`PRAGMA table_info`), preservando linhas existentes.

| Tabela | Conteúdo |
|---|---|
| projects | id UUID hexadecimal, nome, source privado, created_at, metadata JSON, options JSON, status, error |
| jobs | id, project_id FK, kind, candidate_id, state, stage, progress 0–1, payload JSON, error, cancel, timestamps |
| candidates | id, project_id FK, posição ordenada, data JSON completo |
| providers | id e configuração JSON sem API key |
| settings | chave e JSON; provider_order aponta principal/fallback |
| usage | id, project_id FK, created_at e uso JSON sanitizado |

Jobs: queued → running → completed/failed/cancelled; reinício converte running em interrupted. Cancelamento queued termina sem executar. Há no máximo um job queued/running por projeto; globalmente um worker serial.

Timeline em projects/<id>/timeline.json: start/end, segments, words, scenes, silence, audio_events, visual_events, tracks, keywords, semantic_tags. Segundos absolutos no original, não relativos à seleção. Campos de evidência podem estar vazios; não significam que todos os eventos foram detectados.

Candidato contém start/end, title, summary, score, scores, reason, mode, words, edit, revision e render_path privado quando renderizado. API expõe rendered boolean, não caminhos internos. Edit guarda proporção, reframe, crop_x, legendas/estilo/tamanho/posição, palavras e remove_ranges. Palavras editadas devem estar dentro do intervalo; remoções devem ser internas, não sobrepostas e não apagar o clipe inteiro. Edições incrementam revisão e invalidam render.

O candidato também persiste `weights`, `request_boost` e `resolved_clip_model`. Scores usam chaves canônicas sem aliases `_score`. Limites em `edit` são a revisão exibida/renderizada; o score e os limites raiz registram a análise original, não uma reavaliação semântica de edições manuais.

IDs são opacos, não paths. Dados grandes ficam em arquivos, não BLOBs no SQLite. JSON é gravado sem NaN/Infinity e arquivos derivados são substituídos atomicamente. Credenciais ficam somente no Secret Service, fora destas entidades.

## Campos adicionados

`projects.display_name` é o nome editável exibido em todo o sistema; a migração o inicializa com `name` dos projetos existentes. `projects.original_filename` preserva o nome do upload, `projects.source_title` o título de metadados. Renomear altera somente `display_name`; não altera o arquivo, nem o título de cada candidato. Para URL, o valor inicial vem do yt-dlp (ou metadata do vídeo); para upload, do nome sem extensão.

`jobs.checkpoint` persiste etapa, caminho de timeline cacheada, hash de análise, etapas concluídas, erro e provider falho; `attempts` registra retomadas e `failed_provider` permite exibição na UI. Retry transacional reencaminha o **mesmo ID** de job `failed`/`interrupted` de processamento, mantendo payload/checkpoint. `projects/<id>/thumbnail.jpg` é artefato persistente (não BLOB); falta de imagem não altera o schema. `settings.omp_google_cloud_project` contém somente ID de projeto não secreto; tokens e API keys continuam fora do SQLite.

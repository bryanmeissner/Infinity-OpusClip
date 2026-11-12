# Handoff

LocalClip: editor local-first Fedora, FastAPI/SQLite/worker + React. Arquitetura existente preservada; não criar outro scaffold. Plano principal: `PLANO_PROJETO_EDITOR_IA_VIDEO.md`.

## Retomada
Implementação integrada concluída; a suíte de testes e o build passam. TESTING.md registra evidências novas: arquivo/URL, Whisper CPU, timeline, cache, Top 3, três proporções H.264/AAC, edição textual, remoção interna, render/exportação e reprodução Chromium. Correção posterior preserva timestamps VFR ao remover intervalos; regressão real com FFmpeg. Não confundir isso com qualidade geral.

## Executar
```sh
uv sync --extra dev
npm --prefix web ci
npm --prefix web run build
uv run localclip --port 8765
uv run --extra dev pytest -q
```

## Dados
Padrão: `~/.local/share/localclip`, cache `~/.cache/localclip`, respeitando XDG. Validação isolada: `/tmp/localclip-resume-data`, `/tmp/localclip-resume-cache`, porta 8766. Dados temporários não substituem projetos do usuário. Credenciais somente Secret Service, nunca chat/Git.

## Invariantes
Tempos absolutos da fonte; `crop_x=null` significa automático; revisão invalida render; render no editor salva antes; erros inesperados não viram sucesso local; fallback só transitório; nunca inventar timestamps de palavras. Cache de análise v2 e IA v1.1.0.

## Próxima evidência necessária
Credenciais configuradas pela UI para chamadas autenticadas e fallback real; vídeos representativos para avaliar semântica, tracking e sincronização perceptual. Fontes sintéticas VFR/anamórficas/rotacionadas foram exercitadas; não inferir qualidade a partir de resolução/decodificação. Prévia CSS é aproximada; render final é referência.

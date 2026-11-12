# Verificação

## Correção após revisão independente — 2026-10-08

- Primeira revisão: **8,8/10**, com um achado de enquadramento vertical. Reproduzido: dois rostos em alturas distintas numa fonte 1080×1920 resultavam em foco Y=0,475, recortando o espaço vazio entre ambos na saída 16:9.
- Correção: verificação das duas dimensões, margens e headroom antes de enquadrar o grupo; fallback mantém um sujeito com persistência em X e Y. Três regressões cobrem grupo alto demais, limite de headroom e grupo que cabe.
- `uv run --extra dev pytest -q`: **131 passaram**, um aviso Starlette/httpx. Build TypeScript/Vite concluído após os ajustes da prévia.
- Smoke real: fonte retrato 360×640 com dois rostos fotográficos em alturas distintas, quatro amostras OpenCV com dois rostos cada. Render 1920×1080, 2 s; detector no frame renderizado confirmou **um rosto**, imagem observada e decodificação integral FFmpeg exit 0.
- Chromium: editor com a fonte retrato e tracking real (candidato preparado somente como fixture de UI). Moldura 16:9, grupo que não cabe tratado como sujeito individual. O smoke revelou também uso incorreto das porcentagens de `object-position`; corrigida a conversão de coordenadas da fonte para overflow CSS. Screenshot final preservou o rosto inteiro, vídeo em `readyState=4` sem erro. A instância isolada foi encerrada.
- Segunda revisão independente: **9,2/10**, sem bloqueadores concretos identificados. O revisor conferiu código, regressões, documentação e imagens do render/prévia; os testes e smokes foram executados pelo responsável pela integração.

## Ajustes de 2026-10-07

- `uv run --extra dev pytest -q`: **128 passaram**, um aviso Starlette/httpx. Foram removidos testes novos que duplicavam a implementação dos atalhos ou fixavam textos de mensagens; as validações de comportamento e execução real foram mantidas.
- `npm --prefix web run build`: TypeScript e Vite concluídos.
- Instância real isolada na porta 8992, dados/cache/runtime/logs próprios; nenhuma configuração de projeto do usuário alterada.
- Catálogo: 9 opções OpenAI, 8 Gemini, 4 Anthropic, 6 compatíveis, 6 GLM e 9 OMP; descoberta real via OMP retornou 55 modelos. Chromium: seleção de `gemini-2.5-flash` e salvamento com provedor desabilitado confirmados pela API.
- Conta Google existente: teste real de inferência mínima por `google-antigravity/gemini-3.8-flash` respondeu JSON válido em aproximadamente 5,1 s, sem envio de vídeo. Isso comprova uso da conta já autenticada, não uma nova autorização interativa nem elegibilidade de todos os planos.
- Descoberta de modelos rejeita endpoints com query/credenciais/fragmento ou HTTP remoto antes do envio de chave. Reproduzido antes: endpoint local com query era aceito (HTTP 200); depois: HTTP 400.
- Régua Chromium: fonte de 12,345 s, arraste para [2,5; 10,1], Home/End, tentativa de ultrapassar o fim e colisão entre marcadores. Valores finais permanecem dentro da fonte e ordenados; ARIA preserva 12,345, não 12,3. Fonte de 0,4 s permanece [0; 0,4].
- Régua a 390×844 e 1440×1000: screenshot observado, sem overflow horizontal a 390 px; preferência de movimento reduzido aplicada aos controles. A API rejeitou intervalos além do fim, invertidos e negativos sem criar jobs.
- Visão real: vídeo controlado com fotografias de rosto em movimento, 4 s, detector OpenCV produziu [2,2,2,2,1,1,1,1] rostos. Renders reais H.264 nos três formatos (1080×1920, 1080×1080, 1920×1080), SAR 1:1, 4 s e decodificação integral sem erros.
- O smoke visual encontrou duplicação da pessoa no split-screen após mudança de composição. Corrigido: split estático exige múltiplas pessoas em todas as amostras; nova renderização 9:16 e detecção do frame de 3 s confirmaram exatamente um rosto, também observado visualmente. Cortes de cena e persistência de alvo têm regressões; o detector de cenas não detectou a mudança desta fixture de fundo quase constante.
- Lançadores: `desktop-file-validate`, `bash -n`, permissões 0755; confiança `metadata::trusted` aplicada aos dois atalhos neste ambiente. `gio launch` iniciou e parou a instância isolada; segundo iniciar reutilizou o PID, parada liberou a porta, e `restart` real iniciou novo PID.
- Pipeline pelo navegador: fonte de 29,3 s com fala sintética; envio do intervalo [1; 28,3] confirmado nas opções persistidas. Whisper produziu 69 palavras e o tracking 55 amostras; análise concluiu com corte [2,96; 24,82]. Editor iniciou a prévia em 2,96 s, exibiu rosto/zoom e renderizou H.264/AAC vertical. Reprodução final 1080×1920, duração 21,9 s, `paused=false`, sem erro do elemento de vídeo; exportação HTTP 200 e decodificação integral FFmpeg exit 0. O reconhecimento da fala sintética apresentou idioma/palavras incorretos: esta prova não valida precisão da transcrição.
- Parada final: servidor e dois descendentes desapareceram de `/proc`. O smoke revelou falso bloqueio de reinício por sockets HTTP em TIME_WAIT; `is_port_in_use` agora usa a mesma política de reuso de endereço do servidor. Regressão com sockets reais passou e dois ciclos consecutivos iniciar/parar via `gio launch` terminaram com porta livre.

## Integração de 2026-10-05

- `uv run --extra dev pytest -q`: **67 passaram**, um aviso de depreciação Starlette/httpx.
- `npm --prefix web run build`: TypeScript e Vite concluídos.
- Backend real em loopback, dados isolados em `/tmp/localclip-resume-data` e cache em `/tmp/localclip-resume-cache`.
- Vídeo sintético com fala de 68,46 s: importação por API e processamento real com Whisper local. Nova análise após atualização do pipeline terminou com três cortes; scores 71,0 / 70,4 / 68,4 ordenados. Título automático desligado produziu títulos neutros. Modelo Auto resolveu para Conversa / Talking Head.
- Chromium local: alterar título e clicar Renderizar salvou a revisão 2, manteve `crop_x=null`, concluiu render e carregou a URL da revisão correta. Screenshot e estado do player observados.
- Exportação dos três candidatos: 1080×1920 (9:16), 1080×1080 (1:1), 1920×1080 (16:9), todos H.264/AAC, SAR 1:1. Decodificação integral com FFmpeg: exit 0 nos três.
- Corte quadrado com remoção interna de 1 s: vídeo 20,083333 s e áudio 20,061995 s. Isso verifica duração/decodificação, não sincronização perceptual de fala humana.

- URL pública CC0 `https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4`: ingestão/proxy concluídos; metadata 960×540, 5,055 s.
- Cancelamento real durante render: estado observado `running` antes, `cancelled` depois.
- Editor Chromium: texto de palavra alterado, remoção [5,6] adicionada, salvamento/render automáticos concluídos; reprodução do MP4 com duração 21,177007 s e `paused=false`, sem erro do elemento de vídeo. Legenda queimada observada em screenshot.
- Fonte rotacionada 90° (320×240, display 240×320), sem áudio: render de 2 s em 1080×1920, SAR 1:1 e rotação 0.
- Fonte anamórfica 480×360 SAR 4:3, display 640×360: render de 2 s em 1080×1920 SAR 1:1.
- VFR: remoção [1,2] em [0,4] produzia 2,45 s; após preservar timestamps, produz 3,00 s. Regressão permanente com FFmpeg. Fonte VFR com áudio, início 0,5 s e duas remoções: vídeo 4,000000 s, áudio 3,993991 s, decodificação integral exit 0.
- Secret Service real: gravação, leitura idêntica, exclusão e ausência confirmadas com segredo descartável; nenhum valor registrado.

## Reproduções corrigidas

Resultados de diversidade fora da ordem de score; título automático ignorado; erros inesperados de provider convertidos em sucesso local; falha de reanálise sobrescrevendo opções/timeline anteriores; editor renderizando revisão antiga; perda de tracking automático ao salvar. Testes permanentes cobrem invariantes de ranking e preservação de análise; editor foi exercitado no navegador.

## Limites

Nova autorização OAuth interativa, outros provedores autenticados, fallback entre contas, qualidade semântica em conteúdo representativo, rostos reais em movimento/esportes e precisão perceptual em fala humana: **NÃO VALIDADOS** nesta rodada. O teste mínimo com a conta Google existente não comprova acesso de outros planos/modelos. Fotografias animadas e fala sintética comprovam mecânica, não qualidade geral; as fontes de rotação, SAR e VFR não cobrem todos os codecs/containers.

## Rodada de 2026-10-09

- `uv run --extra dev pytest -q`: **156 passaram**, um aviso de depreciação Starlette/httpx. `npm --prefix web run build`: TypeScript e Vite concluídos.
- Upload local de vídeo sintético de 68 s na instância isolada: miniatura 320×180 persistida e exibida no Chromium; `display_name` renomeado e preservado após recarregar; faixas `<30s` e `30s-59s` selecionadas simultaneamente e recebidas no payload.
- Falha proposital de OpenAI sem chave: checkpoint `ranking_failed` manteve timeline anterior. Após remover provider, botão **Tentar novamente** retomou o mesmo job sem reanálise e terminou `completed`, `attempts=1`.
- Render de corte real: MP4 H.264 1080×1920, AAC, duração 23,625 s; frame com legenda queimada observado. `reframe=True` e `subtitles=True` no estado de edição; editor atualizado não oferece desligar legendas.
- Vídeo temporário de 10 s com intro preta de 2 s: `extract_representative_thumbnail` persistiu frame posterior com desvio-padrão 82,99, não a tela preta.
- Fallback de dois provedores e erro esgotado: respostas simuladas em testes. Login OMP novo, cobrança OpenRouter, URL com thumbnail oficial e fallback com credenciais reais: **NÃO VALIDADOS**, dependem de contas/rede autorizadas.

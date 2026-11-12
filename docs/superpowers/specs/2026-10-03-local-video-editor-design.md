# Editor local de vídeos — especificação para revisão

Estado: proposta técnica; não descreve funcionalidades implementadas. A superfície web local foi escolhida pelo usuário. Escopo integral: PLANO_PROJETO_EDITOR_IA_VIDEO.md e solicitação principal; nenhuma fase foi removida.

## Objetivo e aceitação

Transformar vídeos locais ou URLs públicas legalmente utilizáveis em cortes revisáveis para TikTok, Shorts e Reels. Importação, intervalo, transcrição real com palavras temporizadas, cenas, timeline, pedidos semânticos, candidatos naturais, ranking explicável, Top N (padrão 3), preview, editor, reframe, legendas, render e exportação devem funcionar conjuntamente. Não prometer viralização. Ausência de evidência deve aparecer como NÃO VALIDADO, nunca como sucesso.

## Ambiente observado

Linux desktop (testado no Fedora com GNOME/KDE), máquina doméstica com recursos moderados, FFmpeg/ffprobe, uv, Node.js e Secret Service (GNOME Keyring ou KWallet). Encoders libx264, AAC e VA-API opcionais; execução acelerada depende de validação no hardware local.

## Arquitetura proposta

Backend Python/FastAPI, SQLite e um worker local em processo separado, com fila persistida no banco. Sem Redis, serviços externos obrigatórios ou contêiner obrigatório. Dependências de ML devem ter compatibilidade confirmada antes da instalação; usar Python isolado compatível caso 3.14 não seja suportado. Um job pesado por vez, com progresso por etapa e cancelamento propagado aos subprocessos. Jobs interrompidos não podem reaparecer como concluídos após reinício.

Frontend React/TypeScript compilado e servido pelo próprio backend. Telas: projetos/importação, processamento, resultados, editor e provedores. A UI nunca executa trabalho pesado. Polling de status e reprodução HTTP com suporte a ranges. Não adicionar chat ou assistant-ui sem necessidade funcional. Componentes de terceiros só após conferir requisitos oficiais.

API restrita a loopback, validação de Host/Origin e proteção de mutações contra CSRF. Arquivos acessados por identificadores internos, não por paths fornecidos livremente pelo navegador. Originais não são alterados. Exportação não sobrescreve arquivos silenciosamente.

## Dados e jobs

Diretórios XDG: banco, projetos e renders em XDG_DATA_HOME; modelos e artefatos regeneráveis em XDG_CACHE_HOME; configurações não secretas em XDG_CONFIG_HOME. Permissões privadas. Entidades: projeto, fonte, opções de análise, job, timeline versionada, candidato, avaliação, revisão de edição, render, configuração de provider, uso de IA e cache.

Persistir início/fim em segundos na referência temporal do original, identificadores de palavras e offsets explícitos. Edições criam revisão e invalidam apenas renders derivados. Chaves de cache incluem conteúdo, intervalo, configuração, versão do pipeline e modelo. Não reaproveitar ranking entre pedidos ou configurações diferentes.

## Ingestão e pipeline local

Arquivo via seletor/arraste ou URL pública por yt-dlp, sem cookies privados, DRM ou bypass. URLs remotas não podem atingir serviços locais/privados; redirecionamentos e extração precisam respeitar essa restrição. Mostrar progresso e erros reais. ffprobe determina streams, duração, rotação e dimensões antes do processamento.

Processar somente o intervalo escolhido. Extrair áudio mono temporário para transcrição local, usar faster-whisper com timestamps por palavra e VAD, e FFmpeg/OpenCV para silêncio, energia, cenas, faces e movimento. Seleção exata de modelos depende de documentação, licença e smoke de memória. CPU é caminho obrigatório; aceleração é habilitada apenas após prova de execução.

Timeline contém fala/palavras, cenas, silêncio, sinais de áudio e vídeo, keywords e tags com origem/confiança. Não atribuir risada, emoção, identidade ou ação esportiva apenas a energia/movimento. Eventos semânticos multimodais exigem um classificador real ou análise de amostras relevantes por provider visual, com autorização explícita para enviar imagens. Sem evidência suficiente, informar limitação em vez de fabricar evento.

## Pedidos e candidatos

Converter o pedido em critérios estruturados de tópico, emoção, reação, ação, cenário e modalidade necessária. Buscar semanticamente nos dados relevantes, não apenas por substring. Gerar 10–20 candidatos quando a fonte comportar, usando limites de fala, pontuação, silêncio, cena e completude. Fontes curtas podem produzir menos candidatos; não duplicar para preencher Top 3.

Sentido e conclusão precedem duração preferencial. Guardar desvios justificados da duração. Modelo de clipe, gênero, plataforma, duração e pedido afetam estratégia ou pesos reais. Todas as opções enumeradas na solicitação devem estar disponíveis, inclusive duração personalizada e gênero Auto.

## Ranking e IA

Dimensões positivas de 0–100: Hook, Flow, Value, Platform Fit, Narrative Completeness, Emotional Intensity, Audio Signals, Visual Signals, Shareability. Penalidades separadas de contexto e silêncio. Fórmula proposta: clamp(soma(w_i * d_i) / soma(w_i) - penalidade_contexto - penalidade_silêncio, 0, 100). Pesos, fusão local/semântica e penalidades terão constantes explícitas e exemplos em docs/VIRALITY_RANKING.md antes da implementação do ranking.

Não fabricar notas semânticas quando IA estiver indisponível. Modo local deve ser identificado como tal, distinguindo dimensões observadas de ausentes. Avaliação semântica recebe lote compacto de candidatos e contexto suficiente, não o vídeo inteiro. Respostas validadas contra schema e limites do original; texto do vídeo é dado não confiável, nunca instrução de ferramenta.

Adapters iniciais: OpenAI, Gemini, Anthropic e OpenAI-compatible. Interface: understand_request, analyze_candidates, rank_candidates, generate_title, health_check. Orquestração agrupa avaliação/ranking/títulos quando possível, evitando uma chamada por candidato. Modelos configuráveis, sem presumir disponibilidade de nomes. Autenticação e endpoints dependem de consulta oficial atual antes de implementação. Assinatura de chatbot não implica acesso à API.

Principal e fallback sequenciais, apenas em quota/rate limit/indisponibilidade/erro temporário. Não fallback automático em erro de schema. Registrar provider efetivamente usado, modelo, chamadas, tokens quando informados, duração e erros sanitizados. Cache respeita identidade da configuração. Credenciais exclusivamente no Secret Service; indisponibilidade do serviço é erro explícito, não motivo para gravar segredo em texto.

## Render e editor

Saída MP4 H.264/AAC, formatos 9:16, 1:1 e 16:9, pixels quadrados e orientação correta. Reframe usa detecção e tracking, suavização e plano de enquadramento persistido. Para múltiplos sujeitos, avaliar split screen; quando crop perder conteúdo, preservar quadro em vez de zoom aleatório. Editor permite rever e ajustar enquadramento.

Legendas derivadas de palavras reais, editáveis, com estilo/tamanho/posição/destaque e preview do mesmo resultado usado na exportação. Escape de texto para ASS e subprocessos sem shell. Editor altera limites, remove trechos internos, revisa título/legendas/proporção/enquadramento e renderiza novamente. Remoções internas exigem mapear timestamps de legendas e tracking para a timeline de saída.

Resultados mostram posição, potencial estimado, preview, duração, timestamps, título, resumo, dimensões e explicação. Ações assistir, editar, renderizar, exportar e excluir; exclusão nunca remove o arquivo original do usuário.

## Verificação e documentação

Cada subsistema terá smoke real e testes permanentes para invariantes/limites relevantes. E2E: importar, metadata, áudio, transcrição, palavras, cenas, timeline, candidatos, ranking, Top 3 quando possível, render, reprodução no navegador, áudio, sincronização de legendas e proporção. Testar edição e novo render, intervalo, cache, cancelamento e falhas de provider. Testes com respostas simuladas não validam integração real de provider.

Sem credenciais fornecidas com segurança não se pode validar chamadas autenticadas ou fallback real. Nenhuma credencial foi solicitada em chat. Qualidade semântica, tracking e sincronização precisam de vídeos representativos; mídia sintética prova mecânica, não qualidade geral.

Manter os treze documentos exigidos, diferenciando IMPLEMENTADO, TESTADO, VALIDADO, EM ANDAMENTO, PENDENTE, NÃO VALIDADO e PROBLEMAS CONHECIDOS. Inicializar Git com ignore de credenciais/dados/modelos, preservar arquivos existentes e criar commits específicos revisados, sem adicionar configurações privadas automaticamente.

## Ordem de execução

1. Fundação, ingestão e extração/transcrição/cenas.
2. Timeline, critérios, candidatos, ranking e Top N.
3. Tracking, cortes, legendas e render.
4. Interface, preview, resultados e editor.
5. Integração completa dos providers, segurança e fallback.
6. E2E, correções e documentação coerente.

Contratos de provider e dados são definidos antes das fases consumidoras, sem stubs apresentados como funcionalidades. A ordem de fases não dispensa verificação incremental.

## Riscos e decisões

Web local foi escolhida pelo usuário; Qt e Tauri acrescentariam outro fluxo de UI/empacotamento. Memória e disco limitam modelos e concorrência. VA-API anunciado não prova encoder operacional. Completude narrativa e potencial são estimativas explicáveis, não garantias. Vídeos sem fala requerem evidência visual/áudio adequada. Não é possível garantir cortes semanticamente perfeitos em toda entrada; o editor e as limitações explícitas fazem parte do contrato.

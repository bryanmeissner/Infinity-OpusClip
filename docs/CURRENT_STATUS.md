# Estado atual

## IMPLEMENTADO
FastAPI, SQLite, worker separado, React/TypeScript, arquivo/URL pública, transcrição local, timeline, ranking local/híbrido em lote, providers, editor, reframe, legendas, render e exportação.

Lançadores e Supervisor Desktop: lançadores gráficos em português (`Iniciar LocalClip.desktop`, `Parar LocalClip.desktop`), scripts de inicialização/parada (`iniciar.sh`, `parar.sh`), supervisor Python nativo (`scripts/supervisor.py`) com gerenciamento de singleton seguro, verificação de portas ocupadas por terceiros, prevenção de reciclagem de PID, encerramento gracioso de descendentes, suporte a execução headless (`--headless`) e documentação em `docs/SETUP.md`.

Retomada: corrigidos ordenação final, título automático, resolução do modelo Auto, pesos por duração, propagação de erros de provider, cache semântico por ID, Gemini API_KEY_INVALID, preservação de análise anterior quando reanálise falha, salvamento antes de render, edição textual de legendas, remoções internas, reframe automático e coordenadas de reprodução.

Rodada 2026-10-09: faixas múltiplas/Auto exclusivo, contagem automática com deduplicação, `display_name` editável, miniaturas persistentes, reframe/legendas obrigatórios em cortes gerados, cartões de provedores responsivos, OpenRouter, ID opcional de Cloud Project para OMP e checkpoint com retomada/fallback sequencial. Falhas de provedores configurados não rebaixam silenciosamente para ranking local; job falho preserva análise para retry.

## TESTADO
156 testes passaram na suíte completa após correção do contrato de erro de provedores, propagação das faixas ao prompt, suporte a modelos de raciocínio no OpenRouter e limpeza do ID de projeto OMP; build TypeScript/Vite passou. Smoke real: upload de vídeo sintético de 68 s, seleção simultânea de duas durações na UI, job, render H.264/AAC com reframe e legendas, falha de provider sem chave e retomada pelo botão após mudar para modo local. Miniatura com intro preta de 2 s foi amostrada mais adiante (desvio-padrão do frame final 82,99); editor no Chromium não exibe botão de desligar legenda. Ver `docs/TESTING.md` para evidências anteriores.

## VALIDADO
Instância isolada: vídeo sintético de 68,46 s, Whisper CPU, 145 palavras com intervalos válidos, uma cena, 137 amostras de tracking, Top 3 ordenado. Reanálise com cache terminou em 0,12 s. Render/exportação nos três formatos com H.264/AAC, SAR 1:1 e decodificação integral sem erro. Remoção interna de 1 s exercitada no quadrado. Chromium: edição de título salva antes de renderizar, tracking automático preservado, revisão nova carregada.

## EM ANDAMENTO
Validação qualitativa e de integrações externas depende dos insumos descritos abaixo. Implementação integrada concluída; não considerar a aceitação integral concluída sem essas evidências.

## PENDENTE
Nova autorização OAuth interativa, fallback entre contas reais e vídeos humanos representativos dependem da interação/credenciais do usuário. URL pública, cancelamento real de render, reprodução após remoção interna e fontes sintéticas rotacionadas/anamórficas/VFR já foram exercitados em rodada anterior (TESTING.md). Retiming VFR corrigido e protegido por regressão.

## NÃO VALIDADO
Qualidade semântica geral, acompanhamento de falante ativo, tracking em filmagens humanas/esportes e precisão perceptual: sem mídia representativa fornecida. A conta Google existente foi exercitada com resposta mínima; outras contas/modelos e novo consentimento OAuth não foram validados. O vídeo controlado com fotografias de rostos comprova detector/render, não qualidade universal.

## PROBLEMAS CONHECIDOS
Aviso Starlette/httpx. Prévia CSS é aproximada, não substitui render final. Ranking é heurístico sem provider e não garante viralização. Resolução e decodificação corretas não estabelecem qualidade perceptual.

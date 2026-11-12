# Interface e experiência

React 18/TypeScript/Vite, servidos pelo backend local. Estilos em `web/src/index.css`, ícones Lucide, fontes do sistema; sem CDN em runtime. O tema escuro existente foi preservado. Não há certificação WCAG: foco, contraste e navegação precisam ser avaliados nas superfícies reais.

## Telas

- Projetos: upload por seletor/arraste, URL pública, metadata, abertura e exclusão de cópias geridas pelo aplicativo.
- Processamento: intervalo em barra de dois marcadores, três modelos, gêneros, **múltiplas durações** (Auto exclusivo), plataforma, proporção, quantidade de cortes automática, título, reframe/legendas sempre ativos e consentimento de imagens. A barra usa a duração real do arquivo e inicia com o vídeo inteiro; arraste, clique no trilho ou use setas (1 s), Shift + seta (10 s) e Home/End. Início e fim não se cruzam nem ultrapassam a fonte. Tempos exibem milissegundos e os valores ARIA preservam os limites exatos. Sem duração válida, o processamento permanece bloqueado. Mudar projeto reinicializa o formulário.
- Resultados: ranking de Potencial estimado, dimensões e explicação; filtros, preview, editar, renderizar, exportar e excluir. Score refere-se à análise, não é recalculado ao editar manualmente.
- Editor: limites, título, edição de texto por palavra preservando timestamps, proporção, tracking automático ou centro manual, estilo/tamanho/posição de legendas e remoções internas arbitrárias. Intervalos sobrepostos são unidos. O editor carrega palavras adicionais da timeline para permitir ampliar o corte dentro do intervalo analisado.
- Providers: listas de modelos por provedor com catálogo local e descoberta pela API/OMP; digitação manual é opcional. API keys ficam no Secret Service. Contas compatíveis podem usar login no navegador gerenciado pelo OMP, sem copiar tokens para o LocalClip; disponibilidade depende das permissões e cotas de cada conta. Há teste, principal/fallback e desconexão da configuração local. Remover a configuração não desconecta a conta global do OMP.
- Métricas: chamadas/tokens/duração/erros quando informados; não presumir preço ou consumo inexistente.

## Contratos de interação

Bootstrap lista resumos; seleção hidrata detalhes. Polling de 1,5 s durante jobs ativos, 3 s após falha de consulta; cleanup impede atualização por respostas de projeto abandonado. Estados terminais permanecem visíveis no cartão de job. Cancelar solicita cancelamento cooperativo, não garante conclusão imediata.

Renderizar no editor salva primeiro alterações pendentes. Erro de salvamento impede render. Revisões invalidam exportação; o player usa URL com revisão. `crop_x=null` preserva tracking automático; slider define centro manual e há ação para restaurar automático. Exportação fica indisponível quando há alterações não salvas.

Preview do original é aproximado, explicitamente identificado: acompanha rostos e mostra zoom estimado, mas não reproduz exatamente a trajetória nem o split-screen de FFmpeg. A moldura respeita 9:16, 1:1 ou 16:9; sem reframe, preserva a imagem inteira. Render final é a referência para enquadramento e sincronização. Controles do editor usam tempo absoluto da fonte e convertem para tempo relativo do render, descontando remoções. Preview rápido de resultados mostra o trecho original sem efeitos até renderizar.

## Verificação

Build e smoke Chromium registrados em TESTING.md. Validado salvamento de título antes de render, preservação de tracking automático e carregamento da revisão final. Responsividade em todas as larguras, acessibilidade completa e qualidade perceptual de legendas em fala humana: NÃO VALIDADAS.

## Ajustes de navegação e estados

Topbar sem seletor visual “Projeto Ativo”; o projeto é identificado pelo título `display_name` nos cartões, contexto de processamento, resultados e editor. Cartão oferece renomear inline, thumbnail com carregamento/placeholder e persistência após recarregar. Provedores exibem status, método de autenticação, conta OMP, chave, modelo, seleção principal/fallback e erros em cartões responsivos; OpenRouter aparece junto aos demais. Conta Google que exigir Cloud Project pode receber o ID no cartão OMP antes de “Entrar em conta”. Falhas de processamento preservam o cartão de job com estágio, erro, provider e ação “Tentar novamente” sem reiniciar a análise local.

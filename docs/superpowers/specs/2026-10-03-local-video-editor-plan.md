# Plano de implementação — editor local

A especificação 2026-10-03-local-video-editor-design.md foi aprovada pelo usuário. A skill writing-plans foi consultada, mas não está disponível neste ambiente; este plano explicita diretamente contratos, dependências e verificações.

## 1. Fundação e mídia

Criar pacote Python em src/localclip, ambiente isolado e frontend em web. Pesquisar compatibilidade oficial de transcrição, provedores e componentes antes de instalar. Criar banco SQLite com projetos, jobs, configurações, candidatos, revisões, renders, cache e uso. Definir schemas com timestamps absolutos. Implementar ingestão local/URL segura, ffprobe, intervalo, áudio, VAD, transcrição por palavra, cenas e sinais locais. Worker separado com progresso, cancelamento e recuperação explícita de interrupção. Prova: importar vídeo com fala e observar artefatos reais até timeline.

## 2. Semântica e ranking

Implementar critérios estruturados do pedido e evidências multimodais, geração de candidatos naturais e avaliação agrupada. Definir fórmula/constantes por gênero, plataforma, duração e pedido em código e VIRALITY_RANKING.md. Persistir dimensões ausentes sem inventar scores. Prova: pedidos distintos alteram seleção justificadamente; cache evita repetição; Top N não duplica resultados.

## 3. Render

Implementar plano de crop/tracking, múltiplos sujeitos, ajustes manuais e formatos. Implementar ASS com palavras reais e edição, concatenação de trechos e remapeamento temporal. Prova: exportar MP4 nos três formatos, inspecionar streams e decodificar áudio/vídeo; comparar legenda e tracking no preview.

## 4. Interface

Implementar importação, todos os controles exigidos, jobs, resultados ordenados, editor e configurações. Servir frontend compilado em loopback com proteção de origem e acesso a mídia por ID. Prova no navegador real: importar, processar, assistir, editar, renderizar e exportar sem congelamento da UI.

## 5. Providers e segurança

Adapters OpenAI, Gemini, Anthropic e compatível; documentação oficial como fonte de endpoints/autenticação. Secret Service; sem fallback em texto. Fallback sequencial só em erros elegíveis, uso sanitizado, cache e batching. Prova com serviço controlado para classificação de falhas e com credencial real para integração, se disponibilizada com segurança. Não equiparar os dois tipos de evidência.

## 6. Aceitação

Executar fluxo completo com mídia representativa e registrar comando/resultado por etapa. Corrigir falhas, repetir caminho afetado. Revisar acesso a arquivos, URLs, credenciais, subprocessos, exclusão e cancelamento. Atualizar os treze documentos obrigatórios e criar commits por incremento funcional. Relatório final nos dez itens exigidos, sem declarar concluído o que não foi demonstrado.

## Método de execução

Opção A: execução nesta sessão, com tarefas independentes distribuídas somente depois de definir contratos compartilhados; integração e validação centralizadas.

Opção B: execução sequencial nesta sessão, sem agentes de implementação; mesmos contratos e critérios, menor concorrência de alterações.

## Retomada de integração — 2026-10-04

O usuário solicitou continuar a implementação existente. A arquitetura permanece FastAPI/SQLite/worker/React, sem nova stack. O repositório já contém as seis fases em código; a pendência é corrigir contratos e comprovar o fluxo integrado, não criar outro aplicativo.

1. Preservar arquivos e dados existentes; usar uma instância e diretórios temporários separados para validação.
2. Revisar mídia e providers em fatias independentes; centralizar ranking, API, UI e execução das verificações.
3. Reproduzir falhas de comportamento antes de corrigir; validar upload, URL pública, intervalo, transcrição real, timeline, cache, candidatos, render nos três formatos, edição, reprodução, exportação e cancelamento.
4. Executar build e suíte integrada após as alterações. Sincronizar os documentos com a implementação e com a evidência observada, removendo alegações contraditórias.
5. Registrar commits sem configurações privadas, credenciais, modelos ou vídeos. Chamadas autenticadas e qualidade em conteúdo representativo permanecem explicitamente NÃO VALIDADAS se faltarem os insumos.

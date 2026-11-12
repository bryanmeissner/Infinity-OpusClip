# PLANO DO PROJETO — Editor Inteligente de Vídeos Curtos

## 1. Visão geral

Este projeto tem como objetivo criar um software local para Linux Fedora capaz de transformar vídeos longos em cortes curtos de alta qualidade para plataformas como TikTok, YouTube Shorts e Instagram Reels.

O sistema deve permitir importar um vídeo local ou fornecer um link compatível, analisar o conteúdo, identificar automaticamente os melhores momentos, classificá-los por potencial estimado e gerar cortes prontos para revisão, edição e exportação.

A proposta é construir um sistema próprio, inspirado funcionalmente em ferramentas de clipping automático como o OpusClip, mas sem copiar código, modelos proprietários, identidade visual ou algoritmos privados.

O foco principal é:

- processamento local sempre que possível;
- baixo consumo de créditos de IA;
- modularidade;
- transparência;
- facilidade de manutenção;
- possibilidade de conectar diferentes provedores de IA;
- ranking próprio de potencial de corte;
- facilidade para outras IAs/agentes entenderem e continuarem o projeto.

---

## 2. Objetivo principal

O usuário deve conseguir:

1. adicionar um vídeo local ou um link compatível;
2. selecionar o intervalo do vídeo a ser analisado;
3. escolher o tipo/modelo de clipe;
4. selecionar o gênero do conteúdo;
5. escolher a duração desejada dos cortes;
6. informar em linguagem natural quais momentos deseja encontrar;
7. processar o vídeo;
8. receber candidatos classificados;
9. visualizar score e explicações;
10. assistir aos cortes;
11. ajustar início, fim, legenda, proporção e enquadramento;
12. renderizar e exportar os vídeos finais.

---

## 3. Princípio central: Local First

O projeto deve executar localmente o máximo possível.

Atividades que devem preferencialmente ser locais:

- leitura do vídeo;
- extração de metadata;
- extração e normalização de áudio;
- transcrição;
- timestamps;
- Voice Activity Detection;
- detecção de silêncio;
- detecção de cenas;
- análise básica de áudio;
- análise visual;
- OCR quando necessário;
- tracking de pessoas/rostos;
- criação de candidatos;
- corte;
- crop;
- resize;
- geração de legendas;
- renderização;
- armazenamento;
- cache;
- logs.

As IAs externas devem ser utilizadas principalmente para tarefas em que raciocínio semântico realmente agrega valor:

- compreensão do pedido do usuário;
- entendimento do contexto;
- avaliação semântica de candidatos;
- comparação de candidatos;
- análise de hook, payoff, coerência e contexto;
- geração de títulos;
- classificação/ranking.

O sistema não deve enviar um vídeo inteiro para uma IA externa por padrão se uma representação estruturada menor puder ser utilizada.

---

## 4. Fluxo geral pretendido

Fluxo conceitual:

Vídeo / URL
→ ingestão
→ metadata
→ áudio
→ transcrição
→ timestamps
→ VAD / silêncio
→ cenas
→ sinais visuais e de áudio
→ timeline estruturada
→ geração de candidatos
→ avaliação por IA quando necessário
→ ranking
→ Top N
→ preview
→ edição
→ renderização
→ exportação

O número padrão inicial de resultados deve ser 3, mas o sistema pode gerar e avaliar mais candidatos internamente.

Exemplo:

- gerar 10–20 candidatos;
- avaliar em lote;
- ordenar;
- apresentar Top 3.

---

## 5. Entrada de vídeo

A tela principal deve permitir:

### Arquivo local
- drag and drop;
- seletor de arquivo.

### URL
- campo para URL;
- suporte apenas a fontes legalmente utilizáveis;
- sem bypass de DRM, paywall, autenticação privada ou proteções.

Após carregar, mostrar quando possível:

- nome;
- origem;
- thumbnail;
- duração;
- resolução;
- FPS;
- tamanho;
- codec;
- áudio;
- faixa selecionada.

---

## 6. Seleção de intervalo

O usuário deve poder escolher apenas parte do vídeo para análise.

Exemplo:

00:00:00 ━━━━━━━━━━━━━━━━━━━━━━━━━ 00:27:03

O intervalo deve afetar de verdade o processamento, evitando gastar recursos com trechos que não serão utilizados.

---

## 7. Modelo de clipe

Opções iniciais:

- Auto;
- Conversa / Talking Head;
- Multimodal / Clip Anything.

### Auto
O sistema decide a estratégia mais adequada.

### Conversa / Talking Head
Prioriza:

- fala;
- contexto;
- argumento;
- história;
- começo e fim de raciocínio;
- pausas;
- interlocutores.

### Multimodal
Considera também:

- cena;
- objetos;
- ações;
- texto em tela;
- risadas;
- gritos;
- mudanças de energia;
- reações;
- movimento;
- eventos visuais;
- emoção quando tecnicamente viável.

---

## 8. Gênero do conteúdo

A interface deve permitir selecionar ou detectar automaticamente o gênero.

Exemplos:

- Podcast;
- Lifestyle;
- Vlog;
- Viagem;
- Comida;
- Beleza e moda;
- Fitness;
- Esportes;
- Basquete;
- Futebol;
- Futebol americano;
- Marketing e webinar;
- Talking Head;
- Discurso motivacional;
- Comentário;
- Entrevista;
- Entretenimento;
- Filmes;
- Drama;
- Reality / Talk Show;
- Notícias;
- Educacional;
- Review de produtos;
- História;
- Ciência e tecnologia;
- Música;
- Games;
- Outros.

O gênero não deve ser apenas visual: ele deve alterar pesos, regras e critérios do ranking.

---

## 9. Duração dos cortes

Opções pretendidas:

- Auto;
- < 30s;
- 30s–59s;
- 60s–89s;
- 90s–3min;
- 3min–5min;
- 5min–10min;
- personalizada.

A duração deve funcionar como faixa preferencial.

O sistema deve priorizar uma conclusão natural em vez de forçar um tempo exato.

---

## 10. “Incluir momentos específicos”

Esta é uma funcionalidade central.

O usuário poderá escrever pedidos como:

- “Compile todos os momentos hilários.”
- “Encontre as melhores reações.”
- “Pegue as partes em que todos começam a rir.”
- “Encontre quando falaram sobre inteligência artificial.”
- “Pegue as melhores jogadas.”
- “Encontre situações inesperadas.”

O sistema deve converter o pedido em critérios estruturados.

Ele não deve ficar limitado a pesquisa literal de palavras na transcrição.

Quando necessário, o pedido pode influenciar:

- tópicos;
- eventos;
- emoções;
- áudio;
- personagens;
- ação;
- cenário;
- reações;
- duração;
- peso no ranking.

---

## 11. Timeline estruturada

O projeto deve produzir uma representação intermediária do vídeo.

Exemplo conceitual:

```json
{
  "start": 322.20,
  "end": 351.84,
  "speakers": [],
  "transcript": "",
  "words": [],
  "scenes": [],
  "audio_events": [],
  "visual_events": [],
  "silence": [],
  "keywords": [],
  "semantic_tags": []
}
```

O objetivo é permitir que a IA trabalhe principalmente sobre dados estruturados, e não sobre o vídeo bruto inteiro.

---

## 12. Cortes naturais

O sistema deve evitar:

- frase cortada;
- piada sem payoff;
- história sem contexto;
- fim abrupto;
- início sem preparação;
- silêncio desnecessário.

Os limites devem combinar:

- timestamp por palavra;
- VAD;
- silêncio;
- pontuação;
- mudança de cena;
- análise semântica;
- contexto mínimo necessário.

---

## 13. Motor de candidatos

O sistema deve gerar candidatos de maneira eficiente usando sinais locais, antes de pedir análise externa.

Possíveis sinais:

- sentenças completas;
- mudança de assunto;
- intensidade do áudio;
- risada;
- reação;
- silêncio;
- mudança de cena;
- palavras-chave;
- entidades;
- eventos visuais;
- pedido do usuário.

A IA pode avaliar candidatos em lote.

Evitar uma chamada de IA completa por candidato sempre que possível.

---

## 14. Ranking de potencial

O projeto deve ter um mecanismo próprio de ranking de 0 a 100.

Não deve afirmar que um clipe “vai viralizar”.

O termo recomendado na interface é:

**Potencial estimado**

Dimensões iniciais:

### Hook
- primeiros segundos;
- curiosidade;
- surpresa;
- afirmação forte;
- pergunta;
- capacidade de parar o scroll.

### Flow / Coerência
- início;
- desenvolvimento;
- conclusão;
- ritmo;
- clareza.

### Value / Connection
Dependendo do gênero:

- humor;
- entretenimento;
- emoção;
- informação;
- utilidade;
- insight;
- identificação.

### Platform Fit
- adequação a conteúdo curto;
- duração;
- ritmo;
- formato.

### Narrative Completeness
- setup;
- desenvolvimento;
- payoff;
- conclusão.

### Emotional Intensity
- humor;
- surpresa;
- tensão;
- entusiasmo;
- indignação;
- reação.

### Audio Signals
- risada;
- grito;
- aplauso;
- energia;
- mudanças de ritmo;
- pausas relevantes.

### Visual Signals
- reação;
- movimento;
- gesto;
- ação;
- mudança de cena;
- atividade visual.

### Shareability / Quotability
- ideia autossuficiente;
- frase marcante;
- potencial de compartilhamento.

### Penalidades
- contexto externo excessivo;
- silêncio morto;
- enrolação;
- introdução lenta;
- repetição;
- corte incompleto.

O ranking deve ser híbrido:

**sinais determinísticos + análise semântica da IA**

e os pesos devem ser configuráveis conforme gênero, duração, plataforma e instrução do usuário.

---

## 15. Scores armazenados

Guardar separadamente, quando aplicável:

- overall_score;
- hook_score;
- flow_score;
- value_score;
- platform_fit_score;
- emotion_score;
- context_score;
- visual_score;
- audio_score;
- narrative_score;
- shareability_score.

Também guardar uma explicação curta do motivo da nota.

---

## 16. Resultados

A tela de resultados deve permitir visualizar:

- posição no ranking;
- score;
- preview;
- duração;
- título;
- timestamps;
- resumo;
- explicação;
- scores individuais.

Ações:

- assistir;
- editar;
- renderizar;
- exportar;
- excluir.

---

## 17. Editor simples

O objetivo não é criar um editor como Premiere.

A V1 deve permitir:

- alterar início;
- alterar fim;
- visualizar preview;
- cortar trechos;
- revisar legenda;
- alterar proporção;
- alterar título;
- revisar enquadramento;
- renderizar novamente.

---

## 18. Reframe / zoom

O sistema deve suportar principalmente:

- 9:16;
- 1:1;
- 16:9.

Quando habilitado:

- detectar sujeito;
- acompanhar pessoa relevante;
- manter enquadramento;
- evitar crop indevido;
- lidar com duas pessoas;
- considerar split screen quando fizer sentido.

Não aplicar zoom aleatório apenas por estética.

---

## 19. Legendas

O sistema deve permitir:

- ativar/desativar;
- editar;
- escolher estilo;
- posição;
- tamanho;
- número aproximado de palavras;
- destaque da palavra atual;
- preview.

A sincronização deve usar timestamps reais sempre que possível.

---

## 20. Título automático

Toggle:

**Título automático**

Quando habilitado:

- usar apenas informações do conteúdo;
- criar título curto;
- evitar informação inventada;
- evitar clickbait falso.

---

## 21. Provedores de IA

Criar uma tela:

**Configurações → Provedores de IA**

Provedores iniciais possíveis:

- OpenAI / ChatGPT;
- Google Gemini;
- Anthropic Claude;
- provedores compatíveis com OpenAI;
- modelos locais futuramente.

Cada provider deve ser implementado por adapter.

Interface conceitual:

```text
AIProvider
├ understand_request()
├ analyze_candidates()
├ rank_candidates()
├ generate_title()
└ health_check()
```

A aplicação não deve depender diretamente de um único fornecedor.

---

## 22. Autenticação de IA

O sistema pode oferecer métodos como:

- API Key;
- OAuth;
- login oficial do provedor;

mas somente se o método for oficialmente suportado para aquele tipo de aplicação.

Nunca implementar:

- roubo de cookie;
- reutilização clandestina de sessão;
- scraping de login;
- captura indevida de tokens;
- bypass de cobrança;
- autenticação não documentada.

Se um provedor não permitir determinado método, a interface deve informar isso.

---

## 23. Segurança de credenciais

Credenciais não podem ficar:

- hardcoded;
- em Git;
- em logs;
- em arquivos públicos.

No Fedora/Linux, usar solução segura compatível com o ambiente, preferencialmente Secret Service/keyring ou equivalente.

A tela deve permitir:

- conectar;
- testar;
- escolher modelo;
- desconectar;
- verificar status.

---

## 24. Fallback de IA

Permitir:

- provedor principal;
- provedor fallback.

Exemplo:

Gemini → principal  
OpenAI → fallback

O fallback pode ser acionado em casos como:

- rate limit;
- quota;
- indisponibilidade;
- erro temporário.

Não fazer chamadas duplicadas aos dois provedores por padrão.

---

## 25. Controle de custo

É requisito central.

Implementar quando aplicável:

- cache;
- batch;
- deduplicação;
- timeline resumida;
- seleção prévia local;
- reutilização de transcrição;
- reutilização de análise;
- chamadas agrupadas;
- logs de tokens quando o provider informar;
- logs de quantidade de chamadas;
- logs de tempo;
- logs de modelo utilizado.

---

## 26. Modelos locais

A arquitetura deve permitir integração futura com modelos locais, por exemplo via soluções como Ollama ou equivalentes.

Não é obrigatório na primeira versão.

---

## 27. Arquitetura

A stack definitiva deve ser escolhida depois da inspeção e planejamento técnico.

Princípios:

- modular;
- local-first;
- simples;
- testável;
- fácil de manter;
- sem infraestrutura desnecessária.

Possíveis módulos:

- frontend;
- backend local;
- job manager;
- storage;
- ingestão;
- media processing;
- transcription;
- scene detection;
- multimodal analysis;
- candidate generation;
- ranking;
- AI providers;
- render;
- UI state;
- logging;
- cache.

SQLite é aceitável inicialmente se atender aos requisitos.

Evitar por padrão:

- Kubernetes;
- microservices;
- Redis;
- cloud obrigatório;
- serviços pagos.

---

## 28. Organização de dados

Estrutura conceitual:

```text
project-data/
└── <project-id>/
    ├── source/
    ├── metadata/
    ├── transcript/
    ├── timeline/
    ├── candidates/
    ├── previews/
    ├── renders/
    ├── cache/
    └── logs/
```

Evitar duplicação desnecessária de arquivos de vídeo grandes.

---

## 29. Hardware

O software deve detectar o hardware real.

Não assumir NVIDIA/CUDA.

Usar aceleração quando disponível e compatível.

Sempre possuir fallback funcional em CPU.

---

## 30. Testes

Não declarar uma funcionalidade pronta sem testá-la.

Testes mínimos end-to-end quando houver vídeo disponível:

1. importar vídeo;
2. ler metadata;
3. extrair áudio;
4. transcrever;
5. gerar timestamps;
6. detectar cenas;
7. construir timeline;
8. gerar candidatos;
9. aplicar ranking;
10. selecionar Top N;
11. renderizar;
12. reproduzir;
13. validar áudio;
14. validar sincronização;
15. validar legenda;
16. validar proporção.

Quando não for possível validar algo, registrar explicitamente:

**NÃO VALIDADO**

com o motivo.

---

## 31. Documentação obrigatória para agentes e IAs

A pasta `docs/` faz parte do projeto e deve ser mantida atualizada.

Ela não é opcional.

Objetivo:

Permitir que qualquer outro agente ou IA consiga abrir o projeto, entender rapidamente:

- o que é;
- por que existe;
- como funciona;
- arquitetura;
- decisões;
- módulos;
- responsabilidades;
- dependências;
- estado atual;
- limitações;
- como testar;
- como continuar.

Arquivos mínimos:

```text
docs/
├── PROJECT_OVERVIEW.md
├── ARCHITECTURE.md
├── AI_PIPELINE.md
├── VIRALITY_RANKING.md
├── PROVIDERS.md
├── VIDEO_PIPELINE.md
├── UI_UX.md
├── DATA_MODEL.md
├── SECURITY.md
├── TESTING.md
├── DECISIONS.md
├── CURRENT_STATUS.md
└── AGENT_HANDOFF.md
```

### PROJECT_OVERVIEW.md
Objetivo, escopo e funcionamento geral.

### ARCHITECTURE.md
Arquitetura real implementada, módulos, dependências e fluxo entre componentes.

### AI_PIPELINE.md
Como as IAs são usadas, entradas, saídas, prompts estruturados, batching, fallback e controle de custo.

### VIRALITY_RANKING.md
Fórmula, dimensões, pesos, penalidades, scores e evolução do ranking.

### PROVIDERS.md
Provedores suportados, autenticação, modelos, limitações e adapters.

### VIDEO_PIPELINE.md
Ingestão, áudio, transcrição, timeline, candidatos, renderização e exportação.

### UI_UX.md
Telas, componentes, fluxo do usuário e decisões de UX/UI.

### DATA_MODEL.md
Banco, entidades, JSONs, schemas e relacionamentos.

### SECURITY.md
Credenciais, armazenamento, permissões, riscos e práticas adotadas.

### TESTING.md
Como testar, testes existentes, comandos e critérios de validação.

### DECISIONS.md
Registro das decisões arquiteturais importantes, com motivo e alternativas consideradas.

### CURRENT_STATUS.md
O que está:
- pronto;
- em andamento;
- pendente;
- conhecido como problema;
- não validado.

### AGENT_HANDOFF.md
Arquivo curto para qualquer nova IA/agente entender imediatamente:
- objetivo;
- onde começar;
- estado atual;
- arquivos importantes;
- comandos principais;
- próximos passos;
- o que não deve ser quebrado.

---

## 32. Regra de atualização da documentação

Sempre que uma alteração relevante mudar:

- arquitetura;
- fluxo;
- provider;
- ranking;
- banco;
- UI;
- pipeline;
- dependência;
- autenticação;
- testes;
- decisões importantes;

o agente responsável deve atualizar o arquivo correspondente em `docs/`.

Código e documentação não devem divergir.

Se houver conflito, o agente deve verificar o código real e corrigir a documentação.

---

## 33. Fonte de verdade

Ordem recomendada:

1. código executável e testes;
2. schemas/configurações reais;
3. documentação em `docs/`;
4. este plano.

Este arquivo define intenção e direção do projeto.

A documentação em `docs/` descreve a implementação real e atual.

---

## 34. Git

Usar Git.

Boas práticas:

- commits coerentes;
- não destruir alterações existentes;
- não incluir credenciais;
- não adicionar arquivos pesados desnecessários;
- atualizar documentação junto com mudanças relevantes.

---

## 35. Escopo inicial recomendado

### Fase 1
- estrutura;
- ingestão;
- metadata;
- áudio;
- transcrição;
- timestamps;
- cenas.

### Fase 2
- timeline;
- pedidos em linguagem natural;
- candidatos;
- ranking;
- Top 3.

### Fase 3
- corte;
- 9:16;
- legenda;
- renderização.

### Fase 4
- UI;
- resultados;
- preview;
- editor simples.

### Fase 5
- providers;
- autenticação;
- fallback;
- segurança.

### Fase 6
- testes end-to-end;
- correções;
- documentação;
- validação.

---

## 36. Não objetivos da V1

A primeira versão não precisa:

- competir feature por feature com o OpusClip;
- possuir ML próprio treinado;
- substituir editores profissionais;
- possuir colaboração multiusuário;
- usar cloud;
- ter microservices;
- publicar automaticamente em todas as redes;
- possuir analytics avançado.

A prioridade é ter um núcleo confiável e funcional.

---

## 37. Critérios de sucesso da primeira versão

A V1 será considerada bem-sucedida quando conseguir:

1. receber um vídeo;
2. processá-lo localmente;
3. transcrevê-lo;
4. identificar cenas/sinais relevantes;
5. gerar candidatos;
6. entender uma solicitação em linguagem natural;
7. classificar candidatos;
8. selecionar os melhores;
9. gerar pelo menos 3 cortes;
10. renderizá-los corretamente;
11. mostrar resultados em uma interface utilizável;
12. permitir conectar pelo menos um provider real de IA;
13. possuir documentação suficiente para outro agente continuar o projeto.

---

## 38. Regra para agentes futuros

Antes de modificar o projeto:

1. leia este arquivo;
2. leia `docs/PROJECT_OVERVIEW.md`;
3. leia `docs/ARCHITECTURE.md`;
4. leia `docs/CURRENT_STATUS.md`;
5. leia `docs/AGENT_HANDOFF.md`;
6. inspecione o código relevante;
7. confirme o estado real;
8. só então implemente mudanças.

Nunca assumir que uma funcionalidade existe apenas porque foi planejada.

Sempre diferenciar:

- planejado;
- implementado;
- testado;
- validado.

---

## 39. Filosofia do projeto

Este projeto deve ser construído com:

- simplicidade;
- rastreabilidade;
- baixo custo;
- processamento local;
- modularidade;
- documentação;
- testes reais;
- decisões justificadas;
- facilidade de continuidade por diferentes agentes e IAs.

O objetivo não é apenas “gerar cortes”.

O objetivo é construir uma base sólida para um editor inteligente de vídeos curtos que possa evoluir continuamente sem se tornar dependente de um único modelo, provedor ou serviço externo.

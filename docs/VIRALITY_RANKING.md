# VIRALITY_RANKING.md — Especificação e Fórmula do Ranking de Potencial

Este documento descreve a arquitetura, a fundamentação matemática, as matrizes de ponderação, as penalidades e os critérios do motor de ranking e corte natural do **LocalClip** (`src/localclip/ranking.py`).

---

## 1. Filosofia e Princípios Centrais

1. **Potencial Estimado (Nunca "Viralização Garantida")**:
   Nenhum algoritmo pode garantir que um vídeo vá viralizar, pois o sucesso nas redes depende de distribuição algorítmica externa, momento cultural e engajamento da audiência. O sistema reporta estritamente **"Potencial estimado"** em uma escala contínua de **0 a 100**.
2. **Local-First por Padrão**:
   Todas as métricas de áudio, vídeo, cortes de cena, fala, ritmo e limites naturais são computadas inteiramente na máquina do usuário através de sinais determinísticos da timeline.
3. **Transparência e Rastreabilidade de Proveniência**:
   Cada candidato possui o atributo `mode` (`'hybrid'` ou `'local'`) e uma justificativa detalhada (`reason`) informando exatamente quais sinais motivaram a nota. Quando nenhum provedor de IA externo está configurado, o sistema declara explicitamente:
   > *"Modo local: pontuação baseada em sinais determinísticos de áudio, vídeo, fala e ritmo. Análise semântica avançada de IA externa ausente."*
4. **Proibição de Alucinações e Títulos Falsos**:
   Em modo local ou na ausência de resposta da IA, títulos e resumos são extraídos e sintetizados estritamente a partir das palavras literais transcritas no candidato. Nunca são criadas alegações sensacionalistas falsas.
5. **Sentido Precede Duração**:
   A conclusão semântica de uma frase ou pensamento sempre tem prioridade sobre um limite de tempo arbitrário. Desvios justificados são registrados quando uma frase ultrapassa ligeiramente a duração alvo para fechar o raciocínio com dignidade.

---

## 2. Detecção de Limites Naturais de Corte

O corte de um clipe não pode ocorrer em instantes arbitrários. Cortes desajeitados (frases pela metade, histórias sem início ou piadas sem desfecho) destroem o engajamento.

### 2.1 Unidades de Fala e Pontuação
O sistema analisa a lista de palavras temporizadas (`timeline["words"]` e `timeline["segments"]`):
- **Pontuação Terminal**: Palavras que encerram com `.`, `!`, `?` ou `…` marcam limites. O parser atual não distingue abreviações; revisão humana continua necessária.
- **Pausas Naturais de Silêncio**: Intervalos de silêncio $\ge 0.55\,\text{s}$ entre palavras consecutivas são tratados como divisores naturais de fluxo respiratório e pensamento.

### 2.2 Conectivos e Aberturas Suspensas (Dangling Openers)
Se um corte iniciar com uma conjunção que requer contexto anterior, o candidato sofre penalidade de contexto ou é expandido para incluir a sentença de preparação:
- Conectivos penalizados no início: `e`, `mas`, `porém`, `contudo`, `todavia`, `entretanto`, `então`, `porque`, `pois`, `aí`, `daí`, `quando`, `já`, `onde`, `como`, `que`, `se`, `ou`, `caso`.
- Pronomes sem antecedente no início: `ele`, `ela`, `eles`, `elas`, `disso`, `daquilo`, `nisso`, `naquilo`.

### 2.3 Fechamentos Abruptos (Dangling Closers)
Um clipe nunca deve terminar em palavras que anunciam uma continuação:
- Palavras proibidas no término: `porque`, `mas`, `porém`, `pois`, `então`, `quando`, `se`, `que`, `como`, `ou`, `para`, `com`, `de`, `em`, `ou seja`, `quer dizer`.

### 2.4 Alinhamento e Snapping com Cortes de Cena
- **Início (`start`)**: Recua $0.08\,\text{s}$ antes da primeira palavra para não truncar o fonema de ataque. Se houver um corte de cena (`timeline["scenes"]`) até $0.40\,\text{s}$ antes, o início é alinhado com o corte de cena.
- **Fim (`end`)**: Avança $0.15\,\text{s}$ após a última palavra para acomodar o decaimento acústico natural. Se houver um corte de cena até $0.45\,\text{s}$ após, o término é alinhado com o corte de cena.

---

## 3. Motor de Geração de Candidatos (quantidade automática)

O motor varre a fonte inteira e propõe janelas de duração variável, conforme qualquer faixa selecionada. Não corta frases arbitrariamente e não impõe teto de resultados; avaliação remota usa lotes de até 20 propostas para conter o contexto.

1. **Acumulação Multiescala de Sentenças**:
   Itera a partir de cada oração inicial bem formada e acumula sentenças consecutivas até cobrir a faixa de duração alvo (`[min_duration, max_duration]`). Testa se cada término forma uma conclusão limpa.
2. **Âncoras de Interesse Acústico e Visual**:
   Localiza eventos de pico na timeline:
   - Eventos de áudio de alta energia: risadas (`laughter`), aplausos (`applause`), gritos (`shout`), comemorações (`cheer`).
   - Eventos visuais (`visual_events`) com alta confiança.
   - Correspondência de palavras-chave do pedido do usuário.
   Para cada âncora, o motor expande para trás buscando a oração de introdução e para frente buscando a conclusão.
3. **Fallback Multimodal por Cenas**:
   Em vídeos sem fala (conteúdo musical, clipes de ação esportiva ou gameplay silencioso), o motor agrupa transições de cena consecutivas (`scenes`) que correspondam à duração preferencial.
4. **Preservação de Enunciados Completos (Sem Fatiamento Arbitrário)**:
   Se a fonte não comportar múltiplas combinações, sentenças faladas são preservadas integralmente como unidades completas (`complete_utterance`), ou o intervalo total é preservado (`full_interval`). O sistema recusa terminantemente dividir palavras ou orações no meio apenas para forçar uma grade arbitrária de candidatos.
5. **Desduplicação por Sobreposição e Contenção Temporal**:
   $$\text{IoU}(A, B) = \frac{\max(0, \min(A_{end}, B_{end}) - \max(A_{start}, B_{start}))}{\max(A_{end}, B_{end}) - \min(A_{start}, B_{start})}$$
   $$\text{Contenção}(A, B) = \frac{\max(0, \min(A_{end}, B_{end}) - \max(A_{start}, B_{start}))}{\min(A_{end} - A_{start}, B_{end} - B_{start})}$$
   Na fase de geração, propostas com $\text{IoU} \ge 0.55$ ou $\text{Contenção} \ge 0.70$ são tratadas como variações redundantes do mesmo momento, preservando-se a proposta de maior pontuação de recuperação (`retrieval_score`).

6. **Seleção automática por qualidade e diversidade (`select_diverse_top_candidates`)**:
   - Ordena por score e aceita somente candidatos com score >= 40.
   - Rejeita se houver interseção > 2 s, IoU >= 0,15, contenção >= 0,20 ou similaridade lexical Jaccard >= 0,55 com candidato já aceito.
   - Não preenche número alvo; quantidade varia com a qualidade e diversidade do vídeo. Eventos diferentes muito próximos ou semanticamente semelhantes podem ser suprimidos por excesso de cautela.
## 4. As 9 Dimensões Positivas (0 a 100)

Cada candidato recebe uma nota de $0.0$ a $100.0$ em 9 dimensões positivas:

| Dimensão | Sinais Determinísticos Locais | Avaliação Semântica da IA (Modo Híbrido) |
|---|---|---|
| **Hook** | Latência da primeira fala ($<0.4\,\text{s} \to 100$), perguntas retóricas (`?`), termos de impacto ("segredo", "como", "você"), corte de cena ou áudio nos primeiros 3.5s. | Capacidade de capturar atenção inicial, fator surpresa e parada de scroll. |
| **Flow** | Cadência de fala (WPM ideal 140–165 ppm em português), desvio padrão de micropausas, ausência de cortes secos entre frases. | Coerência de desenvolvimento, ritmo da explicação e clareza de transições. |
| **Value** | Riqueza lexical (proporção de palavras únicas com $>3$ letras), sobreposição com palavras-chave da timeline e com o pedido do usuário. | Utilidade, relevância do insight, novidade ou valor cômico/informativo. |
| **Platform Fit** | Ajuste à curva de duração ótima da plataforma e respeito a restrições estritas (ex: teto oficial de 180s / 3 minutos no YouTube Shorts). | Adequação do tom e estilo às expectativas do formato curto vertical. |
| **Narrative** | Início limpo sem conjunção conectiva, término em pontuação conclusiva, presença de $\ge 2$ sentenças completas (setup + payoff). | Estrutura de início, meio e fim da história ou argumento. |
| **Emotion** | Confiança dos eventos acústicos disponíveis, marcas de exclamação e vocabulário emotivo. Picos acústicos locais não comprovam risada/aplauso/grito. | Intensidade de emoção percebida (humor, tensão, empatia, surpresa). |
| **Audio** | Confiança dos eventos acústicos e ocupação temporal da fala; não equivale a avaliação perceptual de qualidade sonora. | Clareza e impacto acústico geral. |
| **Visual** | Ritmo de cortes de cena (ideal de 4 a 14 cortes/minuto), eventos visuais de movimento, presença e estabilidade de rostos rastreados (`tracks`). | Dinamismo visual, apelo estético e enquadramento. |
| **Shareability** | Presença de frases marcantes concisas (3 a 10 palavras), autonomia do pensamento (baixo requerimento de contexto externo). | Potencial de identificação, memorabilidade e compartilhamento com amigos. |

---

## 5. Penalidades Explícitas (0 a 100)

As penalidades são subtraídas diretamente da soma ponderada:

### 5.1 Penalidade de Contexto (`context_penalty`)
Mede o grau de dependência de informações ausentes fora do recorte:
- Início com conjunção solta (`mas`, `porque`, `aí`, etc.): $+35.0$ pontos.
- Início com pronome sem antecedente (`ele`, `disso`, etc.): $+20.0$ pontos.
- Término em suspensão ou conjunção dangling (`porque...`, `mas...`): $+45.0$ pontos.
- Ausência de pontuação terminal ao final do clipe: $+20.0$ pontos.
- Em modo híbrido, a IA semântica contribui com $60\%$ do peso desta penalidade.

### 5.2 Penalidade de Silêncio (`silence_penalty`)
Mede a presença de pausas mortas que provocam abandono do espectador:
- Silêncio individual $\ge 1.5\,\text{s}$: $+35.0$ pontos.
- Silêncio individual entre $0.9\,\text{s}$ e $1.5\,\text{s}$: $+15.0$ pontos.
- Proporção total de silêncio na duração do clipe $> 15\%$: $+200.0 \times (\text{ratio} - 0.15)$ pontos.
- Em clipes multimodais com intensa atividade visual comprovada ($visual \ge 65$), a penalidade de silêncio é atenuada em $60\%$ (ex: cenas de ação ou gameplay visual).

---

## 6. Fórmula Matemática Oficial

Sejam:
- $d_i \in [0, 100]$ as 9 dimensões positivas: $d_1 = \text{hook}, d_2 = \text{flow}, d_3 = \text{value}, d_4 = \text{platform\_fit}, d_5 = \text{narrative}, d_6 = \text{emotion}, d_7 = \text{audio}, d_8 = \text{visual}, d_9 = \text{shareability}$.
- $w_i$ os pesos normalizados resolvidos para o gênero, plataforma e modelo de clipe, onde $\sum_{i=1}^9 w_i = 1.0$.
- $P_{\text{ctx}} \in [0, 100]$ a penalidade de contexto.
- $P_{\text{sil}} \in [0, 100]$ a penalidade de silêncio.
- $B_{\text{req}} \in [0, 25]$ o bônus de correspondência estrita ao pedido do usuário.

A pontuação final de potencial estimado é calculada por:

$$S_{\text{pos}} = \sum_{i=1}^9 w_i \cdot d_i$$

$$\text{Score} = \operatorname{clamp}\left( S_{\text{pos}} - 0.20 \cdot P_{\text{ctx}} - 0.15 \cdot P_{\text{sil}} + B_{\text{req}}, \; 0.0, \; 100.0 \right)$$

O resultado é arredondado para uma casa decimal.

---

## 7. Matriz de Pesos por Gênero (Todos os 27 Gêneros)

Cada gênero prioriza diferentes vetores de retenção:

| Gênero | Hook | Flow | Value | Plat Fit | Narr | Emo | Audio | Visual | Share | Foco Principal |
|---|---|---|---|---|---|---|---|---|---|---|
| **Auto** | 0.16 | 0.12 | 0.14 | 0.10 | 0.14 | 0.12 | 0.08 | 0.08 | 0.06 | Equilíbrio dinâmico |
| **Podcast** | 0.14 | 0.16 | 0.16 | 0.10 | 0.16 | 0.10 | 0.08 | 0.04 | 0.06 | Fluidez, valor e narrativa |
| **Lifestyle** | 0.15 | 0.12 | 0.12 | 0.11 | 0.12 | 0.13 | 0.07 | 0.10 | 0.08 | Identificação e estética |
| **Vlog** | 0.16 | 0.13 | 0.10 | 0.10 | 0.14 | 0.14 | 0.07 | 0.09 | 0.07 | Personalidade e narrativa |
| **Viagem** | 0.15 | 0.10 | 0.10 | 0.10 | 0.11 | 0.14 | 0.08 | 0.15 | 0.07 | Paisagens e emoção visual |
| **Comida** | 0.17 | 0.11 | 0.13 | 0.10 | 0.11 | 0.12 | 0.08 | 0.12 | 0.06 | Hook de apetite e preparo |
| **Beleza** | 0.16 | 0.12 | 0.13 | 0.10 | 0.12 | 0.11 | 0.06 | 0.13 | 0.07 | Demonstração visual e dicas |
| **Fitness** | 0.16 | 0.11 | 0.14 | 0.10 | 0.11 | 0.14 | 0.08 | 0.10 | 0.06 | Motivação e execução técnica |
| **Esportes** | 0.19 | 0.07 | 0.06 | 0.10 | 0.08 | 0.18 | 0.12 | 0.14 | 0.06 | Ação, grito de torcida, emoção |
| **Futebol** | 0.20 | 0.06 | 0.06 | 0.10 | 0.08 | 0.18 | 0.14 | 0.12 | 0.06 | Lance decisivo, narração e gol |
| **Basquete** | 0.20 | 0.06 | 0.06 | 0.10 | 0.08 | 0.18 | 0.13 | 0.13 | 0.06 | Cesta, drible e impacto sonoro |
| **Marketing** | 0.18 | 0.13 | 0.18 | 0.10 | 0.13 | 0.09 | 0.05 | 0.06 | 0.08 | Hook comercial e insight |
| **Talking Head** | 0.18 | 0.15 | 0.15 | 0.10 | 0.15 | 0.12 | 0.05 | 0.04 | 0.06 | Clareza vocal e retenção |
| **Discurso** | 0.16 | 0.14 | 0.15 | 0.10 | 0.16 | 0.16 | 0.05 | 0.03 | 0.05 | Retórica, clímax emocional |
| **Comentário** | 0.17 | 0.14 | 0.16 | 0.10 | 0.14 | 0.12 | 0.06 | 0.05 | 0.06 | Opinião, argumentos e ritmo |
| **Entrevista** | 0.15 | 0.15 | 0.16 | 0.10 | 0.16 | 0.11 | 0.07 | 0.04 | 0.06 | Pergunta e resposta completa |
| **Entretenimento**| 0.18 | 0.10 | 0.09 | 0.10 | 0.11 | 0.17 | 0.11 | 0.08 | 0.06 | Risos, dinamismo e reações |
| **Filmes** | 0.16 | 0.11 | 0.10 | 0.10 | 0.14 | 0.16 | 0.10 | 0.07 | 0.06 | Diálogo tenso ou cena dramática |
| **Reality** | 0.19 | 0.10 | 0.07 | 0.10 | 0.12 | 0.19 | 0.09 | 0.07 | 0.07 | Conflito, choque e revelação |
| **Notícias** | 0.18 | 0.14 | 0.20 | 0.10 | 0.15 | 0.08 | 0.05 | 0.05 | 0.05 | Fato central e síntese rápida |
| **Educacional** | 0.14 | 0.15 | 0.24 | 0.10 | 0.16 | 0.06 | 0.04 | 0.04 | 0.07 | Densidade conceitual e clareza |
| **Produtos** | 0.17 | 0.13 | 0.18 | 0.10 | 0.13 | 0.09 | 0.06 | 0.08 | 0.06 | Veredito, prós/contras e teste |
| **História** | 0.14 | 0.15 | 0.22 | 0.10 | 0.18 | 0.08 | 0.04 | 0.04 | 0.05 | Narrativa factual envolvente |
| **Ciência e tec**| 0.15 | 0.15 | 0.23 | 0.10 | 0.15 | 0.07 | 0.04 | 0.05 | 0.06 | Explicação de mecanismo e dado |
| **Música** | 0.16 | 0.11 | 0.06 | 0.10 | 0.06 | 0.18 | 0.22 | 0.05 | 0.06 | Melodia, ritmo e ápice sonoro |
| **Games** | 0.18 | 0.09 | 0.08 | 0.10 | 0.09 | 0.18 | 0.13 | 0.09 | 0.06 | Jogada insana, grito ou risada |
| **Outros** | 0.16 | 0.12 | 0.14 | 0.10 | 0.14 | 0.12 | 0.08 | 0.08 | 0.06 | Perfil geral balanceado |

---

## 8. Modificadores de Plataforma e Modelo de Clipe

### 8.1 Plataforma
Os pesos base do gênero sofrem multiplicação direta pelos fatores da plataforma e são renormalizados para somar $1.0$:

- **TikTok**:
  - Duração ideal: $28\,\text{s}$ ($\sigma = 12\,\text{s}$, limite $60\,\text{s}$).
  - Multiplicadores: Hook ×1,20; Emotion ×1,15; Flow ×0,95; Value ×0,95; Visual ×1,05; Shareability ×1,05.
- **YouTube Shorts**:
  - Duração ideal: $45\,\text{s}$ ($\sigma = 25\,\text{s}$, suportando confortavelmente até $180\,\text{s}$).
  - **Teto Oficial de 180s (3 Minutos)**: Desde o final de 2024, o YouTube Shorts suporta vídeos de até 3 minutos. Se a duração passar de $180.0\,\text{s}$, a nota de `platform_fit` sofre penalização estrita por exceder o limite do Shorts ($\max(0, 40 - (\text{dur} - 180) \times 12)$).
  - Multiplicadores: Hook ×1,05; Emotion ×0,95; Flow ×1,05; Value ×1,15; Visual ×0,95; Shareability ×1,05. Narrative não recebe multiplicador de plataforma.
- **Instagram Reels**:
  - Duração ideal: $32\,\text{s}$ ($\sigma = 14\,\text{s}$).
  - Multiplicadores: Hook ×1,10; Emotion ×1,05; Flow ×1,00; Value ×0,95; Visual ×1,15; Shareability ×1,20.

### 8.2 Modelo de Clipe
- **Conversa / Talking Head**:
  - Flow $\times 1.20$, Narrative $\times 1.20$, Visual $\times 0.75$.
  - Exige continuidade da fala e rastreamento facial estável.
- **Multimodal / Clip Anything**:
  - Visual $\times 1.35$, Audio $\times 1.30$, Flow $\times 0.80$, Narrative $\times 0.80$.
  - Reduz em $60\%$ a penalidade de silêncio se houver alta atividade visual.
- **Auto**:
  - Detecta automaticamente a taxa de fala do vídeo: se fala ocupar $>60\%$ da duração, aplica o perfil de conversa; caso contrário, multimodal.


### 8.3 Modificadores por Critérios e Pedido Semântico do Usuário
A função `resolve_weights(options, criteria)` adapta dinamicamente a matriz de pesos de acordo com os critérios semânticos extraídos:
- **Humor / Riso** (`reaction: "riso"`, `emotion: "alegria"`): Aumenta os pesos de `emotion` ($\times 1.25$) e `audio` ($\times 1.15$).
- **Reação / Surpresa** (`reaction: "reação"`, `emotion: "surpresa"`): Aumenta `emotion` ($\times 1.20$) e `hook` ($\times 1.15$).
- **Ação / Dinâmica Visual** (`required_modality: "visual"` ou campo `action` não vazio): Aumenta `visual` (×1,25) e `hook` (×1,10).
- **Áudio Específico** (`required_modality: "audio"`): Aumenta `audio` ($\times 1.25$).
- **Argumento / Explicação** (`required_modality: "text"`, `reaction: "argumento"`): Aumenta `narrative` ($\times 1.20$) e `value` ($\times 1.15$).
Os critérios seguem precedência exclusiva na ordem acima (`if/elif`), não se acumulam entre categorias. Após a aplicação dos fatores, todos os pesos são renormalizados para somar exatamente $1.0$.

### 8.4 Duração e proveniência persistida

Além da seleção de janelas, a duração modifica pesos reais: alvo inferior a 30 s multiplica Hook por 1,15 e Shareability por 1,10; alvo a partir de 90 s multiplica Flow por 1,15 e Narrative por 1,25. Duração personalizada usa a média de mínimo/máximo. Os pesos são renormalizados ao final.

Cada candidato persiste `weights`, `request_boost` e `resolved_clip_model`. Auto resolve Conversa quando a união dos segmentos de fala cobre mais de 60% do intervalo; na ausência de segmentos usa palavras. Caso contrário resolve Multimodal. Gênero Auto usa pesos gerais, não classifica semanticamente o gênero.

Seleção por diversidade escolhe o conjunto e depois reordena os selecionados por score decrescente. `auto_title=false` produz título neutro de intervalo tanto no candidato quanto na edição. Erros inesperados de provider são propagados; somente a orquestração de providers decide fallback temporário.

---

## 9. Fusão Híbrida vs Modo Local Puro

O sistema opera de forma transparente em dois regimes:

### 9.1 Modo Híbrido (`mode: "hybrid"`)
Ocorre quando há um provedor de IA ativo e habilitado (`providers["primary"]` ou `providers["fallback"]`).
- O ranking envia o lote estruturado de candidatos pré-selecionados para `providers.evaluate_candidates`.
- A pontuação final de cada dimensão combinada é calculada por:
  $$d_i = 0.60 \cdot d_i^{\text{semântico}} + 0.40 \cdot d_i^{\text{local}}$$
- As dimensões puramente físicas (`platform_fit`, `audio`, `visual`, `silence_penalty`) permanecem 100% determinísticas para proteger a fidelidade à timeline real.
- O título e resumo enriquecidos pelo modelo de linguagem são adotados se válidos.

### 9.2 Modo Local Puro (`mode: "local"`)
Ocorre quando nenhum provedor está configurado ou os provedores esgotaram os erros temporários elegíveis:
- Sem provider, nenhuma chamada externa é realizada; com falhas temporárias pode haver tentativas antes do modo local.
- Chaves ausentes, autenticação inválida e schema inválido são erros explícitos, não sucesso local.
- $d_i = d_i^{\text{local}}$ para todas as dimensões.
- A justificação declara com total transparência a ausência de análise semântica externa e que as dimensões semânticas (como emoção, valor e shareability) são estimativas heurísticas locais baseadas em dados observáveis da timeline (frequência de exclamações, eventos sonoros e tags), não em compreensão real de linguagem natural.
- Títulos são gerados a partir da oração interrogativa ou dos primeiros 7 termos falados no corte, sem promessas sensacionalistas ou alegações falsas.

## 10. Evidências da Timeline Além do Texto

O motor de ranking consome diretamente dados não textuais:
1. **Rastreamento de Rostos (`tracks`) e Enquadramento Dinâmico**:
   Por padrão, `candidate["edit"]["crop_x"]` é estritamente `None`. Isso garante que o pipeline de renderização execute o rastreamento dinâmico facial quadro a quadro (`visual.py` / `media.py`) com suavização e reenquadramento automático. Uma coordenada estática de `crop_x` só é aplicada se o usuário definir manualmente um valor fixo no editor.
2. **Eventos Sonoros (`audio_events`)**:
   O ranking aceita eventos semânticos rotulados, mas o analisador local atual produz picos de energia, não um classificador de risadas/palmas/gritos. Não interpretar ausência desses eventos como ausência de humor.
3. **Cortes de Cena (`scenes`)**:
   Avalia a cadência de edição do material de origem. Um vídeo estático (0 cortes em 45 segundos) pontua baixo em `visual_score`, enquanto de 4 a 14 cortes por minuto pontuam na faixa de excelência ($>85$).
4. **Preservação de Conteúdo e Remoção Opcional (`silence`)**:
   `candidate["edit"]["remove_ranges"]` inicia estritamente como `[]`. O sistema nunca apaga silenciosamente trechos de conteúdo sem consentimento explícito do usuário. Faixas de remoção são adicionadas exclusivamente se o usuário decidir ativá-las na tela de edição.

## 11. Exemplos Práticos Numéricos

### Exemplo 1: Corte de Podcast Conclusivo (Modo Local)
- **Configuração**: Gênero: `Podcast`, Plataforma: `YouTube Shorts`, Duração: `30s–59s`.
- **Características do Trecho**:
  - Início: $14.2\,\text{s}$, Fim: $56.8\,\text{s}$ (Duração: $42.6\,\text{s}$).
  - Início com frase: "O maior erro de um fundador é...", sem conjunção solta.
  - Fim conclusivo: "...e é por isso que a empresa quebra." com ponto final.
  - Cadência: 148 palavras por minuto (WPM).
  - Silêncios: total de $1.1\,\text{s}$ distribuídos em micropausas normais.
- **Dimensões Calculadas**:
  - Hook: 88.0, Flow: 96.0, Value: 85.0, Plat Fit: 99.8, Narrative: 95.0, Emotion: 45.0, Audio: 72.0, Visual: 48.0, Shareability: 74.0.
  - Penalidades: Context Penalty: 0.0, Silence Penalty: 0.0.
- **Cálculo da Média Ponderada**:
  - Pesos Podcast normalizados para Shorts: Hook 0.13, Flow 0.17, Value 0.18, Plat Fit 0.10, Narr 0.17, Emo 0.09, Aud 0.07, Vis 0.03, Share 0.06.
  - $S_{\text{pos}} = 85.4$
  - $\text{Score Final} = \operatorname{clamp}(85.4 - 0 - 0, 0, 100) = \mathbf{85.4}$
- **Resultado**: Top 1. Justificativa reporta alta coerência narrativa e ausência de penalidades.

### Exemplo 2: Momento de Gameplay com Risada e Pedido do Usuário (Modo Híbrido)
- **Configuração**: Gênero: `Games`, Plataforma: `TikTok`, Pedido: "Pegue a parte mais engraçada onde todo mundo começa a rir".
- **Características do Trecho**:
  - Início: $110.0\,\text{s}$, Fim: $138.0\,\text{s}$ (Duração: $28.0\,\text{s}$).
  - Presença de evento de áudio `laughter` com confiança $0.92$ entre $122\,\text{s}$ e $127\,\text{s}$.
  - Correspondência com critério `reaction: "riso"`: bônus de relevância $+25.0$.
- **Notas Semânticas (IA)**: Hook: 95, Flow: 80, Value: 70, Narrative: 80, Emotion: 98, Shareability: 92, Context Penalty: 10.
- **Fusão Híbrida**:
  - Hook: $0.6 \times 95 + 0.4 \times 82 = 89.8$
  - Emotion: $0.6 \times 98 + 0.4 \times 88 = 94.0$
  - $S_{\text{pos}} = 88.1$
  - Penalidades: $0.2 \times 6.0 + 0.15 \times 0.0 = 1.2$
  - Bônus do Pedido: $+20.0$
  - $\text{Score Final} = \operatorname{clamp}(88.1 - 1.2 + 20.0, 0, 100) = \mathbf{100.0}$ (clampado no teto máximo).
- **Resultado**: Top 1 destacado com indicação de que atende diretamente à solicitação de humor do usuário.

### Exemplo 3: Clipe Penalizado por Corte Abrupto e Silêncio Morto
- **Características do Trecho**:
  - Início em: "...e aí ele me falou...", Fim em: "...porque quando nós...".
  - Silêncio morto de $2.8\,\text{s}$ no meio da fala.
- **Penalidades**:
  - Context Penalty: $+35.0$ (conjunção inicial) $+45.0$ (conjunção final) $= 80.0$.
  - Silence Penalty: $+35.0$ (pausa $>1.5\,\text{s}$) $+26.0$ (excesso de silêncio) $= 61.0$.
  - Subtração total: $0.20 \times 80.0 + 0.15 \times 61.0 = 16.0 + 9.15 = 25.15$ pontos de penalidade direta.
- **Resultado**: Rebaixado no ranking devido a corte truncado e quebra de retenção.

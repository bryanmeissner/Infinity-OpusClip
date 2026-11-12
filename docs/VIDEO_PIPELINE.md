# VIDEO_PIPELINE.md — Pipeline de Mídia e Visão Computacional

Este documento descreve a arquitetura, contratos, algoritmos, garantias de segurança e procedimentos operacionais dos módulos de processamento de mídia local (`src/localclip/media.py` e `src/localclip/visual.py`), responsáveis por ingestão, inspeção, análise multimodal determinística, reframe inteligente, subtítulos ASS e renderização do editor local.

---

## 1. Princípio Local-First e Arquitetura

O pipeline executa as etapas pesadas de áudio, visão computacional e transcrição localmente sem dependência obrigatória de serviços em nuvem (testado em Fedora Linux x86_64, FFmpeg 7.1+, Python 3.12, aceleração opcional VAAPI e CPU multithread).

### Módulos:
- `src/localclip/media.py`: Ponto de entrada do processamento. Fornece `probe()`, `ingest_url()`, `ensure_preview()`, `analyze()`, `render()` e aceleração por hardware VAAPI com fallback em CPU.
- `src/localclip/visual.py`: Detecção de cortes de cena, rastreamento de faces via OpenCV Haar Cascades, análise espacial de layout para split-screen, suavização EMA de pan, garantia de SAR 1:1 e extração de miniaturas.

```
                      ┌──────────────────────┐
                      │   Arquivo Local /    │
                      │     URL Pública      │
                      └──────────┬───────────┘
                                 │
                     ingest_url  │  probe (whitelist: file,pipe,crypto,data)
                                 ▼
                      ┌──────────────────────┐
                      │    ensure_preview    │ ───► Browser HTML5 Proxy (H.264/AAC, SAR 1:1)
                      └──────────┬───────────┘
                                 │
                              analyze (intervalo [start, end])
                                 │
        ┌────────────────────────┼────────────────────────┐
        ▼                        ▼                        ▼
 ┌───────────────┐       ┌───────────────┐       ┌─────────────────┐
 │ Extração Áudio│       │ Detecção Cenas│       │ Face Tracking   │
 │ 16kHz Mono    │       │ (visual.py)   │       │ (OpenCV Haar    │
 └───────┬───────┘       └───────┬───────┘       │ display dims)   │
         │                       │               └────────┬────────┘
         ▼                       │                        │
 ┌───────────────┐               │                        ▼
 │faster-whisper │               │               ┌─────────────────┐
 │ VAD + Palavras│               │               │ Visual Events & │
 └───────┬───────┘               │               │ Layout Analysis │
         │                       │               └────────┬────────┘
         ▼                       ▼                        ▼
 ┌─────────────────────────────────────────────────────────────────┐
 │                   Timeline Dict Estruturada                     │
 │ (start, end, segments, words, scenes, silence, audio, visual)   │
 └───────────────────────────────┬─────────────────────────────────┘
                                 │
                      render (Candidate + Edit)
                                 │
        ┌────────────────────────┼────────────────────────┐
        ▼                        ▼                        ▼
 ┌───────────────┐       ┌───────────────┐       ┌─────────────────┐
 │ Remapeamento  │       │ Reframe /     │       │ Subtítulos ASS  │
 │ Intervalos    │       │ Split-Screen  │       │ Highlight /     │
 │ (Cortes int.) │       │ Normaliz. SAR │       │ Classic         │
 └───────┬───────┘       └───────┬───────┘       └────────┬────────┘
         │                       │                        │
         └───────────────────────┼────────────────────────┘
                                 ▼
                      ┌──────────────────────┐
                      │  Encoder Selecionado │
                      │  VAAPI (h264_vaapi)  │
                      │  ou Fallback CPU     │
                      │  (libx264 / AAC)     │
                      └──────────────────────┘
```

---

## 2. Ingestão Segura de URLs (`ingest_url`)

Baixa vídeos públicos da internet utilizando `yt-dlp` sob proteção contra SSRF e cancelamento seguro:

1. **Validação Prévia de Segurança (`validate_public_url`)**:
   - Apenas esquemas `http` e `https`. Rejeição imediata de `file://`, `ftp://`, etc.
   - Bloqueio de hostnames locais e instâncias de nuvem (`localhost`, `127.0.0.1`, `::1`, `0.0.0.0`, `metadata.google.internal`, `.local`, `.internal`).
   - Resolução DNS inicial com verificação de IPs privados e não globais (`not ip.is_global`).
2. **Guarda de Runtime (`SafeSSRFContext`)**:
   - Intercepta `socket.getaddrinfo` durante o download pelo `yt-dlp` para validar todas as conexões subsequentes (redirecionamentos HTTP 301/302, manifestos e chunks de CDN). Conexões para IPs privados disparam `ValueError`.
3. **Cancelamento e Limpeza**:
   - Cancelamento limpo via callback `cancel()`. Em falha ou cancelamento, arquivos parciais (`.part`, `.ytdl`) são excluídos do disco.

---

## 3. Inspeção e Proxy de Reprodução (`probe` e `ensure_preview`)

### 3.1 Inspeção de Mídia (`probe`)
Executa `ffprobe` com saída JSON pura e protocolo restrito:
- **Whitelist de Protocolos**: `-protocol_whitelist file,pipe,crypto,data`, bloqueando requisições externas não autorizadas.
- **Rejeição de Manifestos**: Containers de rede pura (`hls`, `dash`, `applehttp`, `concat`) são rejeitados; exige container autônomo local.
- **Extração de Metadados e Aspect Ratio**:
  - `width`, `height`: Dimensões de armazenamento no container.
  - `sample_aspect_ratio`: Proporção de aspecto dos pixels (SAR). Se não square (ex: `4:3`), computa o fator de escala.
  - `display_aspect_ratio`: Proporção de exibição final (DAR).
  - `rotation`: Normalizado (0, 90, 180, 270) a partir de stream tags (`rotate`) ou side data (`Display Matrix`).
  - `display_width`, `display_height`: Dimensões reais de exibição considerando rotação automática do FFmpeg e correção anamórfica de SAR.
  - `duration`, `fps`, `codec`, `audio_codec`, `has_audio`, `has_video`, `sample_rate`, `channels`, `bitrate`.

### 3.2 Proxy de Pré-visualização (`ensure_preview`)
Garante arquivo MP4 compatível com `<video>` HTML5 do navegador:
- **Caminho Rápido (Remux)**: Aplicado apenas se o arquivo for MP4 nativo (H.264 + AAC ou sem áudio), com largura <= 1920, **SAR quadrado (1:1)** e **sem rotação (rotation == 0)**: `-c copy -movflags +faststart`.
- **Caminho de Transcodificação**: Se o vídeo for anamórfico (SAR != 1:1), possuir rotação, ou usar codecs incompatíveis (MKV, ProRes, VP9, HEVC), o proxy transcodifica preservando o aspecto de exibição:
  - Expansão de SAR anamórfico: `scale=trunc(iw*sar/2)*2:ih,setsar=1`
  - Escala limite: `scale='min(1280,iw)':-2`
  - Normalização: `setsar=1`
  - Codec: `libx264 -preset veryfast -crf 23 -pix_fmt yuv420p -movflags +faststart`

---

## 4. Análise Multimodal no Intervalo (`analyze`)

A análise executa estritamente dentro do intervalo selecionado pelo usuário `[start_sec, end_sec]`. Timestamps são expressos em coordenadas absolutas do vídeo original (`t_absoluto = start_sec + t_relativo`).

### 4.1 Entradas sem Áudio
- Se `meta['has_audio']` for falso, extração acústica, detecção de silêncio e Whisper são automaticamente ignorados.
- `segments = []`, `words = []`, `silence = []`, `audio_events = []`. A análise prossegue para visão computacional sem falhas.

### 4.2 Extração Acústica e Energia RMS em Streaming
- Quando há áudio: extração PCM 16kHz mono (`audio_16k.wav`) e detecção de silêncio via `silencedetect=noise=-30dB:d=0.5`.
- Leitura de amostras via módulo `wave` em janelas de 500ms (baixo uso de RAM).
- Picos acústicos (RMS > 2.8x da mediana, min 0.08) geram `"type": "audio_energy_spike"` com anotação explícita de incerteza: `"Sinal físico detectado; causa semântica não verificada"`.

### 4.3 Transcrição com faster-whisper e Contrato de Timestamps
- Transcrição CPU com faster-whisper (CTranslate2, modelo configurável via `LOCALCLIP_WHISPER_MODEL`, padrão `'base'`, quantização `int8`, 2 threads).
- `vad_filter=True`, `word_timestamps=True`.
- **Contrato de Timestamps**: Palavras e segmentos refletem estritamente as previsões do modelo com validação de monotonicidade (`w_end > w_start`, `w_start >= seg_start`).
- **Proibição de Sintetização Falsa**: Se o Whisper emitir um segmento sem timestamps de palavras (ou palavras forem filtradas), `seg_words` permanece lista vazia `[]`. É terminantemente proibido sintetizar artificialmente palavras ou distribuir linearmente tempos de tokens.

### 4.4 Visão Computacional (`visual.py`)
- **Detecção de Cenas**: FFmpeg `select='gt(scene,0.3)',showinfo` com precisão de `pts_time`.
- **Rastreamento Facial**: Amostragem a 2.0 fps utilizando `display_width` e `display_height` para preservar a orientação real do vídeo (mesmo após autorotation). Classificação por `cv2.CascadeClassifier` sem distorção anamórfica ou letterbox artificial.
- **Análise de Layout de Faces**: `analyze_face_layout()` recomenda split-screen estático apenas quando todas as amostras do trecho contêm múltiplos rostos e existe bimodalidade horizontal com separação $\Delta X \ge 0.28$. Uma amostra com uma pessoa ou sem detecção desativa o split para o trecho inteiro, inclusive em mudanças breves de composição. O custo conservador é preferir plano único quando o detector perde um rosto; evita duplicar a mesma pessoa em painéis fixos após uma mudança de composição. A detecção amostrada não garante identificar mudanças entre amostras.
- **Trajetória Temporal e Auto Zoom (`compute_reframe_trajectory`)**:
  - **Remapeamento Temporal**: Mapeia amostras de tempo absoluto do vídeo original para a linha de tempo de saída do clipe, respeitando cortes e remoções (`kept_intervals`).
  - **Auto Zoom Modesto Contido**: Escala entre 1.0x (planos próximos, face $\ge 26\%$) e 1.25x (planos abertos, face $\le 10\%$) para manter o sujeito em foco sem cortar queixo ou testa.
  - **Anti-Pumping e Decaimento Seguro em Intervalos Prolongados**: Intervalos curtos ($\le 2.0$s) usam interpolação linear para absorver piscadas ou viradas de rosto. Intervalos prolongados (> 2.0s sem faces, como cortes para paisagens ou b-roll) acionam transição suave de 1.5s de volta para o centro neutro (0.5, 0.5) e zoom 1.0x, permanecendo em enquadramento neutro até o sujeito reaparecer (transição de 1.5s para a nova posição). *Tradeoff*: impede que a câmera permaneça travada em bordas de cenários vazios durante planos de cobertura, mantendo transições estéticas naturais. Em clipes inteiramente sem faces, recai diretamente para centro neutro estático e zoom 1.0x.
  - **Múltiplas Pessoas e Enquadramento de Grupo**: O pipeline calcula a caixa delimitadora do grupo e verifica largura, altura, margem e headroom do recorte efetivo, inclusive em conversões de retrato para paisagem. O zoom do grupo é limitado a 1.10x e à capacidade das duas dimensões. Se o grupo não couber ou o posicionamento cortar sua caixa, escolhe o sujeito mais próximo da posição anterior em X e Y com zoom neutro, em vez de apontar para o espaço entre pessoas. A suavização e a detecção amostrada continuam sendo heurísticas; o render é a referência.
  - **Transições e Cortes de Cena (`scenes`)**: O reframe segmenta a linha do tempo com base nos limites de cena detectados (`scenes`). A suavização EMA bidirecional é executada estritamente dentro de cada cena individual, impedindo que a câmera deslize lentamente através de cortes secos ou inicie panorâmicas vazias antes do corte. Nos instantes de corte, transições discretas ($0.02$s) garantem cortes secos entre enquadramentos.
  - **Preview Aproximado**: A simulação rápida usa as dimensões de exibição da fonte e ambas as dimensões do recorte para decidir se o grupo cabe. `object-position` converte o foco da fonte para o deslocamento disponível do CSS, em vez de usar coordenadas de rosto diretamente como porcentagens. Usa `objectFit: cover` apenas com reframe ativo, `transformOrigin: 50% 35%` e moldura na proporção selecionada; sem reframe, a imagem inteira permanece visível. Não reproduz exatamente a trajetória nem o split-screen do render.
  - **Suavização Temporal**: EMA bidirecional (passada para frente e para trás, $\alpha = 0.85$ para $X, Y$; $\alpha = 0.35$ para $Z$) eliminando trepidação (jitter) sem defasagem temporal (lag).
  - **Resolução Temporal e Expressões Planas**: Keypoints amostrados em intervalos de $\Delta t \approx 1.5$s a $2.5$s mais keypoints discretos nos limites de corte de cena. O somatório linear telescópico plano (`v0 + delta * clip((t - t0)/dt, 0, 1)`) é avaliado nativamente pelo FFmpeg sem `if()` aninhados.
---

## 5. Renderização, Reframe e Subtítulos (`render`)

### 5.1 Parâmetros de Renderização por Formato
| Formato | Resolução | SAR | DAR | Mecanismo de Reframe e Auto Zoom |
|---|---|---|---|---|
| **9:16** (Vertical) | 1080x1920 | 1:1 | 9:16 | Rastreamento temporal $X(t), Y(t)$ com margem de topo (headroom 35%) e auto zoom $Z(t) \in [1.0, 1.25]$. Executado via `scale=...:eval=frame,crop=...:eval=frame,scale=1080:1920,setsar=1`. |
| **9:16** (Split) | 1080x1920 | 1:1 | 9:16 | Intencionalmente estático: painel superior (sujeito esquerdo, 1080x960) + inferior (sujeito direito, 1080x960) empilhados via `vstack=inputs=2,setsar=1` para evitar cinetose e deriva visual assimétrica em entrevistas. |
| **1:1** (Quadrado) | 1080x1080 | 1:1 | 1:1 | Rastreamento temporal $X(t), Y(t)$ e auto zoom $Z(t)$ com recorte quadrado proporcional e enquadramento headroom 40%. |
| **16:9** (Horizontal) | 1920x1080 | 1:1 | 16:9 | Rastreamento dinâmico temporal e auto zoom modesto: em fontes 16:9, zoom sutil cria margem de pan para acompanhar movimento lateral; em fontes 4:3 ou retrato, recorta e recentra suavemente no sujeito. |
| **Centro manual** | Conforme formato | 1:1 | Conforme formato | Se `crop_x` for informado, a posição usa centro horizontal fixo e zoom neutro 1.0x. Em cortes gerados, `reframe=False` legado não desativa o reframe obrigatório; só `crop_x` ajusta o enquadramento manualmente. |
### 5.2 Normalização de SAR Anamórfico
Quando a entrada tem pixels não-quadrados (`sample_aspect_ratio` diferente de `1:1` e `0:1`, como 1440x1080 com SAR 4:3):
- Antes de qualquer recorte ou split, é aplicado o filtro:
  ```
  scale=trunc(iw*sar/2)*2:ih,setsar=1
  ```
- Isso expande os pixels para o aspecto de exibição real (1920x1080) em vez de esmagar o conteúdo anamórfico.

### 5.3 Remoção de Intervalos Internos (`remove_ranges`) e Sincronia A/V
- `compute_kept_intervals(clip_start, clip_end, remove_ranges)` calcula os intervalos mantidos.
- Quando há múltiplos intervalos:
  - Vídeo: seleção de intervalos semiabertos `[início,fim)`, preservando timestamps e subtraindo somente início/gaps removidos. Não reconstruir timestamps por contagem de frames/FPS médio: isso encurta ou alonga fontes VFR.
  - Áudio: mesma seleção com `aselect`, seguida de `asetpts=N/SR/TB` e `-shortest`. Limites dependem dos frames de áudio; medição de duração não comprova sincronia perceptual.
  - Ausência de áudio: omite mapeamento de áudio sem duplicação de flags `-an`.

### 5.4 Subtítulos Queimados ASS (`generate_ass_subtitles`)
- Remapeamento temporal de palavras para o tempo do vídeo final cortado.
- Estilos `'highlight'` (iluminação de palavra ativa em amarelo `&H0000FFFF&`) e `'classic'`.
- Margem inferior segura de 240px em 9:16 (livre da interface de redes sociais).
- Sanitização de caracteres de controle ASS.

### 5.5 Encoders e Cancelamento
- **Hardware VAAPI**: Utiliza dispositivo `/dev/dri/renderD128` (se suportado e funcional):
  `-vaapi_device /dev/dri/renderD128 -c:v h264_vaapi -b:v 4M`
- **Fallback CPU Automático**: Em falha de driver VAAPI, executa `libx264 -preset fast -crf 22 -pix_fmt yuv420p`.
- **Cancelamento**: Interrupções (`cancel()`, `KeyboardInterrupt`, `BaseException`) encerram o grupo de processos (`os.killpg`) com SIGTERM/SIGKILL e excluem arquivos parciais imediatamente, sem disparar fallback CPU desnecessário.

---

## 6. Status de Verificação das Funcionalidades

| Componente / Funcionalidade | Escopo | Mecanismo | Status Atual |
|---|---|---|---|
| Ingestão e SSRF | Bloqueio de IP privado em DNS/redirects | `validate_public_url` + `SafeSSRFContext` | **VALIDADO** (Smoke real com URLs locais bloqueadas) |
| Inspeção de Mídia | Metadados, rotação e aspecto real | `probe()` com ffprobe + SAR/DAR parsing | **VALIDADO** (Smoke real: SAR 4:3, rotação 90° e display dims verificados) |
| Proxy de Reprodução | Remux H.264/AAC e transcode adaptativo | `ensure_preview()` com normalização de SAR | **VALIDADO** (Smoke real: 1440x1080 SAR 4:3 convertido para 1280x720 SAR 1:1) |
| Normalização SAR Anamórfico | Preservação de DAR sem esmagamento | `scale=trunc(iw*sar/2)*2:ih,setsar=1` | **VALIDADO** (Smoke real: 1440x1080 SAR 4:3 renderizado para 1080x1920 SAR 1:1 DAR 9:16) |
| Rotação e Autorotation | Orientação correta em visual/render | Uso de `display_width` e `display_height` | **VALIDADO** (Smoke real: vídeo 90° renderizado em 1080x1920 retrato) |
| Remoções e VFR | Duração após cortes internos | Seleção + remapeamento dos timestamps originais | **VALIDADO nos fixtures sintéticos**: 3,00 s sem áudio; duas remoções com áudio produzem vídeo 4,000000 s e áudio 3,993991 s. Sincronia perceptual não validada. |
| Entrada sem Áudio | Renderização e análise sem faixa de áudio | Detecção em probe e flags limpas | **VALIDADO** (Smoke real: renderização limpa com `has_audio=False` sem duplicação de flags) |
| Transcrição Whisper | Timestamps estritos de palavras | faster-whisper CPU int8 com timestamps | **VALIDADO** (Smoke real: modelo base; fallback sintético removido para preservar contrato) |
| Rastreamento Facial & Auto Zoom | Detecção OpenCV Haar + Trajetória Temporal + Auto Zoom | `track_subjects` + `compute_reframe_trajectory` + `build_reframe_filter` | **IMPLEMENTADO E VALIDADO**: Rastreamento temporal contínuo e auto zoom modesto (1.0x-1.25x) com proteção para múltiplas pessoas (enquadramento em grupo e histerese temporal sem oscilação), segmentação estrita por cortes de cena (sem gliding entre cenas), fallback neutro para ausência de faces e controle manual soberano (`crop_x`). |
| Subtítulos ASS | Legendas classic e highlight | `generate_ass_subtitles` remapeado | **VALIDADO** (Smoke real: queima de legendas com PlayRes e margem segura) |
| Cancelamento e Limpeza | Término limpo e remoção de parciais | `_kill_process_group` em `BaseException` | **VALIDADO** (Smoke real: cancelamento limpo e arquivos parciais unlinked) |
| CPU / VAAPI | Codificação por hardware e fallback libx264 | `is_vaapi_supported()` + fallback | **CPU VALIDADA**; não há evidência integrada de falha real VAAPI seguida de fallback. |
| Ingestão ao Vivo de URLs Arbitrárias | Download em produção de CDNs complexas | `yt-dlp` sob restrições de rede | **NÃO VALIDADO** (Depende de conectividade e provedores externos) |
| Modelos Grandes de Transcrição | Whisper large/medium em GPU | Configuração via `LOCALCLIP_WHISPER_MODEL` | **NÃO VALIDADO** (Apenas CPU int8 base validado localmente) |
| Provedores Externos de LLM/Ranking | Avaliação semântica por APIs remotas | Ranking engine externo | **NÃO VALIDADO** (Fora do escopo do pipeline local) |

## Imagem de capa e flags obrigatórias

`media.ingest_url()` pede a thumbnail oficial ao yt-dlp sob a mesma guarda de rede da ingestão e a converte localmente para JPEG privado. Se não houver imagem oficial, `visual.extract_representative_thumbnail()` extrai frame de vídeo/preview para `projects/<id>/thumbnail.jpg` por gravação temporária e substituição. Upload local usa essa segunda via; leitura posterior não reprocessa imagem válida. Projetos legados geram capa sob demanda; arquivo removido/geração inválida resulta em 410/404 e placeholder visual. Título remoto vem primeiro do sidecar do extrator; upload mantém stem do arquivo como nome exibido, com `source_title` informativo separado.

Na geração de candidatos, `reframe=True` e `subtitles=True` são normalizados mesmo quando opções antigas persistidas contêm `false`. No render, flags antigas `false` também são ignoradas para novos cortes; editor conserva ajustes de enquadramento e estilo/posição de legenda. Vídeo sem palavras temporizadas não permite inventar legendas: o filtro de legendas exige evidência real de transcrição.

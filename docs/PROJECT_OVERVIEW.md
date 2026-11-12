# LocalClip

Editor local-first para Fedora: transforma vídeo longo em candidatos de cortes curtos revisáveis para TikTok, YouTube Shorts e Instagram Reels. O score se chama **Potencial estimado** e não promete viralização.

O usuário importa arquivo/URL pública, seleciona intervalo, modelo de clipe, gênero, uma ou várias faixas de duração, plataforma, formato e pedido de momentos específicos. Reframe e legendas são sempre ativos na geração. Processamento local constrói a timeline; candidatos de qualidade são classificados com sinais determinísticos e, quando configurado, análise semântica externa em lotes, sem quantidade manual nem repetição do mesmo momento. Resultados podem ser vistos, editados, renderizados e exportados.

Vídeos não são enviados integralmente a providers por padrão. Transcrição, mídia, timeline, armazenamento e render são locais. O modo sem provider é explicitamente heurístico: não equivale à compreensão semântica de IA. Frames pontuais só podem ser enviados quando autorizados.

## Execução

Requisitos: Linux Fedora, FFmpeg/ffprobe, Python >= 3.12, uv, Node/npm (apenas para build do frontend), Secret Service para credenciais. Detalhes completos de instalação e segurança em [`docs/SETUP.md`](SETUP.md).

### Início Rápido (GNOME / KDE ou Terminal)

- **Lançadores gráficos**: Clique duas vezes em `Iniciar LocalClip.desktop` (para iniciar o servidor e abrir o navegador) e `Parar LocalClip.desktop` (para encerramento seguro). No GNOME Nautilus, habilite com botão direito -> *"Permitir execução"*.
- **Scripts diretos via terminal**:
  ```sh
  ./iniciar.sh            # Inicia servidor e abre navegador
  ./iniciar.sh --headless # Inicia servidor em modo headless (para testes)
  ./iniciar.sh status     # Exibe status da instância
  ./parar.sh              # Encerra com segurança servidor e workers
  ```
- **Execução manual**:
  ```sh
  uv sync --python 3.12 --extra dev
  npm --prefix web install
  npm --prefix web run build
  uv run localclip
  ```

Abrir http://127.0.0.1:8765. Primeiro uso de transcrição pode baixar modelo local; isso requer rede, mas não envia áudio para transcrição remota. API keys são configuradas na UI, não em arquivos versionados. Dados ficam em diretórios XDG; detalhes em DATA_MODEL.md.
## Escopo e evidência

Plano original: `PLANO_PROJETO_EDITOR_IA_VIDEO.md`. Desenho e plano de execução aprovados: `docs/superpowers/specs/2026-10-03-local-video-editor-{design,plan}.md`. A existência de código não comprova qualidade: consultar CURRENT_STATUS.md e TESTING.md para o que foi exercitado.

Não objetivos: editor profissional multitrilha, publicação automática, analytics social, cloud obrigatória ou treinamento de modelo proprietário.

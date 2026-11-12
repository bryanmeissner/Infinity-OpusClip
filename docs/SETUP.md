# Guia de Instalação e Execução (SETUP)

Este documento descreve a inicialização, parada segura, pré-requisitos e arquitetura de gerenciamento de processos do **LocalClip** no Fedora Linux (GNOME e KDE).

---

## 1. Pré-requisitos do Sistema

O LocalClip é uma aplicação local-first voltada para Fedora Linux. Os seguintes pacotes são necessários:

1. **Linux**: Kernel moderno com suporte a `procfs` e namespaces.
2. **Python >= 3.12**:
   ```sh
   sudo dnf install python3.12 python3.12-devel
   ```
3. **FFmpeg e ffprobe** (recomendado via RPM Fusion para suporte a todos os formatos H.264/AAC):
   ```sh
   sudo dnf install https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm
   sudo dnf install ffmpeg
   ```
4. **Gerenciador de pacotes uv** (pode ser instalado localmente no usuário, sem `sudo`):
   ```sh
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
5. **Node.js e npm** (necessários apenas caso seja necessário recompilar a interface web em `web/`):
   ```sh
   sudo dnf install nodejs npm
   ```

*Nota: Os scripts do projeto nunca executam `sudo` automaticamente. Pré-requisitos de usuário (`uv`, `.venv`, build web) são preparados de forma autônoma sem privilégios elevados. Caso algum pré-requisito de sistema (`ffmpeg`, `ffprobe`, `python3.12`) esteja ausente, o supervisor relata o comando apropriado de instalação (`sudo dnf install ...`) de forma clara e encerra com segurança.*

---

## 2. Inicializadores para Fedora GNOME / KDE

Para facilitar o uso sem a necessidade de comandos manuais no terminal, o repositório inclui lançadores gráficos na raiz do projeto:

- `Iniciar LocalClip.desktop`: Inicia o servidor, valida dependências/build e abre o navegador padrão em `http://127.0.0.1:8765`.
- `Parar LocalClip.desktop`: Encerra o servidor e todos os processos filhos/workers descendentes com segurança.

### Comportamento e Limites no GNOME (Nautilus) vs KDE (Dolphin)
- **KDE Dolphin**: Os arquivos `.desktop` possuem permissão de execução (`chmod +x`) e abrem com duplo clique diretamente, executando no diretório do projeto e respeitando caminhos com espaços e codificação URI.
- **Fedora GNOME (Nautilus)**: Por política de segurança do GNOME 43+, o Nautilus bloqueia por padrão a execução direta com clique duplo de arquivos `.desktop` mantidos em pastas arbitrárias do usuário (fora das pastas padrão XDG de aplicativos):
  1. **Opção recomendada no GNOME**: Execute diretamente os scripts shell clicáveis `./iniciar.sh` ou `./start.sh` (e `./parar.sh` / `./stop.sh`), que contam com suporte nativo a diálogos gráficos (`zenity`/`notify-send`).
  2. **Integração nativa com o Menu de Aplicativos (GNOME Dash)**: Crie links simbólicos para os atalhos **na raiz do checkout** (não copie: `%k` precisa resolver o caminho original):
     ```sh
     mkdir -p ~/.local/share/applications
     ln -sfn "$(pwd)/Iniciar LocalClip.desktop" ~/.local/share/applications/localclip-iniciar.desktop
     ln -sfn "$(pwd)/Parar LocalClip.desktop" ~/.local/share/applications/localclip-parar.desktop
     ```
     Execute estes comandos dentro do diretório do projeto. Mover o checkout depois exige recriar os links.
  3. **Confiança de metadados no Nautilus**: Em ambientes que suportam o atributo de confiança do Nautilus:
     ```sh
     gio set "Iniciar LocalClip.desktop" metadata::trusted true
     gio set "Parar LocalClip.desktop" metadata::trusted true
     ```
---

## 3. Scripts Shell Diretos (Alternativa ao .desktop)

Se preferir executar diretamente no terminal ou em gerenciadores de arquivos sem atalho desktop:

### Iniciar Aplicação
```sh
./iniciar.sh
```
- Inicia o servidor em `http://127.0.0.1:8765`.
- Abre automaticamente o navegador web padrão.
- Se já estiver em execução, não duplica o processo; em vez disso, foca/reabre a aba existente.
- Se executado via duplo-clique no gerenciador de arquivos (sem terminal), exibe notificações ou caixas de diálogo nativas (`zenity` / `kdialog` / `notify-send`) em caso de erro.

### Parar Aplicação
```sh
./parar.sh
```
- Envia sinal `SIGTERM` para o grupo de processos do servidor e workers.
- Aguarda desligamento gracioso com fechamento ordenado do banco de dados e liberação da trava de instância.
- Se necessário, força término com `SIGKILL` após o tempo limite.

### Reiniciar Aplicação
```sh
./iniciar.sh restart
```
- Executa parada segura de workers/servidor e reinicia na mesma porta.

### Verificar Status
```sh
./iniciar.sh status
```
---

## 4. Modo Headless e Parâmetros de Linha de Comando

Para testes automatizados, servidores locais sem monitor ou desenvolvimento, é possível usar as opções headless e porta customizada:

### Iniciar sem Abrir Navegador (Headless)
```sh
./iniciar.sh --headless
# ou especificando porta alternativa:
./iniciar.sh --headless --port 8990
```

### Encerrar em Porta Específica
```sh
./parar.sh --port 8990
```

### Supervisor Python Direto
Você também pode invocar diretamente o supervisor padrão da biblioteca padrão do Python:
```sh
python3 scripts/supervisor.py start --headless --port 8765
python3 scripts/supervisor.py status --port 8765
python3 scripts/supervisor.py stop --port 8765
python3 scripts/supervisor.py restart --headless --port 8765
```

### Variáveis de Ambiente Suportadas
- `LOCALCLIP_PORT`: Porta TCP padrão (padrão: `8765`).
- `LOCALCLIP_HOST`: Host de ligação (padrão: `127.0.0.1`).
- `LOCALCLIP_HEADLESS`: Se definido como `1` ou `true`, suprime a abertura de navegadores.
- `LOCALCLIP_RUNTIME_DIR`: Diretório privado para arquivos de estado (`0700`). Padrão: `$XDG_RUNTIME_DIR/localclip` ou `~/.local/state/localclip/run`.
- `LOCALCLIP_LOG_DIR`: Diretório privado para logs (`0700`). Padrão: `~/.local/state/localclip/logs`.

---

## 5. Mecanismo de Propriedade de Processos e Segurança

O supervisor do LocalClip foi desenhado para garantir isolamento e estabilidade no ambiente do usuário:

1. **Serialização via fcntl flock contra Corridas**:
   - Operações de `start` e `stop` adquirem um bloqueio exclusivo `fcntl.flock` no arquivo privado `$LOCALCLIP_RUNTIME_DIR/supervisor_<porta>.lock` (permissão `0600`).
   - Cliques duplos acidentais ou invocações concorrentes são serializados, impedindo sobrescrita de arquivos de estado ou inicialização de instâncias conflitantes.
2. **Validação Estrita de Identidade do Processo**:
   - Antes de confiar no estado ou enviar qualquer sinal (`SIGTERM`/`SIGKILL`), o supervisor verifica a identidade completa do processo:
     - `pid` ativo e não-zombie (`state` diferente de `Z` ou `X`).
     - `starttime` exato no `/proc/<pid>/stat` (campo 22) correspondente ao registrado (prevenindo reciclagem de PID pelo kernel).
     - `pgid` e `session` idênticos aos registrados.
     - Diretório `/proc/<pid>/cwd` apontando exatamente para a raiz do repositório.
     - Linha de comando contendo a porta e executáveis esperados (`localclip`/`uvicorn`).
3. **Rastreamento de Descendentes com Proteção contra Reuso de PID**:
   - Descobre recursivamente a árvore de descendentes (`ppid` em `/proc`) incluindo workers, FFmpeg e subprocessos.
   - Captura e valida o par `{pid: starttime}` para cada filho antes de emitir qualquer sinal de encerramento, garantindo que processos reciclados não sejam atingidos.
   - Quando o processo principal é líder de seu grupo (`actual_pgid == pid`), o encerramento abrange o grupo inteiro via `killpg`.
   - Caso o grupo não coincida (`actual_pgid != pid`), o supervisor envia individualmente `SIGTERM` tanto ao processo principal quanto a todos os descendentes verificados, aguardando término gracioso antes de qualquer `SIGKILL`.
4. **Prontidão Determinística (Root 200 + Bootstrap 200)**:
   - A inicialização só é considerada bem-sucedida quando a rota raiz `/` retorna HTTP 200 (garantindo frontend compilado e montado) E a rota `/api/projects` retorna HTTP 200 (garantindo backend FastAPI e banco SQLite prontos). Respostas 503 são tratadas como serviço incompleto.
5. **Proteção de Portas Ocupadas por Terceiros**:
   - Caso a porta já esteja vinculada por outro processo no sistema, o supervisor detecta e encerra a tentativa de início com erro claro, sem interferir nem enviar sinais para processos de terceiros.
6. **Modo Headless e Supressão de Alertas**:
   - As opções `--headless`, `--no-browser` e a variável `LOCALCLIP_HEADLESS=1` suprimem completamente a abertura de navegador e caixas de diálogo/notificações gráficas (`zenity`/`kdialog`/`notify-send`), mesmo em shells não-interativos.
7. **Privacidade e Permissões Restritas**:
   - Diretórios de runtime e logs são criados com modo estrito `0700` (`rwx------`).
   - Arquivos de trava, estado e logs são criados com modo `0600` (`rw-------`). Nenhuma credencial ou segredo é gravado.

# LocalClip — Provedores de IA e Adapters (`PROVIDERS.md`)

Este documento descreve a integração de provedores de Inteligência Artificial, autenticação segura, endpoints oficiais, adapters implementados e limitações técnicas no LocalClip.

---

## 1. Evidências de Pesquisa e Fontes Oficiais Consultadas

**Status:** `IMPLEMENTADO`, `NÃO VALIDADO (integração real pendente de execução)`

Os contratos e endpoints foram implementados com base em documentação oficial pesquisada durante o desenvolvimento:

1. **Anthropic Claude API:**
   - *Ferramenta utilizada:* Consulta via `web_search` aos endpoints de listagem de modelos e autenticação (`GET /v1/models`, header `x-api-key`, header `anthropic-version: 2023-06-01`).
   - *Documentação oficial:*
     - https://docs.anthropic.com/en/api/getting-started
     - https://docs.anthropic.com/en/api/messages
     - https://docs.anthropic.com/en/api/models-list
   - *Autenticação requerida:* Header `x-api-key: <chave>` e `anthropic-version: 2023-06-01`.
2. **OpenAI Chat Completions API:**
   - *Documentação oficial:* https://platform.openai.com/docs/api-reference/chat
   - *Autenticação requerida:* Header `Authorization: Bearer <chave>`.
   - *Formato estruturado:* Parâmetro `response_format: {"type": "json_object"}`, exigindo que o prompt requisite explicitamente um objeto JSON raiz (`{"candidates": [...]}`).
3. **Google Gemini REST API:**
   - *Documentação oficial:* https://ai.google.dev/api/generate-content
   - *Autenticação requerida:* Header `x-goog-api-key: <chave>` (preferido em vez de query parameter na URL para evitar vazamento em logs HTTP).
   - *Formato estruturado:* `generationConfig: {"responseMimeType": "application/json"}`.
4. **FreeDesktop Secret Service Specification:**
   - *Documentação oficial:* https://specifications.freedesktop.org/secret-service-spec/latest/
   - *Implementação:* Comunicação via DBus com backend `keyring.backends.SecretService.Keyring` ou CLI `secret-tool` com entrada estrita via `stdin`.

---

## 2. Princípios de Arquitetura e Modo Local

**Status:** `IMPLEMENTADO`, `NÃO VALIDADO (integração real pendente de execução)`

1. **Arquitetura Local-First:** Toda a análise estrutural de áudio, fala (Whisper local), detecção de cenas e renderização é executada estritamente na máquina local sem dependência de serviços externos.
2. **Sem Fabricação de Dados Semânticos:** Quando nenhum provedor estiver configurado, ou caso todos os provedores elegíveis estejam indisponíveis, o sistema **não inventa nem fabrica notas semânticas** (como atribuir arbitrariamente 50.0). Em vez disso:
   - `understand_request`: Retorna critérios locais estruturados com o campo `mode="local"` e o aviso explicativo em `semantic_limitation`.
   - `evaluate_candidates`: Retorna lista vazia `[]`, instruindo o motor de ranking a calcular a pontuação exclusivamente sobre os sinais observados localmente no vídeo.

---

## 3. Autenticação e Gestão de Segredos via Linux Secret Service

**Status:** `VALIDADO EM SMOKE TEST REAL (Armazenamento e ciclo de vida no Secret Service)`, `NÃO VALIDADO (Chamadas remotas e fallback com credenciais reais de usuário)`

### 3.1 Política de Segurança
- **Proibição de Armazenamento em Texto Claro:** Chaves de API **nunca** são salvas em arquivos `.env`, SQLite ou arquivos de texto no disco.
- **Isolamento de Backend:** O código força estritamente o backend `keyring.backends.SecretService.Keyring`. Não utiliza backends genéricos não verificados que poderiam salvar em texto plano.
- **Fallback CLI via Stdin:** O fallback via utilitário `secret-tool` envia a chave exclusivamente através de `stdin` (`input=clean_key`), prevenindo a gravação de chaves vazias.
- **Erros Explícitos:** Caso o daemon DBus (ex: `ksecretd` ou `gnome-keyring`) esteja inacessível, uma exceção explícita `SecretServiceUnavailableError` é lançada. Falhas de serviço **não** são mascaradas como chaves ausentes.
- **Validação Real de Armazenamento:** O ciclo de vida de credenciais foi validado com sucesso em smoke test real no ambiente Linux (Fedora): gravação de chave aleatória via `save_key(id, uuid)`, recuperação idêntica via `get_key(id)`, exclusão limpa via `delete_key(id)` retornando `True` e confirmação de inexistência subsequente via `get_key(id) == None`. Nenhum segredo foi registrado em logs nem vazado em respostas.
- **Ressalva de Integração com APIs Remotas:** As chamadas de rede autenticadas a provedores remotos (OpenAI, Gemini, Anthropic) e a cascata de fallback em produção permanecem `NÃO VALIDADO`, pois dependem de credenciais e cotas reais fornecidas pelo usuário final.

### 3.2 Funções Públicas do Módulo (`src/localclip/providers.py`)
```python
save_key(provider_id: str, key: str) -> None
get_key(provider_id: str) -> str | None
delete_key(provider_id: str) -> bool
has_key(provider_id: str) -> bool
```

---

## 4. Adapters Implementados

**Status:** `IMPLEMENTADO`, `NÃO VALIDADO (integração real pendente de execução)`

### 4.1 OpenAI (`OpenAIAdapter`)
- **Endpoint Base:** `https://api.openai.com/v1` (configurável).
- **Health Check:** `GET /models` com `Authorization: Bearer <chave>`.
- **Compreensão de Pedido:** `POST /chat/completions` com `response_format: {"type": "json_object"}`.
- **Avaliação em Lote:** `POST /chat/completions` solicitando objeto `{"candidates": [...]}`.
76:   - *Modelos:* Identificador configurável pelo usuário no cadastro do provedor (ex: `gpt-6-luna`, `gpt-6.1-sol`, `gpt-6-astra`, `gpt-5.6-luna`, `gpt-5.6-terra`, `o3-mini`, `gpt-4o`).
77:   - *Listagem Dinâmica (`list_models`):* `GET /models` com `Authorization: Bearer <chave>`. Filtra automaticamente modelos não-conversacionais (embeddings, TTS, Whisper, DALL-E) para exibir modelos de chat/raciocínio (`gpt-6`, `gpt-5.6`, `o1`, `o3-mini`, `gpt-4o`, `gpt-4o-mini`, etc.).
### 4.2 Google Gemini (`GeminiAdapter`)
- **Endpoint Base:** `https://generativelanguage.googleapis.com/v1beta` (configurável).
- **Health Check:** `GET /models` com `x-goog-api-key: <chave>`.
- **Compreensão e Avaliação:** `POST /models/{model}:generateContent` com `generationConfig: {"responseMimeType": "application/json"}`.
- **Modelos:** Identificador configurável pelo usuário (ex: `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.0-flash` conforme suporte ativo na API do Google).
- **Listagem Dinâmica (`list_models`):** `GET /models` com header `x-goog-api-key: <chave>`. Filtra modelos que suportam `supportedGenerationMethods: ["generateContent"]` e normaliza identificadores removendo o prefixo `models/`.
- **Tratamento de Autenticação:** `API_KEY_INVALID` pode vir como HTTP 400; somente esse código explícito é classificado como credencial inválida. Se houver fallback configurado, ele é tentado antes de pausar o job.
### 4.3 Anthropic Claude (`AnthropicAdapter`)
- **Endpoint Base:** `https://api.anthropic.com/v1` (configurável).
- **Health Check:** `GET /models` com headers `x-api-key` e `anthropic-version: 2023-06-01`.
- **Compreensão e Avaliação:** `POST /messages` com prompt de sistema orientando retorno exclusivo em JSON.
- **Modelos:** Identificador configurável pelo usuário (ex: `claude-3-5-haiku-20241022`, `claude-3-7-sonnet-20250219`, `claude-3-5-sonnet-20241022` conforme cota ativa).
- **Listagem Dinâmica (`list_models`):** `GET /models` com `x-api-key` e `anthropic-version: 2023-06-01`. Retorna a lista de modelos ativos na conta.
### 4.4 OpenAI-Compatible (`CompatibleAdapter`)
- **Herança:** Estende `OpenAIAdapter` compartilhando rotinas de validação e comunicação HTTP.
- **Endpoint Base:** Fornecido obrigatoriamente pelo usuário (ex: `http://localhost:11434/v1` para Ollama, `http://localhost:8000/v1` para vLLM ou LM Studio).
- **Autenticação:** Header `Authorization` opcional (omitido se nenhuma chave for fornecida).
- **Modelos:** Identificador configurável pelo usuário (ex: `llama3.2`, `llama3.1`, `qwen2.5`, `mistral`, `deepseek-r1`).
- **Listagem Dinâmica (`list_models`):** Consulta primária em `GET {base_url}/models`. Se o endpoint retornar 404 ou erro (ex: servidor nativo Ollama sem path `/v1`), tenta automaticamente fallback para `GET {host}/api/tags`, extraindo modelos instalados e metadados de parâmetros (ex: 3B, 8B). Não exige chave de API para instâncias locais.
### 4.5 OMP CLI Bridge (`OmpAdapter`)
- **Como funciona:** Executa inferência via CLI `omp` (`omp -p --mode json --model <provedor/modelo> --no-tools --no-session --no-skills --no-rules --no-extensions --no-lsp --no-title`). As credenciais residem e são renovadas exclusivamente pelo OMP no host local; o LocalClip nunca recebe, extrai nem armazena tokens OAuth.
- **Login no Navegador:** Acionado pelo endpoint `POST /api/omp/login`, iniciando `omp login <provider>` com captura segura da URL de autorização loopback local e fechamento limpo de processo no encerramento da aplicação.
- **Provedores OAuth Suportados:** `google-antigravity` (Gemini 3, Claude), `openai-codex` (ChatGPT Plus/Pro), `anthropic`, `github-copilot`, `google-gemini-cli`. (Para Z.AI/GLM, utiliza-se o provedor dedicado `glm` com chave no Secret Service, pois a CLI requer inserção manual de chave de API).
- **Limites de Plano e Cotas:** O login via OMP conecta as contas sob assinatura do usuário, mas está estritamente subordinado às regras e cotas do plano (ex: janelas de 5 horas, cotas semanais, cotas compartilhadas 3p para Claude/GPT no Antigravity, e cotas do ChatGPT Plus). O sistema não faz falsas promessas de acesso irrestrito; em caso de limite excedido (429/quota), aciona fallback sequencial quando houver provedor secundário configurado.
- **Descoberta de Modelos (`list_models`):** Executa `omp models --json`, filtra modelos do tipo chat/raciocínio, anota o status de conta conectada e ordena os modelos com conta autenticada prioritariamente no catálogo.

### 4.6 Catálogo Curado e Descoberta Segura (`src/localclip/providers.py`)
O módulo expõe funções de contrato para a interface:
- `get_curated_catalog() -> Dict[str, List[Dict[str, Any]]]`: Retorna catálogo estático de modelos para `omp`, `openrouter`, `openai`, `gemini`, `anthropic`, `glm` e `compatible`; descoberta remota é opcional.
- `list_provider_models(config: Dict[str, Any]) -> Dict[str, Any]`: Executa a descoberta dinâmica. Busca a chave com segurança no Linux Secret Service (ou configuração temporária para teste); se ausente em provedores de nuvem, retorna o catálogo curado com `source="unauthenticated"`; se houver falha de rede/cota, retorna o catálogo de fallback com `source="curated_fallback"` e a mensagem higienizada (`sanitize_text`); se bem-sucedido, retorna os modelos ativos na conta com `source="api"`. Credenciais nunca são devolvidas na resposta HTTP.
- **Validação Estrita de Endpoints:** Conforme política do backend, qualquer requisição de descoberta customizada valida rigorosamente `base_url` (`validate_endpoint`), exigindo HTTPS para endpoints públicos remotos, proibindo credenciais embutidas e rejeitando query parameters inesperados antes de qualquer invocação do adapter.

## 5. Validação de Schemas e Contratos de Saída

**Status:** `IMPLEMENTADO`, `NÃO VALIDADO (integração real pendente de execução)`

### 5.1 Regras Rígidas de Validação (`_parse_and_validate_evaluations`)
- **Raiz do Payload:** Deve ser um objeto JSON contendo a lista `candidates`.
- **Correspondência Estrita de IDs e Ordenação Canônica:** Todos os IDs retornados pelo provedor devem corresponder exatamente ao conjunto de candidatos solicitados. Os resultados são indexados por ID e retornados rigorosamente na sequência canônica solicitada, eliminando desvios de ordem de LLMs ou corrupção de cache.
- **Dimensões Obrigatórias:** Cada candidato deve conter exatamente as 7 dimensões: `hook`, `flow`, `value`, `narrative`, `emotion`, `shareability`, `context_penalty`.
- **Limites Numéricos:** Cada valor de score deve ser estritamente numérico, finito (`math.isfinite`) e situado no intervalo `[0.0, 100.0]`. Qualquer valor fora da faixa lança `SchemaValidationError`.
- **Campos Textuais Obrigatórios:** Os campos `title`, `summary` e `reason` devem ser strings não-vazias.

### 5.2 Opção de Desativação de Títulos (`auto_title: False`)
Quando `options.get("auto_title")` for falso, o prompt instrui o modelo a retornar títulos neutros (`Corte {id}`) para evitar consumo desnecessário de criatividade enquanto mantém o schema estrito com campos textuais preenchidos.
---

## 6. Política de Fallback Sequencial

**Status:** `IMPLEMENTADO`, `NÃO VALIDADO (integração real pendente de execução)`

O pipeline suporta configuração de dois provedores: `{"primary": config, "fallback": config | None}`.

| Erro Observado | Classificação | Ação de Fallback |
|---|---|---|
| HTTP 429 (Rate Limit / Quota) | `TemporaryProviderError` | Tenta provedor fallback sequencialmente |
| HTTP 500, 502, 503, 504 (Instabilidade) | `TemporaryProviderError` | Tenta provedor fallback sequencialmente |
| Timeout de Rede / Queda de Conexão | `TemporaryProviderError` | Tenta provedor fallback sequencialmente |
| HTTP 401, 403, 402 ou 400 (`API_KEY_INVALID`) | `AuthenticationError` / crédito ou configuração conforme resposta | Tenta fallback distinto se configurado; caso contrário, pausa o job |
| Chave não encontrada no Secret Service | `ProviderKeyNotFoundError` | Tenta fallback distinto se configurado; caso contrário, pausa o job |
| Quebra de Schema JSON pelo Modelo | `SchemaValidationError` | **Falha imediata** sem fallback |

---

## 7. Limitações Conhecidas

**Status:** `PROBLEMAS CONHECIDOS`

1. **Modelos Locais Menores:** Modelos quantizados com menos de 7 bilhões de parâmetros em runtimes compatíveis frequentemente falham na estrita aderência ao schema JSON com 7 dimensões, gerando `SchemaValidationError`.
2. **Latência de Provedores Remotos:** Avaliações em lote dependem da estabilidade da conexão de internet e da carga atual dos servidores dos provedores de nuvem.
3. **Versionamento de Cache:** O cache de IA é versionado (`LOCALCLIP_AI_PIPELINE_VERSION = "1.1.0"`), invalidando automaticamente caches gerados sob semânticas de serialização anteriores.

---

## 8. Pesquisa e Análise de Viabilidade: Autenticação por Conta, OAuth e Integração OMP

**Status:** `ANALISADO E DOCUMENTADO COM FONTES OFICIAIS (Outubro/2026)`

### 8.1 Evidências e Fontes Oficiais Consultadas
1. **Gemini CLI Authentication & Transição Antigravity:**
   - Documentação oficial de autenticação: https://geminicli.com/docs/get-started/authentication/
   - Comunicado oficial no Google Developers Blog: https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli
   - Nota oficial da plataforma: *"Unpaid tier and Google One users: Gemini CLI was replaced by Antigravity CLI on June 18th, 2026."*
   - Sign in with Google pessoal: Usuários com assinatura **Google AI Pro** ou **Google AI Ultra** e usuários individuais do **Gemini Code Assist** possuem acesso autorizado com cotas via login pessoal no CLI oficial (contas Workspace podem exigir vinculação de projeto).
2. **Catálogo Oficial Google Gemini (Atualizado em 01/10/2026):**
   - Catálogo oficial da API: https://ai.google.dev/gemini-api/docs/models
   - Modelos estáveis ativos: `gemini-3.8-flash` (novo estável), `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-2.5-flash`, `gemini-2.5-pro`.
   - Modelos desligados/descontinuados: Família `gemini-1.5` encerrada e família `gemini-2.0` (`gemini-2.0-flash`, `gemini-2.0-flash-lite`) oficialmente desligada (*shut down*).
3. **Catálogo Oficial Anthropic Claude (Consultado em Outubro/2026):**
   - Visão geral de modelos: https://platform.claude.com/docs/en/models/overview
   - Lineup ativo: `claude-fable-5-1`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-4-5-20251001` (alias `claude-haiku-4-5`).
   - Depreciações e encerramentos: Claude 3.5 Sonnet (`claude-3-5-sonnet-20241022`), Claude 3.5 Haiku (`claude-3-5-haiku-20241022`) e Claude 3.7 Sonnet foram descontinuados e retirados em 19 de fevereiro de 2026.
4. **OpenAI Chat Completions e Modelos de Raciocínio:**
   - Referência de API e modelos: https://platform.openai.com/docs/models e https://platform.openai.com/docs/api-reference/chat
   - Modelos de raciocínio (`o1`, `o3`, `o4`): Rejeitam o parâmetro `temperature` (HTTP 400 se enviado valor customizado diferente de default) e requerem `max_completion_tokens`. Modelos chat padrão: `gpt-4o-mini`, `gpt-4o`, `gpt-5-mini`, `gpt-5`.
5. **Arquitetura de Autenticação do OMP (`omp.sh`):**
   - Secrets e autenticação: https://omp.sh/docs/secrets
   - Auth Broker e Gateway: https://github.com/Raudbjorn/omp/blob/main/docs/auth-broker-gateway.md
   - Modelos e resolução: https://github.com/Raudbjorn/omp/blob/main/docs/models.md
   - O OMP implementa OAuth por provedor via loopback local (`anthropic:54545`, `openai-codex:1455`, `google-gemini-cli:8085`, `google-antigravity:51121`). O *Auth Broker* (`omp auth-broker serve`) é opcional e voltado a times/servidores; no modo desktop/CLI padrão o OMP grava credenciais no banco SQLite local (`agent.db`).

### 8.2 Integração Operacional com o OMP
O LocalClip integra operacionalmente o CLI `omp` como adaptador de inferência (`OmpAdapter`) e fluxo de autenticação via navegador:

1. **Delegação de Autenticação Segura:** O LocalClip não extrai nem armazena tokens ou senhas de contas assinadas. Invoca `omp login <provider>`, que sobe o callback loopback local oficial e persiste as credenciais no cofre do próprio OMP.
2. **Informação Clara de Limites e Planos:** A interface e a documentação informam com clareza que o uso via OMP é estritamente subordinado às regras e cotas do plano contratado pelo usuário (janelas de 5h, limites semanais e restrições de cada provedor). Nenhuma promessa de acesso irrestrito ou cota ilimitada é realizada.
3. **Tratamento Preciso de Erros de Login:** Quando um fluxo de login termina sem sucesso, as mensagens de erro retornadas pelo processo (como cancelamento, porta ocupada ou timeout) são capturadas e apresentadas ao usuário, permitindo nova tentativa informada.
4. **Priorização de Modelos Conectados:** Na listagem dinâmica de modelos (`GET /api/providers/omp/models`), modelos pertencentes a contas ativamente logadas no OMP são identificados e exibidos no topo da seleção, facilitando a escolha sem necessidade de digitação manual de identificadores complexos.
5. **Compatibilidade com Fallback Sequencial:** Caso a conta logada no OMP esgote sua cota temporária (HTTP 429 ou `usage_limit_reached`), o erro é mapeado como `RateLimitError` (`TemporaryProviderError`), acionando o provedor fallback configurado no pipeline (ex: API direta com chave no Secret Service).

## OpenRouter, projeto Google e recuperação (2026-10-09)

- **OpenRouter:** adapter dedicado em `providers.py` usa `https://openrouter.ai/api/v1`, autenticação `Authorization: Bearer`, `/key` para testar a chave e `/models` para descobrir IDs (`organização/modelo`). Chat Completions com JSON estruturado segue a abstração comum. API Key permanece no Secret Service; `402` indica crédito insuficiente, `401` autenticação, `403` permissão, `429` rate limit e `5xx` indisponibilidade. Erros de formato `400` não são repetidos enfraquecendo o contrato JSON. Documentação oficial: https://openrouter.ai/docs/api/reference/overview e https://openrouter.ai/docs/api/reference/errors-and-debugging .
- **Gemini via OMP:** a documentação oficial distingue conta individual (normalmente sem projeto Cloud) de Workspace/licença Code Assist/Vertex AI (projeto necessário): https://geminicli.com/docs/get-started/authentication/ . O formulário carrega o ID salvo, aceita somente ID real informado pelo usuário e permite **limpá-lo apagando o campo antes de entrar novamente**; salva apenas esse identificador **não secreto** em `settings.omp_google_cloud_project` e passa `GOOGLE_CLOUD_PROJECT`/`GOOGLE_CLOUD_PROJECT_ID` aos subprocessos OMP de login, detecção e inferência, inclusive no worker após reinício. Se essas variáveis já estiverem definidas externamente no ambiente da aplicação, é necessário removê-las externamente para usar conta sem projeto. Para projeto Workspace, habilite Gemini for Cloud API e permissões IAM apropriadas. OAuth/tokens continuam geridos pelo OMP. Novo consentimento interativo da conta afetada: **NÃO VALIDADO** sem ação do usuário no navegador.
- **Fallback:** tentativas sequenciais no principal e no único fallback distinto; sem ciclo de retorno. Se ambos falham, mantém erro e checkpoint para `POST /api/jobs/{jid}/retry` após corrigir conta ou selecionar outro provider. Testes de respostas simuladas não provam disponibilidade de cotas ou chamadas remotas autenticadas.

# Segurança

## Fronteira local

Servidor vinculado somente a 127.0.0.1. Host permitido local, Origin deve coincidir com Host e mutações requerem X-LocalClip: 1. Não habilitar CORS permissivo, proxy público ou bind 0.0.0.0. CSP restringe recursos à aplicação; sem scripts de CDN. Este não é um serviço multiusuário autenticado: outros processos do mesmo usuário podem acessar loopback.

IDs internos resolvem arquivos; downloads não aceitam paths arbitrários. Upload usa nome fixo source.media e não confia em extensão. Reserva mínima de 512 MiB de disco durante upload. Originais do usuário são preservados. API de exclusão apaga apenas candidato e renders gerados associados.

## Credenciais

Provedores usam autenticação oficialmente documentada; assinaturas ChatGPT/Claude/Gemini não equivalem automaticamente a crédito de API. Sem captura de cookies, scraping de login ou bypass. Chaves não são retornadas pela API, não entram no SQLite, Git nem nos arquivos de configuração. Secret Service deve estar disponível/desbloqueado; sem fallback para texto claro. Consulte PROVIDERS.md para implementação específica.

Endpoints personalizados exigem HTTPS, exceto loopback explícito para servidores locais. Não aceitam credenciais embutidas, query ou fragmento. Usuário precisa confiar no endpoint que receberá sua chave e dados. Não reutilizar uma credencial em outro endpoint sem revisar a configuração.

## Conteúdo não confiável

Transcrição e frames são dados não confiáveis, não instruções para ferramentas. Modelos retornam dados estruturados validados. Não há execução de comandos propostos por IA. Vídeo inteiro não é enviado por padrão; imagens relevantes dependem de autorização explícita. Respostas e caches podem conter conteúdo privado do vídeo e ficam em diretórios privados.

URLs devem ser públicas, com validação de destino inclusive em extração/redirecionamento; não contornar DRM, paywall ou login privado. FFmpeg e bibliotecas de decodificação processam arquivos potencialmente hostis: manter dependências atualizadas e não tratar validação de metadata como sandbox. Não há isolamento por máquina virtual.

## Armazenamento

Umask 077 ao iniciar, diretórios raiz 0700; credenciais fora da árvore de dados. Cache e renders consomem disco; cancelar não implica apagar todas as evidências úteis. Não há criptografia própria dos vídeos ou banco: recomenda-se criptografia do disco do Fedora para proteção em repouso.

## Verificação

Testes de origem, paths, intervalos, fallback e segredos são necessários; situação real em TESTING.md/CURRENT_STATUS.md. O ciclo de vida de armazenamento no Linux Secret Service (gravação com ID e UUID aleatórios, recuperação idêntica e exclusão limpa sem vazamento em logs) foi testado e VALIDADO em smoke real em Linux (Fedora). Conexões remotas autenticadas e sequenciamento de fallback com provedores externos em produção permanecem NÃO VALIDADAS até o fornecimento de credenciais de API ativas por parte do usuário.

## Novas superfícies

O ID opcional de Google Cloud é um identificador não secreto, persistido em SQLite e repassado por variáveis de ambiente **somente aos subprocessos OMP**; nunca são inventados projeto nem credenciais. Login OAuth continua sob controle do OMP, sem captura de tokens pelo LocalClip. OpenRouter usa o mesmo Secret Service dos demais providers; o teste de conexão não retorna API Key. A thumbnail remota, quando disponível via yt-dlp, é obtida sob guarda SSRF da ingestão; conversão e leitura final usam apenas arquivo local do projeto. Nome editável e filename original nunca são usados como path arbitrário em rotas de mídia.

# Decisões

1. **Web local**, escolhido pelo usuário após comparação com Qt e Tauri. UI servida em loopback; evita outro runtime desktop e mantém dados locais.
2. **Python + FastAPI + SQLite + processo worker.** Ecossistema de transcrição/mídia e fila simples persistente. Não usar Redis ou microsserviços sem necessidade.
3. **Python 3.12 isolado.** Versões mais novas do Python no sistema são possíveis, mas ambiente compatível reduz risco de dependências de ML sem wheels. uv.lock fixa resolução instalada.
4. **Um job pesado por vez.** Hardware-alvo: máquinas domésticas com poucos núcleos, RAM limitada e pouco disco livre. CPU é obrigatório; não presumir CUDA em GPUs não-NVIDIA. Aceleração requer teste real.
5. **Timeline temporal absoluta.** Evita misturar tempos relativos de áudio recortado, original e render; remoções internas exigem mapeamento explícito.
6. **IA agrupada e opcional.** Não mandar vídeo inteiro; reutilizar análise local e cache semântico. Ranking local é heurístico e deve aparecer como tal. Não tratar energia como risada ou movimento como jogada reconhecida.
7. **Secret Service explícito.** Nenhuma chave em SQLite/Git; backend seguro, sem armazenamento em texto como fallback.
8. **Autenticação por métodos oficiais.** Nenhum reaproveitamento de cookies de chatbot. Endpoints/modelos configuráveis; suporte de autenticação depende de documentação oficial por provider.
9. **Durações preferenciais múltiplas e contagem automática.** `Auto` exclusivo; aceitar qualquer faixa manual escolhida sem truncar a fala. Não limitar artificialmente a 20 nem preencher resultados ruins; score mínimo e deduplicação temporal/lexical após ranking. Lotes remotos são delimitados para conter custo.
10. **Edição não destrutiva.** Preservar original; revisões invalidam renders. Não remover silêncios automaticamente sem pedido do usuário.
11. **Evidências separadas.** Testes de contrato, smoke sintético, chamada real autenticada e avaliação qualitativa não são equivalentes. Registrar NÃO VALIDADO quando faltar a evidência apropriada.
12. **Retomada explícita no mesmo job.** Checkpoint da timeline no cache antes de chamar IA; falha de provider preserva artefatos e resultados publicados anteriores. Retry reconsulta configuração atual de providers sem baixar/transcrever novamente.
13. **Identidade separada de arquivo.** `display_name` é fonte editável de UI; `original_filename` e `source_title` registram a origem sem renomear vídeo físico. Migração aditiva preserva projetos antigos.
14. **Reframe/legendas obrigatórios na geração.** Interface não oferece desativação; backend normaliza configs legadas. Preferências de estilo e enquadramento manual no editor continuam.
15. **Integração OMP/OpenRouter sem contornar autenticação.** Projeto Cloud informado pelo usuário quando exigido pela conta e persistido como ID não secreto; API keys OpenRouter permanecem no Secret Service. Fallback sequencial, nunca ciclo de provedores.

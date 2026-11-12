# IA local: RX 6600 (8 GB) ou CPU

O SearchJob conversa com qualquer servidor compatível com a API da OpenAI
(`/v1/chat/completions`). Não há custo por uso e nenhum dado sai da sua rede.

## Qual modelo usar

| Modelo | Tamanho (Q4) | Onde roda bem | Observação |
|---|---|---|---|
| Qwen2.5 7B Instruct | ~4,7 GB | RX 6600 / CPU com 10 GB de RAM | melhor custo-benefício em português |
| Qwen3 8B | ~5 GB | RX 6600 | o SearchJob remove o bloco `<think>` automaticamente |
| Llama 3.1 8B Instruct | ~4,9 GB | RX 6600 | boa alternativa |
| Qwen2.5 3B Instruct | ~2 GB | CPU modesta | mais rápido, um pouco menos preciso |

Com 8 GB de VRAM, modelos de 7B–8B quantizados em **Q4_K_M** cabem inteiros na placa.

## Opção 1: RX 6600 no Windows com LM Studio (recomendado)

O suporte da AMD (ROCm) no Windows é limitado para a RX 6600, mas o **backend Vulkan**
funciona bem nela.

1. Instale o [LM Studio](https://lmstudio.ai).
2. Em *Settings → Runtime*, selecione o runtime **Vulkan** (llama.cpp).
3. Baixe `Qwen2.5 7B Instruct` em `Q4_K_M` e carregue com **GPU offload no máximo**.
4. Na aba *Developer*, inicie o servidor, marque **Serve on Local Network** e anote a porta
   (padrão `1234`).
5. No `.env` do servidor:
   ```env
   SJ_LLM_BASE_URL=http://IP-DO-SEU-PC:1234/v1
   SJ_LLM_MODEL=qwen2.5-7b-instruct
   ```
   O nome exato do modelo aparece em `http://IP-DO-SEU-PC:1234/v1/models`.
6. Libere a porta 1234 no Firewall do Windows apenas para a rede local.

Alternativa sem interface: os binários do **llama.cpp com Vulkan**
(`llama-server -m modelo.gguf -ngl 99 --host 0.0.0.0 --port 1234`).

## Opção 2: CPU do servidor com Ollama

Já vem no `docker-compose.yml` (perfil `ollama`). Em CPU, cada vaga leva de alguns
segundos a cerca de um minuto, dependendo do processador. Isso é tranquilo porque a
análise roda em lote, em segundo plano.

```bash
docker compose --profile ollama up -d
docker exec -it searchjob-ollama ollama pull qwen2.5:7b-instruct
```

## Testar a conexão

Na página de opções da extensão, clique em **Testar conexão**. O teste mostra se a IA está
online e qual modelo está em uso. Pelo terminal:

```bash
curl -H "X-API-Key: SUA_CHAVE" http://IP-DO-LXC:8000/api/llm/status
```

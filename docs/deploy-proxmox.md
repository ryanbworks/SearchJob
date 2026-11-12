# Deploy no Proxmox (LXC + Docker)

O servidor roda 24h num container leve no Proxmox. A IA pode ficar:

- **no próprio servidor, na CPU**, com Ollama: sempre disponível, mais lenta. Como a análise
  roda em lote ao longo do dia, a velocidade não atrapalha;
- **no PC com a RX 6600**, com LM Studio: bem mais rápida, mas só funciona com o PC ligado.
  Quando ele está desligado, as vagas ficam "pendentes" e são analisadas depois.

```
┌──────────── Proxmox ─────────────┐        ┌──────── PC (RX 6600) ────────┐
│ LXC "searchjob" (Debian 12)      │        │ LM Studio (Vulkan)  :1234    │
│  ├─ searchjob  (API + agendador) │◀──────▶│ (opcional)                   │
│  └─ ollama     (IA na CPU, opc.) │  rede  │ Firefox + extensão SearchJob │
└──────────────────────────────────┘ local  └──────────────────────────────┘
```

## 1. Criar o container LXC

No shell do Proxmox (ou pela interface web, em *Create CT*):

```bash
pveam update
pveam download local debian-12-standard_12.7-1_amd64.tar.zst   # confira o nome com: pveam available | grep debian-12

pct create 120 local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst \
  --hostname searchjob \
  --cores 4 --memory 8192 --swap 1024 \
  --rootfs local-lvm:20 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --unprivileged 1 --features nesting=1,keyctl=1 \
  --onboot 1
pct start 120
pct enter 120
```

Recursos sugeridos:

| Cenário | vCPU | RAM | Disco |
|---|---|---|---|
| Só o SearchJob (IA no PC) | 1–2 | 1 GB | 8 GB |
| SearchJob + Ollama com modelo 3B | 4 | 6 GB | 15 GB |
| SearchJob + Ollama com modelo 7B | 4–6 | 10 GB | 20 GB |

> `nesting=1` é obrigatório para rodar Docker dentro de LXC. Recomendo reservar um IP fixo
> para o container no seu roteador, porque a extensão usa esse endereço.

## 2. Instalar o Docker

Dentro do container:

```bash
apt update && apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sh
docker --version && docker compose version
```

## 3. Baixar e configurar o SearchJob

```bash
git clone https://github.com/ryanbworks/SearchJob.git /opt/searchjob
cd /opt/searchjob/server

cp .env.example .env
nano .env                       # defina SJ_API_KEY e a opção de IA

cp data/profile.example.md data/profile.md
nano data/profile.md            # escreva seu perfil/currículo em texto

chown -R 1000:1000 data         # o container roda como usuário sem privilégios (uid 1000)
```

## 4. Subir

**Opção A: IA na CPU do servidor (Ollama)**

```bash
docker compose --profile ollama up -d --build
docker exec -it searchjob-ollama ollama pull qwen2.5:7b-instruct   # ou qwen2.5:3b-instruct, mais leve
```

**Opção B: IA no PC com a RX 6600**: veja [ia-local.md](ia-local.md) e então:

```bash
docker compose up -d --build
```

Para conferir:

```bash
docker compose ps
docker compose logs -f searchjob
curl http://localhost:8000/health
```

A documentação interativa da API fica em `http://IP-DO-LXC:8000/docs`, e o relatório em
`http://IP-DO-LXC:8000/report?key=SUA_CHAVE`.

## 5. Primeira coleta manual

```bash
docker compose exec searchjob searchjob cycle
```

Depois disso o agendador coleta a cada `SJ_COLLECT_EVERY_HOURS` e gera o relatório às
`SJ_REPORT_HOUR` horas.

## Atualizar

```bash
cd /opt/searchjob && git pull
cd server && docker compose up -d --build
```

## Backup

Todos os dados ficam em `server/data/` (banco SQLite, perfil e relatórios). Inclua o LXC nos
backups agendados do Proxmox (*Datacenter → Backup*) ou copie a pasta.

## Segurança

- **Não exponha a porta 8000 para a internet.** Para acessar de fora de casa, use uma VPN
  como Tailscale ou WireGuard.
- Use uma `SJ_API_KEY` longa e aleatória.
- O container roda sem root e o LXC é *unprivileged*.

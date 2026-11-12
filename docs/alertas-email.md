# Alertas de vaga por e-mail

A Gupy é só uma parte do mercado. LinkedIn, Indeed, InfoJobs e Catho mandam **alertas de
vaga por e-mail**. O SearchJob lê esses e-mails e transforma cada vaga num item do banco,
que passa pelos mesmos filtros, pela análise da IA e aparece no painel.

A mesma leitura reconhece **respostas das empresas**:

| E-mail contém | Status da candidatura vira |
|---|---|
| "entrevista", "agendar", "próxima etapa", "teste técnico"… | Entrevista |
| "infelizmente", "não seguiremos", "outro candidato"… | Recusado |

O e-mail é associado à vaga pelo nome da empresa (no remetente, assunto ou texto). Só
candidaturas marcadas como **Candidatado** ou **Entrevista** são atualizadas, e o status
nunca anda para trás. Cada mudança fica registrada nas notas da vaga.

> A caixa é aberta **somente leitura**: nenhum e-mail é apagado, movido ou marcado como lido.

## 1. Crie um e-mail só para vagas (recomendado: Gmail)

Um endereço separado mantém sua caixa pessoal fora do sistema e facilita usar o mesmo
e-mail em todos os sites de vagas.

1. Crie a conta Gmail.
2. Ative a **verificação em duas etapas**: Conta Google → Segurança.
3. Gere uma **senha de app** em <https://myaccount.google.com/apppasswords> (nome: "SearchJob").
4. Use essa senha de 16 letras no `.env`, nunca a senha normal da conta.

> Outlook/Hotmail não aceitam mais senha simples via IMAP (exigem OAuth), por isso não são
> suportados por enquanto.

## 2. Configure o servidor

No `server/.env`:

```env
SJ_IMAP_HOST=imap.gmail.com
SJ_IMAP_USER=seu.email.de.vagas@gmail.com
SJ_IMAP_PASSWORD=abcdabcdabcdabcd
SJ_IMAP_DAYS=7
```

Reinicie (`docker compose up -d`) e teste na hora:

```bash
docker compose exec searchjob searchjob email
```

Depois disso, a leitura roda junto com cada coleta automática.

## 3. Crie os alertas nos sites

Use **o mesmo e-mail de vagas** em cada site e busque termos como "suporte técnico",
"help desk", "service desk" e "técnico de informática", na sua cidade e em "remoto".

- **LinkedIn**: pesquise a vaga → ative **"Alerta de vaga"** → em *Preferências → Alertas
  de vaga*, escolha receber **por e-mail, diariamente**.
- **Indeed**: pesquise → **"Receber novas vagas por e-mail"**.
- **InfoJobs**: pesquise → **"Criar alerta"**.
- **Catho**: pesquise → **"Receber vagas por e-mail"**.

> Dica: candidate-se pela Gupy e por sites de empresas usando também esse e-mail. Assim as
> respostas chegam nele e o funil do painel se atualiza sozinho.

## Limitações

- Alertas trazem só título, empresa e local. A IA dá uma nota mais conservadora para eles;
  abra a vaga antes de se candidatar.
- O reconhecimento de respostas usa palavras-chave. Confira as notas da vaga no painel e
  corrija o status na tabela se precisar.

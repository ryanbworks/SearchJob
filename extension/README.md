# SearchJob Autofill (Firefox)

Extensão que preenche formulários de candidatura com o seu perfil e usa a IA local do
servidor SearchJob para sugerir respostas a perguntas abertas.

## Instalar para uso pessoal

**Modo temporário (desenvolvimento):**
1. Abra `about:debugging#/runtime/this-firefox` no Firefox.
2. Clique em **Carregar extensão temporária…** e selecione `extension/manifest.json`.
3. A extensão some ao fechar o Firefox. Para uso diário, use a opção abaixo.

**Instalação permanente (assinada, sem publicar na loja):**
1. Crie uma conta de desenvolvedor gratuita em <https://addons.mozilla.org/developers/>.
2. Gere a chave em *Ferramentas → Gerenciar chaves de API*.
3. Rode `npx web-ext sign --channel=unlisted --api-key=... --api-secret=...` nesta pasta.
4. Instale o arquivo `.xpi` gerado (arraste para o Firefox).

## Como usar
1. Abra as **opções** da extensão, preencha o perfil e informe o endereço do servidor
   (ex.: `http://192.168.0.50:8000`) e a chave `SJ_API_KEY`. Clique em **Salvar** e
   aceite a permissão de acesso ao servidor.
2. Na página de candidatura, clique no ícone e em **Preencher formulário**.
   - Verde: campo preenchido com o perfil.
   - Tracejado laranja: pergunta aberta. Use **Responder com IA** no popup.
3. Revise tudo, envie a candidatura e clique em **Marcar como candidatado**.

## Privacidade
- O perfil fica em `browser.storage.local`, somente neste navegador.
- O script só roda na aba atual e somente quando você clica (permissão `activeTab`).
- CPF, RG e senhas não são armazenados nem preenchidos.
- Nada é enviado automaticamente: o botão de envio é sempre seu.

## Desenvolvimento
```bash
npm install
npm test        # testes do reconhecimento de campos (node:test)
npm run lint    # validação com web-ext
npm start       # abre um Firefox de teste com a extensão
```

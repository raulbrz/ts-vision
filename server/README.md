# ts-vision backend

Backend Python que recebe os arquivos enviados pela interface em `web/` e, numa única
chamada, manda as imagens direto para um LLM multimodal via OpenRouter, que já devolve o
CSV estruturado.

## Setup

1. Crie um ambiente virtual e instale as dependências:

   ```bash
   cd server
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. Copie `.env.example` para `.env` e preencha:

   ```bash
   cp .env.example .env
   ```

   - `OPENROUTER_API_KEY`: chave gerada em openrouter.ai/keys.
   - `OPENROUTER_MODEL`: modelo a usar (padrão `google/gemma-4-26b-a4b-it:free`). Precisa
     ser um modelo com suporte a **entrada multimodal (imagem)** listado em
     openrouter.ai/models — o backend manda as páginas da timesheet como imagens, não
     como texto.
   - `APP_USERNAME` / `APP_PASSWORD`: a conta raiz do site, em texto puro no `.env` (que é
     gitignorado). Contas adicionais são criadas na tela `/register` e ficam no SQLite
     `server/users.db` (também gitignorado), com senha em hash scrypt.
   - `AUTH_SECRET`: segredo usado para assinar o token de sessão. Se ficar vazio, o
     servidor gera um a cada start e todas as sessões caem no restart (inclusive nos
     reloads do `debug=True`). Gere um com
     `python3 -c "import secrets; print(secrets.token_hex(32))"`.
   - `AUTH_TOKEN_TTL_HOURS`: validade do token de sessão em horas (padrão `12`).
   - `REGISTRATION_SECRET`: segredo pedido na tela `/register` para autorizar a criação de
     conta. Se vazio, vale o `AUTH_SECRET` — por isso o registro só funciona com um
     `AUTH_SECRET` fixo no `.env` (com segredo efêmero, `/api/register` responde 503).
   - `AUTH_FAILURE_DELAY_SECONDS`, `AUTH_MAX_ATTEMPTS`, `AUTH_BLOCK_SECONDS`,
     `AUTH_MAX_BLOCK_SECONDS`, `AUTH_ATTEMPT_WINDOW_SECONDS`: freio de força bruta das rotas
     de login/registro (padrões: 1s de atraso por falha; a partir da 5ª falha do mesmo IP na
     janela de 15min, bloqueio de 30s dobrando a cada falha até 15min). Um login/registro
     bem-sucedido zera o contador daquele IP.

3. Rode o servidor:

   ```bash
   python app.py
   ```

   O servidor sobe em `http://localhost:5000`.

## Endpoints

- `POST /api/login` — recebe `{"usuario", "senha"}` em JSON e devolve
  `{"token", "usuario", "expira_em"}`. 401 se as credenciais não baterem. Aceita tanto a
  conta raiz do `.env` quanto usuários do `users.db`.
- `POST /api/register` — recebe `{"usuario", "senha", "segredo"}`; cria o usuário e já
  devolve um token (201). 403 se o segredo não bater, 409 se o nome já existir, 400 para
  usuário/senha fora das regras (usuário: 3–32 caracteres em `[A-Za-z0-9._-]`; senha:
  mínimo 8), 503 se o registro estiver indisponível por falta de `AUTH_SECRET`.

`/api/login` e `/api/register` respondem 429 com header `Retry-After` quando o IP passa do
limite de tentativas falhas (senha errada no login, segredo errado no registro). Os dois
contadores são independentes, e erros de validação (400/409) não contam como tentativa.
- `GET /api/session` — revalida o token do header `Authorization: Bearer <token>`;
  devolve `{"usuario"}` ou 401.
- `POST /api/ocr` — exige o mesmo header `Authorization`; sem token válido responde 401
  antes de tocar no OpenRouter.

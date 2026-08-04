# ts-vision backend

Backend Python que recebe os arquivos enviados pela interface em `web/`, extrai texto
com o Google Cloud Vision e estrutura o resultado em CSV usando um LLM via OpenRouter.

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

   - `GOOGLE_APPLICATION_CREDENTIALS`: caminho para o JSON de uma service account do
     Google Cloud com a API **Cloud Vision** habilitada no projeto
     (console.cloud.google.com → APIs & Services → Library → Cloud Vision API → Enable;
     depois IAM & Admin → Service Accounts → Create → Keys → Create key → JSON).
   - `OPENROUTER_API_KEY`: chave gerada em openrouter.ai/keys.
   - `OPENROUTER_MODEL`: modelo a usar (padrão `openai/gpt-4o-mini`; qualquer modelo
     listado em openrouter.ai/models funciona, desde que suporte instruções longas).

3. Rode o servidor:

   ```bash
   python app.py
   ```

   O servidor sobe em `http://localhost:5000`.

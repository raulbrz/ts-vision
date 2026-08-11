# ts-vision

Extrai dados de folhas de ponto manuscritas ("GOLD TIGERS SERVICES TIMESHEETS", em PDF ou imagem) para
uma tabela CSV, mandando as imagens direto para um LLM multimodal (via OpenRouter) que já aplica as
regras de conversão do prompt em [`prompt-to-OCR`](./prompt-to-OCR) e devolve o CSV estruturado.

## Estrutura

- `web/` — interface de upload (HTML/CSS/JS puro, sem build); `web/register/` é a tela de criação de
  conta, servida como `/register`.
- `server/` — backend Python (Flask) que chama o LLM multimodal via OpenRouter. Veja
  [`server/README.md`](./server/README.md) para configurar a credencial (OpenRouter).
- `prompt-to-OCR` — prompt que define o schema do CSV e as regras de extração; usado em tempo de
  execução pelo backend, não é só documentação.
- `docs/superpowers/` — specs e planos de implementação de cada feature.
- `BACKLOG.md` — itens de melhoria conhecidos, em ordem de prioridade.
- `docker-compose.yml`, `server/Dockerfile`, `web/Dockerfile`, `deploy/nginx.conf` — deploy em VPS via
  Docker (ver seção [Deploy](#deploy) abaixo).

## Como rodar

```bash
# Terminal 1 — backend
cd server
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # preencha com suas credenciais reais
python app.py           # http://localhost:5000

# Terminal 2 — frontend
cd web
python3 -m http.server 8000   # http://localhost:8000
```

Abra `http://localhost:8000` e entre com o usuário e a senha definidos em `server/.env`
(`APP_USERNAME` / `APP_PASSWORD`) — a tela de upload só aparece depois do login, e o backend recusa
`/api/ocr` sem sessão válida. Para criar outras contas, use `http://localhost:8000/register`: além do
usuário e da senha novos, a tela pede o segredo de registro do servidor (o `AUTH_SECRET` do
`server/.env`, ou o `REGISTRATION_SECRET` se você definir um). As contas criadas ficam em
`server/users.db` com a senha em hash scrypt.

Depois de entrar, selecione os arquivos, informe o intervalo de datas e clique em "Enviar
para OCR". O andamento (preparo de cada arquivo, análise pela IA, conclusão ou erro) aparece em
tempo real na tela; "Cancelar" interrompe um envio em andamento. Ao concluir, "Baixar CSV" exporta o
resultado como arquivo `.csv`, "Copiar CSV" copia o mesmo conteúdo para a área de transferência e
"Limpar resultado" reseta a tabela para um novo envio.

## Deploy

Para rodar numa VPS via Docker: clone o repositório na máquina e preencha `server/.env` (copie de
`server/.env.example`, mesma credencial do setup local — só `OPENROUTER_API_KEY`/`OPENROUTER_MODEL`
e as variáveis de auth, nenhum arquivo de credencial adicional). Recomendado fixar `AUTH_SECRET` no
`.env` (não deixar em branco) — isso mantém as sessões válidas entre restarts do container e evita
divergência entre processos do backend. Depois:

```bash
docker compose up -d --build
```

Isso sobe dois containers: `server` (Flask + gunicorn, sem porta publicada — só acessível pelo `web`)
e `web` (nginx, configurado por `deploy/nginx.conf`, servindo `web/` e fazendo proxy de `/api/` para
o `server`). Nenhuma porta é publicada no host: `web` entra também na rede Docker externa
`nginx_proxy-network` (o Nginx Proxy Manager já rodando na VPS), e é lá que se cria o proxy host
apontando pro container `ts-vision-web`, porta `80` — sem custom location, o roteamento de `/api` já
é resolvido dentro do próprio container `web`. `server/users.db` fica num volume Docker nomeado,
então sobrevive a `docker compose up -d --build` (rebuild + recreate); só é perdido com
`docker compose down -v`.

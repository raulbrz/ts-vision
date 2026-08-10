# ts-vision

Extrai dados de folhas de ponto manuscritas ("GOLD TIGERS SERVICES TIMESHEETS", em PDF ou imagem) para
uma tabela CSV, usando OCR (Google Cloud Vision) seguido de um LLM (via OpenRouter) que aplica as
regras de conversão do prompt em [`prompt-to-OCR`](./prompt-to-OCR).

## Estrutura

- `web/` — interface de upload (HTML/CSS/JS puro, sem build); `web/register/` é a tela de criação de
  conta, servida como `/register`.
- `server/` — backend Python (Flask) que orquestra OCR + LLM. Veja [`server/README.md`](./server/README.md)
  para configurar as credenciais (Google Cloud Vision e OpenRouter).
- `prompt-to-OCR` — prompt que define o schema do CSV e as regras de extração; usado em tempo de
  execução pelo backend, não é só documentação.
- `docs/superpowers/` — specs e planos de implementação de cada feature.
- `BACKLOG.md` — itens de melhoria conhecidos, em ordem de prioridade.

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
para OCR". O andamento (OCR de cada arquivo, ajuste do texto pela IA, conclusão ou erro) aparece em
tempo real na tela; "Cancelar" interrompe um envio em andamento. Ao concluir, "Baixar CSV" exporta o
resultado como arquivo `.csv` e "Limpar resultado" reseta a tabela para um novo envio.

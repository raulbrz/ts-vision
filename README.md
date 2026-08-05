# ts-vision

Extrai dados de folhas de ponto manuscritas ("GOLD TIGERS SERVICES TIMESHEETS", em PDF ou imagem) para
uma tabela CSV, usando OCR (Google Cloud Vision) seguido de um LLM (via OpenRouter) que aplica as
regras de conversão do prompt em [`prompt-to-OCR`](./prompt-to-OCR).

## Estrutura

- `web/` — interface de upload (HTML/CSS/JS puro, sem build).
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

Abra `http://localhost:8000`, selecione os arquivos, informe o intervalo de datas e clique em "Enviar
para OCR". O andamento (OCR de cada arquivo, ajuste do texto pela IA, conclusão ou erro) aparece em
tempo real na tela, e o botão "Limpar resultado" reseta a tabela para um novo envio.

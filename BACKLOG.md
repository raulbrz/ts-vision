# BACKLOG.md

Itens de melhoria identificados no pipeline de OCR (`server/` + `web/`), em ordem de prioridade.
Segurança/produção foi propositalmente deixada por último — não é o foco agora.

## Alta prioridade — corretude do resultado

Estes afetam diretamente a qualidade dos dados extraídos, que é o propósito da ferramenta.

- [ ] **PDFs com mais de 5 páginas são truncados silenciosamente.** `ocr.py` usa
  `batch_annotate_files` (API síncrona do Vision), que processa no máximo 5 páginas por arquivo. Hoje
  o restante é descartado sem log nem aviso ao usuário. Precisa detectar o caso e reportar (evento
  `ocr_falhou` parcial, ou nota avisando que só as N primeiras páginas foram lidas).
- [ ] **Parsing de CSV no frontend é frágil.** `renderResultsTable` (`web/app.js`) faz
  `line.split(',')` — quebra se algum campo tiver vírgula (nome com vírgula, campo entre aspas).
  Trocar por um parser de CSV mínimo que respeite aspas.
- [ ] **Parsing da resposta do LLM é acoplado a texto livre.** `_split_csv_and_notes` (`server/llm.py`)
  identifica o bloco CSV e as notas por regex sobre o texto do modelo. Qualquer variação na resposta
  (ordem de seções, formatação do header "Pontos de atenção") quebra o parser sem erro explícito.
  Considerar pedir uma saída estruturada (ex.: JSON) ao modelo em vez de texto livre.
- [x] **Sem retry/backoff na chamada ao OpenRouter.** `llm.structure` faz uma única tentativa; um
  429/5xx transitório vira erro direto para o usuário em vez de nova tentativa. Resolvido: chamada
  extraída para `llm._post_with_retry`, que tenta até 3 vezes com backoff exponencial + jitter
  (respeitando `Retry-After` quando presente) em respostas 429/5xx ou erros de rede; erros não
  transitórios (400/401/etc.) continuam propagando imediatamente.
- [ ] **Sem validação de tipo/tamanho real de arquivo no backend.** O filtro de extensão
  (`.pdf/.png/.jpg/.jpeg`) só existe no frontend; um arquivo malformado ou renomeado chega ao
  `ocr.extract_text` e derruba com uma exceção genérica.

## Média prioridade — usabilidade

- [x] **Não há como exportar o CSV gerado.** O resultado só é renderizado como tabela HTML; falta um
  botão para baixar o `.csv`. Resolvido: botão "Baixar CSV" no cabeçalho do resultado (`web/index.html`)
  gera um `Blob` com o texto CSV recebido no evento `concluido` (guardado em `lastCsvText`,
  `web/app.js`) e dispara o download via link temporário, nomeado com as datas inicial/final.
- [x] **Sem `AbortController` no fetch de streaming.** Uma vez submetido, o usuário não consegue
  cancelar um processamento em andamento. Resolvido: `activeController` guarda o `AbortController` do
  envio atual (`web/app.js`), `#cancel-button` chama `.abort()`, e o `AbortError` resultante é
  capturado e exibido como um evento `cancelado` na timeline (estágio só do frontend, o backend nunca
  o emite).
- [ ] **`OCR_ENDPOINT` hardcoded para `localhost:5000`** em `web/app.js`. Impede deploy do frontend
  sem editar o código-fonte; precisa virar configurável (variável de build, arquivo de config, etc.).
- [ ] **Sem validação de formato das datas.** O backend só checa que `data_inicial`/`data_final` não
  estão vazias, não que são datas válidas/coerentes entre si.

## Baixa prioridade — qualidade de código e performance

- [ ] **Sem testes automatizados.** `_split_csv_and_notes` é uma função pura e crítica (acopla o
  parsing ao formato de saída do `prompt-to-OCR`) — é a candidata mais valiosa para testes unitários.
- [ ] **OCR processado sequencialmente.** O loop em `app.py` processa um arquivo por vez; para envios
  com muitos arquivos, paralelizar as chamadas ao Vision reduziria o tempo total.

## Adiado — produção/segurança

Não é prioridade agora, mas fica registrado para quando o app for exposto além de uso local:

- [ ] `CORS(app)` está aberto para qualquer origem, sem autenticação.
- [ ] `debug=True` em `app.run` (deve ser desligado fora do ambiente de desenvolvimento).

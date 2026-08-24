# BACKLOG.md

Itens de melhoria identificados no pipeline de OCR (`server/` + `web/`), em ordem de prioridade.
Segurança/produção foi propositalmente deixada por último — não é o foco agora.

## Alta prioridade — corretude do resultado

Estes afetam diretamente a qualidade dos dados extraídos, que é o propósito da ferramenta.

- [x] **PDFs com mais de 5 páginas são truncados silenciosamente.** Resolvido por construção: o
  pipeline trocou o Cloud Vision (API síncrona limitada a 5 páginas por arquivo) por um LLM
  multimodal via OpenRouter, com `attachments.py` renderizando todas as páginas do PDF via PyMuPDF
  sem limite algum.
- [ ] **Uploads de PDFs grandes podem estourar o payload da chamada ao LLM.** `attachments.py`
  renderiza todas as páginas em PNG a 200 DPI sem nenhum teto de tamanho/páginas, e `llm.py` manda
  todas numa única requisição a OpenRouter. Com um modelo pequeno/gratuito (ex.:
  `google/gemma-4-26b-a4b-it:free`, o default do `config.py`), um PDF de ~18 páginas/10MB já falhou em
  produção (2026-08-18) com um erro opaco do backend do modelo (`"Error in input stream"` — confirmado
  não existir em nenhum código deste repo nem em suas dependências, então vem de fora). Contornado
  trocando `OPENROUTER_MODEL` em produção para `google/gemini-2.5-flash-lite` (pago, contexto maior),
  sem mudança de código. Se o problema voltar (modelo gratuito, ou um PDF ainda maior), a mitigação já
  desenhada e testada é dividir as páginas em lotes menores por chamada ao LLM
  (`_flatten_attachments` + chunking em `llm.structure`, mesclando CSV e notas das várias respostas ao
  final, preservando o número de página original de cada imagem) — não está implementada no repo hoje,
  foi descartada quando a troca de modelo já resolveu o caso concreto.
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
  `attachments.to_image_parts` e derruba com uma exceção genérica.

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
- [x] **OCR processado sequencialmente.** Deixou de ser um gargalo: o preparo de cada arquivo
  (`attachments.to_image_parts`) é local (renderização de PDF via PyMuPDF, sem chamada de rede) e o
  processamento em si virou uma única chamada ao LLM para todos os arquivos, não mais uma chamada de
  OCR por arquivo.
- [ ] **Sem cache-busting nos arquivos estáticos do `web/`.** `app.js`/`style.css`/`index.html` são
  referenciados sem hash/versão no nome. Em produção, atrás do Cloudflare, isso significa até 4h
  (`cache-control: max-age=14400` observado) de cache no edge que sobrevive a um redeploy do container
  `web` inteiro — confirmado em 2026-08-24 (`cf-cache-status: HIT` com `last-modified` anterior ao
  deploy), só resolvido com "Purge Cache" manual no Cloudflare (ver `CLAUDE.md` § Deployment). Fix
  duradouro: nome de arquivo com hash de conteúdo ou querystring versionada (ex.: `app.js?v=<git-sha>`)
  atualizada a cada deploy, ou uma Cache Rule no Cloudflare tratando esses arquivos como no-cache.

## Adiado — produção/segurança

Não é prioridade agora, mas fica registrado para quando o app for exposto além de uso local:

- [x] **Sem autenticação nenhuma.** Resolvido: login simples de usuário/senha na frente do site.
  `server/auth.py` emite um token assinado com HMAC-SHA256 (`AUTH_SECRET`), `POST /api/login` e
  `GET /api/session` no `app.py`, e `POST /api/ocr` protegido por `@auth.login_required`; o frontend
  tem uma tela de login (`#login-screen`) e guarda o token em `localStorage`.
- [ ] `CORS(app)` continua aberto para qualquer origem (agora com auth por token, mas sem restrição
  de origem).
- [x] **Sem cadastro de usuários.** Resolvido: tela `/register` (`web/register/`) + `POST /api/register`,
  protegidos por um segredo compartilhado (`REGISTRATION_SECRET`, com fallback para `AUTH_SECRET`). Os
  usuários ficam em `server/users.db` (SQLite, gitignorado) com senha em hash scrypt (`server/users.py`);
  o par `APP_USERNAME`/`APP_PASSWORD` do `.env` continua valendo como conta raiz.
- [ ] **Segredo de registro é o `AUTH_SECRET` por padrão.** A chave que assina os tokens acaba sendo
  digitada num formulário e trafegando na rede; se vazar, dá para forjar token de qualquer usuário.
  Definir um `REGISTRATION_SECRET` separado resolve — hoje isso é opcional, deveria ser o padrão.
- [x] **Sem rate limiting no `/api/login` nem no `/api/register`.** Resolvido: `server/ratelimit.py`
  conta tentativas falhas por IP (contadores separados por rota); cada falha custa
  `AUTH_FAILURE_DELAY_SECONDS` e, a partir da 5ª, o IP leva 429 + `Retry-After` com bloqueio de 30s
  dobrando até 15min. Sucesso zera o contador. Falta cobrir o caso multi-worker: o estado é do
  processo, então com vários workers cada um conta o seu — em produção precisaria de Redis ou similar.
- [ ] **Freio de força bruta usa `request.remote_addr` direto.** Atrás de um proxy reverso isso vira o
  IP do proxy e o bloqueio passa a valer para todo mundo de uma vez; precisa tratar `X-Forwarded-For`
  (com lista de proxies confiáveis) quando o app for exposto.
- [ ] **Não há como listar, remover ou trocar a senha de um usuário.** Só dá para criar; qualquer outra
  operação exige mexer no SQLite na mão. Falta pelo menos um script de administração.
- [ ] **Token fica em `localStorage`.** Sobrevive a XSS mal; com o app exposto, migrar para cookie
  `httpOnly`+`SameSite` seria mais seguro.
- [ ] `debug=True` em `app.run` (deve ser desligado fora do ambiente de desenvolvimento).

# 🤖 RaizitoBot

Bot do Telegram com integração de IA (Google Gemini) que oferece conversação inteligente, gerenciamento de tarefas, busca na web e transcrição de áudio, agora com memória de contexto e acesso a Gmail, Drive, Calendar e Docs via Google Workspace.

## ✨ Funcionalidades

- 💬 **Conversação com IA**: Integração com Google Gemini para respostas inteligentes
- 📝 **Tarefas Inteligentes**: Adicione, liste e complete tarefas com prazo, prioridade, categoria, recorrência e lembretes
- 🔍 **Busca na Web**: Pesquise informações diretamente do Telegram
- 🎙️ **Transcrição de Áudio**: Converta mensagens de voz em texto com Gemini
- 🖼️ **Análise de Imagens**: Envie fotos e receba análises da IA
- 🧠 **Memória de Conversa**: Contexto das últimas interações para respostas mais coerentes
- 🧩 **Memória Pessoal Persistente**: Salve fatos importantes com `/remember` ou mensagens como "lembre que..."
- 🧭 **RAG Local**: Busca semântica em memórias, tarefas, notas e documentos do projeto usando SQLite como banco vetorial
- 🗓️ **Briefing Diário**: Combine agenda, tarefas, memória e RAG com `/today` e resumos automáticos
- 📧 **E-mails Inteligentes**: Liste, resuma e indexe Gmail no RAG sem enviar respostas automaticamente
- 📁 **Drive/Docs Inteligentes**: Indexe arquivos do Drive e resuma Google Docs com RAG
- 📊 **Status do App**: Monitore o status do bot

## 🚀 Deploy em Produção

Para colocar o bot em produção, consulte o **[Guia de Deploy](DEPLOY.md)** completo com instruções para:

- ⭐ **Railway** (recomendado - gratuito e fácil)
- ▲ **Vercel** (webhook serverless)
- 🌐 **Render** (alternativa gratuita)
- 🐳 **Docker** (VPS/servidor próprio)
- ☁️ **Google Cloud Run**
- 🔷 **Heroku**

## 🔑 Configuração das APIs do Google

Para configurar as chaves de API necessárias (Google Search, Gmail, Drive, etc.), consulte o **[Guia de Configuração das APIs](GOOGLE_APIS_SETUP.md)**.


## 🛠️ Desenvolvimento Local

### Pré-requisitos

- Python 3.11+
- FFmpeg (para processamento de áudio)

### Instalação

1. **Clone o repositório**
   ```bash
   git clone https://github.com/TenorioDevfullStack/RaizitoBot.git
   cd RaizitoBot
   ```

2. **Instale as dependências**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure as variáveis de ambiente**
   ```bash
   cp .env.example .env
   ```
   
   Edite o arquivo `.env` com suas credenciais:
   - `TELEGRAM_TOKEN`: Token do [@BotFather](https://t.me/BotFather)
   - `TELEGRAM_WEBHOOK_SECRET`: segredo opcional para proteger o webhook do Telegram
   - `GEMINI_API_KEY`: Key do [Google AI Studio](https://aistudio.google.com/)
   - `GEMINI_MODEL`: Modelo Gemini opcional (padrão: `gemini-2.5-flash`)
   - `GOOGLE_SEARCH_API_KEY` e `GOOGLE_SEARCH_CX`: Chaves do Google Custom Search
   - `GOOGLE_SERVICE_ACCOUNT_FILE`: JSON do service account com acesso a Gmail/Drive/Calendar/Docs
   - `GOOGLE_DELEGATED_USER`: (opcional) usuário a ser impersonado ao usar o service account
   - `GOOGLE_CALENDAR_TIMEZONE`: fuso usado ao criar eventos (padrão: `America/Sao_Paulo`)

4. **Execute o bot**
   ```bash
   python main.py
   ```

### Deploy na Vercel

Na Vercel, o bot roda por webhook em `/api/webhook`. Depois do deploy, configure o webhook do Telegram:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_TOKEN>/setWebhook?url=https://SEU-DOMINIO.vercel.app/api/webhook&secret_token=<TELEGRAM_WEBHOOK_SECRET>"
```

Se não usar `TELEGRAM_WEBHOOK_SECRET`, remova o parâmetro `secret_token`.

## 📋 Comandos Disponíveis

| Comando | Descrição |
|---------|-----------|
| `/start` | Inicia o bot e exibe mensagem de boas-vindas |
| `/help` | Mostra lista de comandos disponíveis |
| `/task <descrição>` | Adiciona uma nova tarefa. Entende `hoje`, `amanhã`, `dd/mm`, horário, `#categoria`, prioridade e recorrência |
| `/list [filtro] [#categoria]` | Lista tarefas. Filtros: `hoje`, `semana`, `atrasadas`, `concluidas`, `todas` |
| `/tasks [filtro] [#categoria]` | Atalho para listar tarefas |
| `/done <id>` | Marca uma tarefa como concluída |
| `/today` | Mostra briefing do dia com agenda, tarefas, prioridades e contexto |
| `/daily on HH:MM` | Ativa resumo diário automático |
| `/daily off` | Desativa resumo diário |
| `/daily status` | Mostra configuração do resumo diário |
| `/reminders status` | Mostra configuração dos avisos de reunião |
| `/reminders minutes <n>` | Define antecedência dos avisos de reunião |
| `/reminders on/off` | Ativa ou desativa avisos de reunião |
| `/event <texto>` | Prepara criação de evento no Calendar, checa conflitos e pede confirmação |
| `/confirm_event <id>` | Confirma e cria um evento pendente no Calendar |
| `/cancel_event <id>` | Cancela um evento pendente |
| `/remember <texto>` | Salva uma memória pessoal persistente |
| `/memory` | Lista as memórias salvas |
| `/memory add <texto>` | Salva uma nova memória |
| `/memory delete <id>` | Apaga uma memória específica |
| `/memory clear` | Apaga todas as suas memórias |
| `/forget <id>` | Apaga uma memória específica |
| `/knowledge` | Mostra status da base semântica local |
| `/knowledge search <consulta>` | Busca memórias, tarefas, notas e docs por significado |
| `/knowledge add <texto>` | Salva uma nota diretamente na base semântica |
| `/knowledge index_docs` | Indexa documentos do projeto na base vetorial |
| `/emails list [query]` | Lista e-mails recentes com ID, prioridade, remetente, assunto, data e trecho |
| `/emails summary [query]` | Resume e-mails recentes com Gemini e indexa no RAG |
| `/emails index [query]` | Indexa e-mails recentes no RAG |
| `/emails search <consulta>` | Busca e-mails indexados por significado |
| `/email_draft <email_id> <instrução>` | Gera rascunho local de resposta, sem enviar |
| `/drafts [pending|archived|all]` | Lista rascunhos locais |
| `/draft_view <id>` | Mostra um rascunho local |
| `/draft_delete <id>` | Arquiva um rascunho local |
| `/search <query>` | Busca informações na web |
| `/gmail [query]` | Lista e-mails recentes (com filtro opcional) |
| `/drive` | Lista arquivos recentes do Drive |
| `/drive list [nome]` | Lista arquivos do Drive com filtro opcional por nome |
| `/drive index [nome]` | Indexa metadados de arquivos do Drive no RAG |
| `/drive search <consulta>` | Busca arquivos do Drive por significado |
| `/calendar` | Mostra próximos eventos |
| `/docs <documento>` | Mostra título e prévia de um Google Docs |
| `/docs summary <documento>` | Resume um Google Docs com Gemini e indexa no RAG |
| `/docs index <documento>` | Indexa o texto completo de um Google Docs no RAG |
| `/app_status` | Verifica o status do bot |

Além dos comandos, você pode:
- 💬 Enviar mensagens de texto para conversar com a IA (com contexto das últimas interações)
- 📝 Criar tarefas em linguagem natural, como `me lembre de pagar boleto amanhã às 9 #casa prioridade:alta`
- 🖼️ Enviar fotos para análise
- 🎙️ Enviar áudios/voice notes para transcrição

### Exemplos de tarefas inteligentes

```text
/task pagar boleto amanhã às 9 #casa prioridade:alta
/task revisar relatório em 3 dias p2 lembrete em 30 minutos
/task enviar resumo toda semana sexta às 16 #trabalho
/list hoje
/list atrasadas
/list semana #trabalho
```

Recorrências simples aceitas: `todo dia`, `semanal`/`toda semana` e `mensal`/`todo mês`.
Os lembretes usam o `job_queue` do python-telegram-bot enquanto o bot estiver rodando em polling.

### RAG local e banco vetorial

O bot mantém uma tabela `knowledge_items` no SQLite com vetores locais gerados por hashing. Essa primeira versão não depende de Chroma, Qdrant ou APIs externas de embedding.

Memórias e tarefas são indexadas automaticamente. Para indexar a documentação do projeto:

```text
/knowledge index_docs
/knowledge search memoria semantica
/knowledge add Preferir respostas curtas quando eu estiver no celular
```

Nas conversas normais, o bot busca itens relevantes nessa base e injeta o contexto recuperado no prompt do Gemini.

### Agenda e briefing diário

```text
/today
/daily on 08:00
/daily status
/reminders minutes 30
/event reunião com Ana amanhã às 10 por 45min local: Sala 2 desc: revisar proposta ana@example.com
/confirm_event 1
```

O bot pede confirmação antes de criar eventos no Calendar. Antes da confirmação, ele tenta detectar conflitos e sugere horários alternativos. Eventos criados entram na base RAG para busca semântica futura. Quando o resumo diário está ativo, o `job_queue` envia o briefing no horário configurado e também avisa sobre reuniões conforme a antecedência configurada.

### E-mails inteligentes

```text
/emails list
/emails summary newer_than:7d
/emails index from:cliente@example.com
/emails search proposta da Loja X
```

`/emails summary` usa o Gemini para resumir os e-mails retornados e destaca possíveis ações. A Fase 4.1 não envia e-mails nem cria rascunhos; ela só lê, resume e indexa informações para busca semântica.

### Rascunhos de e-mail

```text
/emails list from:cliente@example.com
/email_draft 18cafe123 responder educadamente pedindo prazo até sexta
/drafts
/draft_view 1
/draft_delete 1
```

Os rascunhos são salvos apenas no SQLite local e indexados no RAG. Nenhum e-mail é enviado nesta fase.

### Drive e Docs inteligentes

```text
/drive list proposta
/drive index Loja X
/drive search contrato loja
/docs summary 1abcDEFdocumentId
/docs index 1abcDEFdocumentId
```

`/drive index` salva metadados dos arquivos na base RAG. `/docs summary` e `/docs index` leem o conteúdo de Google Docs, geram resumo quando solicitado e salvam trechos no RAG. Esta fase não edita arquivos no Drive ou Docs.

## 🏗️ Estrutura do Projeto

```
RaizitoBot/
├── bot/
│   ├── __init__.py
│   ├── ai_service.py          # Integração com Google Gemini
│   ├── db.py                  # Gerenciamento do banco de dados e memória de conversas
│   ├── external_integration.py # Integrações externas
│   ├── google_services.py     # Integrações Gmail/Drive/Calendar/Docs
│   ├── handlers.py            # Handlers do Telegram
│   └── web_search.py          # Funcionalidade de busca web
├── main.py                    # Arquivo principal
├── requirements.txt           # Dependências Python
├── Dockerfile                 # Container Docker
├── docker-compose.yml         # Configuração Docker Compose
├── Procfile                   # Configuração para Railway/Heroku
├── .env.example               # Template de variáveis de ambiente
├── .gitignore                 # Arquivos ignorados pelo Git
└── DEPLOY.md                  # Guia de deploy em produção
```

## 🔒 Segurança

- ⚠️ **Nunca** commite o arquivo `.env` com suas credenciais
- 🔐 Mantenha suas API keys em segredo
- 🛡️ Use variáveis de ambiente em produção

## 🤝 Contribuindo

Contribuições são bem-vindas! Sinta-se à vontade para:

1. Fazer fork do projeto
2. Criar uma branch para sua feature (`git checkout -b feature/NovaFuncionalidade`)
3. Commit suas mudanças (`git commit -m 'Adiciona nova funcionalidade'`)
4. Push para a branch (`git push origin feature/NovaFuncionalidade`)
5. Abrir um Pull Request

## 📝 Licença

Este projeto é open source e está disponível sob a licença MIT.

## 📧 Contato

Para dúvidas ou sugestões, abra uma issue no GitHub!

---

**Desenvolvido com ❤️ usando Python e Google Gemini**

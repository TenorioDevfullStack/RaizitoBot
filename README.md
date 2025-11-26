# 🤖 RaizitoBot

Bot do Telegram com integração de IA (Google Gemini) que oferece conversação inteligente, gerenciamento de tarefas, busca na web e transcrição de áudio, agora com memória de contexto e acesso a Gmail, Drive, Calendar e Docs via Google Workspace.

## ✨ Funcionalidades

- 💬 **Conversação com IA**: Integração com Google Gemini para respostas inteligentes
- 📝 **Gerenciamento de Tarefas**: Adicione, liste e complete tarefas
- 🔍 **Busca na Web**: Pesquise informações diretamente do Telegram
- 🎙️ **Transcrição de Áudio**: Converta mensagens de voz em texto (Groq Whisper)
- 🖼️ **Análise de Imagens**: Envie fotos e receba análises da IA
- 🧠 **Memória de Conversa**: Contexto das últimas interações para respostas mais coerentes
- 📧 **Integração Google**: Leia e-mails, arquivos do Drive, eventos do Calendar e Docs
- 📊 **Status do App**: Monitore o status do bot

## 🚀 Deploy em Produção

Para colocar o bot em produção, consulte o **[Guia de Deploy](DEPLOY.md)** completo com instruções para:

- ⭐ **Railway** (recomendado - gratuito e fácil)
- 🌐 **Render** (alternativa gratuita)
- 🐳 **Docker** (VPS/servidor próprio)
- ☁️ **Google Cloud Run**
- 🔷 **Heroku**

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
   - `GEMINI_API_KEY`: Key do [Google AI Studio](https://makersuite.google.com/app/apikey)
   - `GROQ_API_KEY`: Key do [Groq Console](https://console.groq.com)
   - `GOOGLE_SEARCH_API_KEY` e `GOOGLE_SEARCH_CX`: Chaves do Google Custom Search
   - `GOOGLE_SERVICE_ACCOUNT_FILE`: JSON do service account com acesso a Gmail/Drive/Calendar/Docs
   - `GOOGLE_DELEGATED_USER`: (opcional) usuário a ser impersonado ao usar o service account

4. **Execute o bot**
   ```bash
   python main.py
   ```

## 📋 Comandos Disponíveis

| Comando | Descrição |
|---------|-----------|
| `/start` | Inicia o bot e exibe mensagem de boas-vindas |
| `/help` | Mostra lista de comandos disponíveis |
| `/task <descrição>` | Adiciona uma nova tarefa |
| `/list` | Lista todas as tarefas pendentes |
| `/done <id>` | Marca uma tarefa como concluída |
| `/search <query>` | Busca informações na web |
| `/gmail [query]` | Lista e-mails recentes (com filtro opcional) |
| `/drive` | Lista arquivos recentes do Drive |
| `/calendar` | Mostra próximos eventos |
| `/docs <documento>` | Mostra título e prévia de um Google Docs |
| `/app_status` | Verifica o status do bot |

Além dos comandos, você pode:
- 💬 Enviar mensagens de texto para conversar com a IA (com contexto das últimas interações)
- 🖼️ Enviar fotos para análise
- 🎙️ Enviar áudios/voice notes para transcrição

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

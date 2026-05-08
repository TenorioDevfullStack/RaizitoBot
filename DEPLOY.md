# 🚀 Guia de Deploy em Produção - RaizitoBot

Este guia apresenta diferentes opções para colocar o RaizitoBot em produção.

## 📋 Pré-requisitos

Antes de fazer o deploy, você precisa:

1. **Token do Telegram Bot**
   - Acesse [@BotFather](https://t.me/BotFather) no Telegram
   - Crie um novo bot com `/newbot`
   - Salve o token fornecido

2. **Google Gemini API Key**
   - Acesse [Google AI Studio](https://makersuite.google.com/app/apikey)
   - Crie uma nova API key

---

## 🎯 Opção 1: Railway (Recomendado - Gratuito)

**Vantagens**: Fácil, gratuito, deploy automático via Git, logs em tempo real

### Passo a Passo

1. **Acesse [Railway.app](https://railway.app)** e faça login com GitHub

2. **Crie um novo projeto**
   - Clique em "New Project"
   - Selecione "Deploy from GitHub repo"
   - Escolha o repositório `TenorioDevfullStack/RaizitoBot`

3. **Configure as variáveis de ambiente**
   - No painel do Railway, vá em "Variables"
   - Adicione as seguintes variáveis:
     ```
     TELEGRAM_TOKEN=seu_token_aqui
     GEMINI_API_KEY=sua_key_aqui
     ```

4. **Deploy automático**
   - O Railway detectará automaticamente o `Procfile`
   - O deploy iniciará automaticamente
   - Aguarde alguns minutos

5. **Verificar logs**
   - Clique em "Deployments" → "View Logs"
   - Você deve ver "Bot is running..."

✅ **Pronto!** Seu bot está no ar 24/7 gratuitamente!

---

## 🎯 Opção 2: Vercel

**Importante**: na Vercel o bot não usa polling contínuo. Ele responde via webhook em `/api/webhook`.

### Passo a Passo

1. **Configure as variáveis de ambiente na Vercel**
   ```env
   TELEGRAM_TOKEN=seu_token_aqui
   GEMINI_API_KEY=sua_key_aqui
   TELEGRAM_WEBHOOK_SECRET=um_segredo_aleatorio
   ```

2. **Faça o deploy**
   - Use o repositório GitHub normalmente pela Vercel.
   - A rota de produção será `https://SEU-DOMINIO.vercel.app/api/webhook`.

3. **Aponte o Telegram para o webhook**
   ```bash
   curl "https://api.telegram.org/botSEU_TOKEN/setWebhook?url=https://SEU-DOMINIO.vercel.app/api/webhook&secret_token=SEU_SEGREDO"
   ```

4. **Verifique o webhook**
   ```bash
   curl "https://api.telegram.org/botSEU_TOKEN/getWebhookInfo"
   ```

✅ **Bot respondendo via webhook na Vercel!**

---

## 🎯 Opção 3: Render (Alternativa Gratuita)

**Vantagens**: Gratuito, fácil configuração, SSL automático

### Passo a Passo

1. **Acesse [Render.com](https://render.com)** e faça login com GitHub

2. **Crie um novo Web Service**
   - Clique em "New +" → "Web Service"
   - Conecte seu repositório GitHub
   - Selecione `TenorioDevfullStack/RaizitoBot`

3. **Configure o serviço**
   - **Name**: `raizitobot`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`

4. **Adicione variáveis de ambiente**
   - Na seção "Environment Variables", adicione:
     ```
     TELEGRAM_TOKEN=seu_token_aqui
     GEMINI_API_KEY=sua_key_aqui
     ```

5. **Deploy**
   - Clique em "Create Web Service"
   - Aguarde o deploy (3-5 minutos)

✅ **Bot online!**

---

## 🎯 Opção 4: VPS/Servidor com Docker

**Vantagens**: Controle total, pode usar qualquer provedor (DigitalOcean, AWS, Azure, etc.)

### Passo a Passo

1. **Conecte ao seu servidor via SSH**
   ```bash
   ssh usuario@seu-servidor.com
   ```

2. **Instale Docker e Docker Compose**
   ```bash
   # Ubuntu/Debian
   sudo apt update
   sudo apt install -y docker.io docker-compose git
   sudo systemctl start docker
   sudo systemctl enable docker
   ```

3. **Clone o repositório**
   ```bash
   git clone https://github.com/TenorioDevfullStack/RaizitoBot.git
   cd RaizitoBot
   ```

4. **Configure as variáveis de ambiente**
   ```bash
   cp .env.example .env
   nano .env
   ```
   
   Edite o arquivo `.env` com suas credenciais:
   ```env
   TELEGRAM_TOKEN=seu_token_aqui
   GEMINI_API_KEY=sua_key_aqui
   ```

5. **Inicie o bot com Docker Compose**
   ```bash
   docker-compose up -d
   ```

6. **Verificar logs**
   ```bash
   docker-compose logs -f
   ```

7. **Comandos úteis**
   ```bash
   # Parar o bot
   docker-compose down
   
   # Reiniciar o bot
   docker-compose restart
   
   # Atualizar o bot
   git pull
   docker-compose up -d --build
   ```

✅ **Bot rodando em seu servidor!**

---

## 🎯 Opção 5: Google Cloud Run

**Vantagens**: Escalável, paga apenas pelo uso, infraestrutura do Google

### Passo a Passo

1. **Instale o Google Cloud SDK**
   - Acesse [cloud.google.com/sdk](https://cloud.google.com/sdk)

2. **Faça login e configure o projeto**
   ```bash
   gcloud auth login
   gcloud config set project SEU_PROJETO_ID
   ```

3. **Build e push da imagem**
   ```bash
   gcloud builds submit --tag gcr.io/SEU_PROJETO_ID/raizitobot
   ```

4. **Deploy no Cloud Run**
   ```bash
   gcloud run deploy raizitobot \
     --image gcr.io/SEU_PROJETO_ID/raizitobot \
     --platform managed \
     --region us-central1 \
     --set-env-vars TELEGRAM_TOKEN=seu_token,GEMINI_API_KEY=sua_key
   ```

✅ **Bot no Google Cloud!**

---

## 🎯 Opção 6: Heroku

**Vantagens**: Tradicional, bem documentado

> ⚠️ **Nota**: Heroku não oferece mais plano gratuito. Considere Railway ou Render.

### Passo a Passo

1. **Instale o Heroku CLI**
   - Acesse [devcenter.heroku.com/articles/heroku-cli](https://devcenter.heroku.com/articles/heroku-cli)

2. **Faça login**
   ```bash
   heroku login
   ```

3. **Crie um app**
   ```bash
   heroku create raizitobot
   ```

4. **Configure as variáveis de ambiente**
   ```bash
   heroku config:set TELEGRAM_TOKEN=seu_token
   heroku config:set GEMINI_API_KEY=sua_key
   ```

5. **Deploy**
   ```bash
   git push heroku master
   ```

6. **Verificar logs**
   ```bash
   heroku logs --tail
   ```

---

## 🔧 Manutenção e Monitoramento

### Verificar se o bot está online

Envie `/start` para o bot no Telegram. Se responder, está funcionando!

### Atualizar o bot

Para todas as opções baseadas em Git (Railway, Render):
1. Faça commit das mudanças
2. Push para o GitHub
3. Deploy automático será acionado

Para Vercel, depois do deploy confirme se o webhook continua apontando para:
```bash
https://SEU-DOMINIO.vercel.app/api/webhook
```

Para Docker:
```bash
git pull
docker-compose up -d --build
```

### Logs e Debugging

- **Railway**: Painel → View Logs
- **Vercel**: Dashboard → Project → Logs ou Functions
- **Render**: Dashboard → Logs
- **Docker**: `docker-compose logs -f`
- **Heroku**: `heroku logs --tail`

---

## 🆘 Troubleshooting

### Bot não responde

1. Verifique se as variáveis de ambiente estão corretas
2. Verifique os logs para erros
3. Confirme que o token do Telegram está correto

### Erro de API Key

- Verifique se as API keys estão ativas
- Confirme que não há espaços extras nas variáveis

### Problemas com áudio

- Certifique-se de que `ffmpeg` está instalado (já incluído no Dockerfile)

---

## 💰 Custos Estimados

| Plataforma | Custo Mensal | Notas |
|------------|--------------|-------|
| Railway | **Gratuito** | $5/mês de crédito grátis |
| Vercel | **Gratuito** | Ideal para webhook serverless |
| Render | **Gratuito** | Plano free tier |
| VPS (DigitalOcean) | $4-6 | Droplet básico |
| Google Cloud Run | $0-5 | Pay-per-use |
| Heroku | $7+ | Sem plano gratuito |

---

## 🎉 Recomendação Final

Para começar, recomendo **Railway** pela facilidade e gratuidade. Quando o bot crescer, considere migrar para um VPS ou Google Cloud Run para mais controle.

**Dúvidas?** Abra uma issue no GitHub!

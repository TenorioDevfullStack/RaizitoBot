# 🔑 Guia de Configuração das APIs do Google

Este guia detalha como obter as credenciais necessárias para as funcionalidades de busca e integração com o Google Workspace (Gmail, Drive, Calendar, Docs).

## 1. Criar um Projeto no Google Cloud

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/).
2. Clique no seletor de projetos no topo da página e selecione **"Novo Projeto"**.
3. Dê um nome ao projeto (ex: `RaizitoBot`) e clique em **"Criar"**.
4. Certifique-se de que o novo projeto está selecionado.

## 2. Ativar as APIs Necessárias

No menu lateral, vá em **"APIs e Serviços" > "Biblioteca"** e pesquise/ative as seguintes APIs:

- **Gmail API**
- **Google Drive API**
- **Google Calendar API**
- **Google Docs API**
- **Custom Search API** (para busca na web)

## 3. Configurar a Busca na Web (Custom Search)

Para usar o comando `/search`, você precisa de uma API Key e um ID de Mecanismo de Pesquisa (CX).

1. **Obter a API Key**:
   - Vá em **"APIs e Serviços" > "Credenciais"**.
   - Clique em **"Criar Credenciais" > "Chave de API"**.
   - Copie a chave gerada. Esta será sua `GOOGLE_SEARCH_API_KEY`.

2. **Obter o ID do Mecanismo de Pesquisa (CX)**:
   - Acesse o [Programmable Search Engine](https://programmablesearchengine.google.com/controlpanel/all).
   - Clique em **"Adicionar"**.
   - Em "Pesquisar em", selecione **"Pesquisar na Web inteira"**.
   - Dê um nome ao mecanismo e clique em **"Criar"**.
   - Após criar, clique em **"Personalizar"** e copie o **"ID do mecanismo de pesquisa"**. Este será seu `GOOGLE_SEARCH_CX`.

## 4. Configurar o Service Account (Gmail, Drive, Calendar, Docs)

Para acessar os dados do usuário, usaremos uma Conta de Serviço.

1. **Criar a Conta de Serviço**:
   - No Google Cloud Console, vá em **"IAM e Administrador" > "Contas de serviço"**.
   - Clique em **"Criar Conta de Serviço"**.
   - Dê um nome (ex: `raizitobot-service`) e clique em **"Criar e Continuar"**.
   - (Opcional) Dê a função de "Leitor" ou "Editor" se necessário, mas para este bot, as permissões serão dadas via compartilhamento direto.
   - Clique em **"Concluir"**.

2. **Gerar a Chave JSON**:
   - Clique na conta de serviço recém-criada (no e-mail da lista).
   - Vá na aba **"Chaves"**.
   - Clique em **"Adicionar Chave" > "Criar nova chave"**.
   - Selecione **JSON** e clique em **"Criar"**.
   - O arquivo será baixado automaticamente. Renomeie-o para `service_account.json` (ou o nome que preferir) e coloque-o na raiz do projeto.
   - **IMPORTANTE**: Defina o caminho deste arquivo na variável `GOOGLE_SERVICE_ACCOUNT_FILE` no seu `.env`.

3. **Compartilhar Recursos**:
   - Copie o **e-mail** da conta de serviço (algo como `raizitobot-service@seu-projeto.iam.gserviceaccount.com`).
   - **Drive/Docs**: Vá ao seu Google Drive, clique com o botão direito na pasta ou arquivo que deseja que o bot acesse, clique em "Compartilhar" e cole o e-mail da conta de serviço.
   - **Calendar**:
     1. Acesse [calendar.google.com](https://calendar.google.com).
     2. No menu lateral esquerdo, localize a seção **"Minhas agendas"**.
     3. Passe o mouse sobre o nome da sua agenda (no seu caso, **"Leandro Tenório"**).
     4. Clique nos **três pontinhos (Opções)** que aparecerão ao lado do nome e selecione **"Configurações e compartilhamento"**.
     5. **OU**, se já estiver na tela de Configurações, clique em **"Leandro Tenório"** no menu lateral esquerdo (abaixo de "Configurações das minhas agendas").
     6. Role a página principal até encontrar a seção **"Compartilhar com pessoas ou grupos específicos"**.
     7. Clique em **"Adicionar pessoas e grupos"**.
     8. Cole o e-mail da conta de serviço e selecione **"Fazer alterações em eventos"** se quiser usar criação de eventos com `/event` e `/confirm_event`. Para apenas ler a agenda, **"Ver todos os detalhes do evento"** é suficiente.
     9. Clique em **"Enviar"**.

## Resumo das Variáveis no `.env`

```env
GOOGLE_SEARCH_API_KEY=Sua_Chave_de_API_do_Passo_3
GOOGLE_SEARCH_CX=Seu_ID_CX_do_Passo_3
GOOGLE_SERVICE_ACCOUNT_FILE=caminho/para/seu/arquivo_json_do_Passo_4.json
GOOGLE_CALENDAR_TIMEZONE=America/Sao_Paulo
```

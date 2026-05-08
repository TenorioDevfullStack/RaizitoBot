# Plano de Implementacao - Super Assistente

Este plano transforma o RaizitoBot de um chatbot com ferramentas em um assistente pessoal proativo, com memoria, agenda, tarefas inteligentes e integracoes cada vez mais autonomas.

## Fase 1 - Fundacao de assistente pessoal

Objetivo: fazer o bot lembrar contexto importante e entender comandos naturais simples.

- Memoria persistente por usuario.
- Comandos para salvar, listar e apagar memorias.
- Uso das memorias nas respostas do Gemini.
- Intencoes naturais basicas, como "lembre que..." e "o que voce lembra de mim?".
- Melhorias nas mensagens de ajuda.

## Fase 2 - Tarefas inteligentes

Objetivo: deixar as tarefas mais proximas de um assistente real.

- Prazo, prioridade e categoria nas tarefas.
- Listagem por hoje, semana, atrasadas e concluidas.
- Lembretes agendados usando job queue do python-telegram-bot.
- Criacao de tarefa por linguagem natural.
- Recorrencia simples: diaria, semanal e mensal.

## Fase 3 - Agenda e resumo diario

Objetivo: transformar Calendar + tarefas + memoria em briefing pessoal.

- Comando `/today` com agenda, tarefas e prioridades.
- Resumo diario automatico em horario configuravel.
- Criacao de eventos no Calendar por linguagem natural.
- Avisos antes de reunioes.
- Sugestoes de reorganizacao quando o dia estiver cheio.

## Fase 4 - Email e Drive inteligentes

Objetivo: fazer o bot ler, resumir e preparar respostas com aprovacao humana.

- Resumo de emails recentes e importantes.
- Busca semantica simples em emails.
- Rascunho de resposta para aprovacao.
- Busca e resumo de arquivos do Drive.
- Perguntas e respostas sobre Docs.

## Fase 5 - Modo agente

Objetivo: permitir que o usuario de uma meta e o bot quebre em passos.

- Planejamento automatico de metas.
- Execucao com checkpoints.
- Registro do estado de uma missao.
- Confirmacao antes de acoes sensiveis.
- Relatorios de progresso.

## Fase 6 - Painel e operacao

Objetivo: dar visibilidade e controle fora do Telegram.

- Painel web com status do bot.
- Logs recentes e erros por integracao.
- Lista de usuarios autorizados.
- Backup do banco.
- Configuracoes editaveis.

## Regras de produto

- O bot deve pedir confirmacao antes de enviar emails, criar eventos importantes ou apagar dados.
- O usuario deve conseguir ver e apagar memorias.
- Falhas de API devem virar mensagens claras, nao stack traces.
- Cada fase deve terminar com testes manuais simples e atualizacao da documentacao.

## Primeira entrega

Implementar a Fase 1:

- Tabela `memories`.
- Funcoes de banco para criar, listar e apagar memorias.
- Comandos `/remember`, `/memory` e `/forget`.
- Deteccao de mensagens como "lembre que..." sem precisar chamar comando.
- Inclusao das memorias no prompt enviado ao Gemini.

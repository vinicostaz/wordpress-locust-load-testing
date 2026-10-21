# Testes de carga no WordPress com Locust

Projeto acadêmico para avaliar o desempenho de uma instalação WordPress com
balanceamento de carga, variando simultaneamente:

- o conteúdo acessado;
- a quantidade de usuários concorrentes;
- a quantidade de instâncias do WordPress.

O projeto executa automaticamente uma matriz com 27 testes e transforma os
resultados do Locust em tabelas e gráficos.

## Arquitetura

```text
                                   +--> wordpress1 --+
Locust --> Nginx (load balancer) ---+--> wordpress2 --+--> MySQL
                                   +--> wordpress3 --+
```

O ambiente contém:

- um Nginx como único ponto de entrada;
- três instâncias WordPress que compartilham arquivos e banco de dados;
- um MySQL acessível somente pela rede interna;
- um Locust definido no Docker Compose;
- ferramentas auxiliares para preparar o conteúdo e gerar o relatório.

## Cenários avaliados

| Identificador | Conteúdo simulado |
| --- | --- |
| `imagem_1mb` | Post e imagem PNG de aproximadamente 1 MB |
| `texto_400kb` | Post contendo aproximadamente 400 KB de texto |
| `imagem_300kb` | Post e imagem PNG de aproximadamente 300 KB |

Cada cenário é executado com:

- 10, 100 e 1000 usuários;
- 1, 2 e 3 instâncias do WordPress.

Isso produz `3 x 3 x 3 = 27` execuções.

## Tecnologias

- Docker Engine e Docker Compose v2;
- `nginx:1.19.0`;
- `wordpress:5.4.2-php7.2-apache`;
- `mysql:5.7`;
- `locustio/locust:2.33.2`;
- Python e Matplotlib para consolidação dos resultados.

> As versões do WordPress, Nginx e MySQL foram mantidas para atender aos
> requisitos da atividade. Elas não são recomendadas para produção.

## Pré-requisitos

- Docker instalado e em execução;
- Docker Compose v2;
- `curl` disponível no host.

Verifique com:

```bash
docker --version
docker compose version
curl --version
```

## 1. Configuração

Clone o repositório e entre na pasta:

```bash
git clone https://github.com/vinicostaz/wordpress-locust-load-testing.git
cd wordpress-locust-load-testing
```

Crie o arquivo local de variáveis:

```bash
cp .env.example .env
```

Edite `.env` e substitua todas as senhas de exemplo.

Por padrão, o WordPress é publicado em <http://localhost:8080> e o painel do
Locust em <http://localhost:8089>.

## 2. Inicialização dos contêineres

Inicie o ambiente:

```bash
docker compose up -d
```

Confira os seis serviços:

```bash
docker compose ps
```

Os serviços esperados são `mysql`, `wordpress1`, `wordpress2`, `wordpress3`,
`nginx` e `locust`.

## 3. Preparação automática dos posts

Execute a ferramenta de preparação:

```bash
docker compose --profile tools run --rm content-setup
```

Ela realiza automaticamente as seguintes tarefas:

1. aguarda o WordPress responder;
2. conclui a instalação inicial usando as variáveis do `.env`;
3. gera imagens PNG de aproximadamente 1 MB e 300 KB;
4. cria ou atualiza os três posts;
5. grava em `runtime/scenarios.json` os endereços usados pelo Locust.

O comando pode ser executado novamente sem criar posts duplicados.

## 4. Teste interativo pelo Locust

Abra <http://localhost:8089>. Informe, por exemplo:

- **Number of users:** `10`;
- **Ramp up:** `10`;
- **Host:** `http://nginx`.

O cenário padrão é `imagem_1mb`. Para alterar o cenário da interface, modifique
`SCENARIO` no serviço `locust` do `docker-compose.yml` e recrie o serviço.

## 5. Execução automática da matriz completa

O script utiliza 20 segundos por execução por padrão:

```bash
./scripts/run_matrix.sh
```

O teste completo leva aproximadamente 9 minutos, além do tempo necessário para
baixar ou construir as imagens Docker na primeira execução.

É possível alterar a duração:

```bash
DURATION=60 ./scripts/run_matrix.sh
```

Também é possível executar uma matriz menor para validação rápida:

```bash
USERS="10" INSTANCES="1" SCENARIOS="imagem_1mb" DURATION=10 ./scripts/run_matrix.sh
```

Durante a execução, o script:

1. ativa 1, 2 ou 3 instâncias do WordPress;
2. recria o Nginx com o pool correspondente;
3. executa o Locust em modo headless;
4. salva CSV e relatório HTML de cada teste;
5. consolida as métricas;
6. gera automaticamente os gráficos finais.

Por padrão, o Locust usa dois processos para aproveitar mais de um núcleo de
CPU durante os testes com 1000 usuários. Esse valor pode ser alterado:

```bash
LOCUST_PROCESSES=4 ./scripts/run_matrix.sh
```

## Resultados gerados

Uma execução completa da matriz já foi realizada e acompanha o projeto. O
[relatório consolidado](results/RELATORIO.md) apresenta a tabela, a análise e
os 12 gráficos obtidos.

```text
results/
|-- RELATORIO.md
|-- summary.csv
|-- test_matrix.csv
|-- html/                 # relatório individual de cada execução
`-- raw/                  # arquivos CSV originais do Locust

graphs/
|-- imagem_1mb_*.png
|-- imagem_300kb_*.png
`-- texto_400kb_*.png
```

Para cada cenário são produzidos quatro gráficos:

- tempo médio de resposta por número de usuários;
- requisições por segundo por número de usuários;
- tempo médio de resposta por número de instâncias;
- requisições por segundo por número de instâncias.

O `summary.csv` também contém mediana, percentis P95 e P99, número de
requisições, falhas e taxa percentual de falhas.

## Executando somente o gerador de relatório

Se os CSVs já existem:

```bash
docker compose --profile tools run --rm --build report
```

## Como conferir o balanceamento

Execute várias vezes:

```bash
curl -I http://localhost:8080/
```

O cabeçalho `X-Upstream` mostra qual instância respondeu:

```text
X-Upstream: 172.20.0.4:80
```

## Comandos úteis

Exibir logs:

```bash
docker compose logs -f
```

Parar os contêineres preservando dados:

```bash
docker compose down
```

Apagar contêineres e o volume do banco:

```bash
docker compose down -v
```

Para reiniciar completamente, remova também o conteúdo local de
`wordpress_data/` e `runtime/` antes de subir o ambiente novamente.

## Estrutura do projeto

```text
.
|-- docker-compose.yml
|-- locust/
|   `-- locustfile.py
|-- nginx/
|   |-- nginx-1.conf
|   |-- nginx-2.conf
|   `-- nginx-3.conf
|-- report/
|   `-- Dockerfile
|-- scripts/
|   |-- generate_report.py
|   |-- run_matrix.sh
|   `-- setup_content.py
|-- graphs/
|-- results/
|-- runtime/
`-- wordpress_data/
```

## Observações sobre os resultados

Testes de carga executados em máquinas diferentes podem produzir números
diferentes. CPU, memória, armazenamento, processos em segundo plano e o tempo
de aquecimento do WordPress influenciam as métricas. Por isso, compare os
cenários executados na mesma máquina e sob as mesmas condições.

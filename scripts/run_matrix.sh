#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if [[ ! -f .env ]]; then
    echo "Arquivo .env ausente. Execute: cp .env.example .env" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

# Matriz padrao: 3 cargas x 3 quantidades de instancias x 3 cenarios = 27 testes.
# As variaveis podem ser sobrescritas para executar uma matriz menor.
USERS_VALUES=(${USERS:-10 100 1000})
INSTANCE_VALUES=(${INSTANCES:-1 2 3})
SCENARIO_VALUES=(${SCENARIOS:-imagem_1mb texto_400kb imagem_300kb})
DURATION="${DURATION:-20}"
LOCUST_PROCESSES="${LOCUST_PROCESSES:-2}"

if [[ ! -f runtime/scenarios.json ]]; then
    echo "Cenarios nao preparados. Execute:" >&2
    echo "docker compose --profile tools run --rm content-setup" >&2
    exit 1
fi

mkdir -p results/raw results/html graphs
printf 'scenario,instances,users,duration_seconds,spawn_rate,locust_processes,executed_at\n' > results/test_matrix.csv

restore_stack() {
    # Ao terminar, deixa novamente as tres instancias e a interface do Locust ativas.
    docker compose start wordpress1 wordpress2 wordpress3 >/dev/null 2>&1 || true
    WORDPRESS_INSTANCES=3 docker compose up -d --no-deps --force-recreate nginx >/dev/null 2>&1 || true
    docker compose up -d locust >/dev/null 2>&1 || true
}
trap restore_stack EXIT

wait_for_site() {
    local attempts=0
    until curl -fsS -H "Host: ${SITE_HOST_HEADER}" "http://localhost:${NGINX_PORT}/" >/dev/null; do
        attempts=$((attempts + 1))
        if (( attempts >= 60 )); then
            echo "Site nao respondeu apos 60 tentativas." >&2
            return 1
        fi
        sleep 2
    done
}

configure_instances() {
    local instances="$1"
    # wordpress1 e a instancia base e permanece ativa em todos os testes.
    docker compose start wordpress1 >/dev/null

    # Liga somente os WordPress necessarios para a rodada atual.
    case "$instances" in
        1)
            # Teste com uma instancia: somente wordpress1.
            docker compose stop wordpress2 wordpress3 >/dev/null
            ;;
        2)
            # Teste com duas instancias: wordpress1 e wordpress2.
            docker compose start wordpress2 >/dev/null
            docker compose stop wordpress3 >/dev/null
            ;;
        3)
            # Teste com tres instancias: todas ficam ativas.
            docker compose start wordpress2 wordpress3 >/dev/null
            ;;
        *)
            echo "Quantidade de instancias invalida: $instances" >&2
            return 1
            ;;
    esac

    # Recria somente o Nginx e seleciona o arquivo nginx-N.conf correspondente.
    WORDPRESS_INSTANCES="$instances" docker compose up -d --no-deps --force-recreate nginx >/dev/null
    wait_for_site
}

docker compose stop locust >/dev/null 2>&1 || true

# Primeiro varia as instancias; dentro de cada configuracao varia cenario e usuarios.
for instances in "${INSTANCE_VALUES[@]}"; do
    echo
    echo "=== Configurando ${instances} instancia(s) WordPress ==="
    configure_instances "$instances"

    for scenario in "${SCENARIO_VALUES[@]}"; do
        for users in "${USERS_VALUES[@]}"; do
            spawn_rate=$((users / 10))
            (( spawn_rate < 1 )) && spawn_rate=1
            prefix="${scenario}_i${instances}_u${users}"

            rm -f "results/raw/${prefix}"_*.csv "results/html/${prefix}.html"

            echo
            echo "--- Cenario=${scenario} | instancias=${instances} | usuarios=${users} ---"
            # Executa o Locust sem interface e grava CSV e HTML para esta combinacao.
            # --users define o total de usuarios; --spawn-rate a velocidade de entrada;
            # --run-time define por quanto tempo a carga permanece em execucao.
            docker compose run --rm --no-deps \
                -e SCENARIO="$scenario" \
                locust \
                -f /mnt/locust/locustfile.py \
                --host http://nginx \
                --headless \
                --users "$users" \
                --spawn-rate "$spawn_rate" \
                --run-time "${DURATION}s" \
                --processes "$LOCUST_PROCESSES" \
                --stop-timeout 10 \
                --reset-stats \
                --csv "/mnt/results/raw/${prefix}" \
                --csv-full-history \
                --html "/mnt/results/html/${prefix}.html" \
                --only-summary \
                --exit-code-on-error 0

            printf '%s,%s,%s,%s,%s,%s,%s\n' \
                "$scenario" "$instances" "$users" "$DURATION" "$spawn_rate" "$LOCUST_PROCESSES" "$(date -Iseconds)" \
                >> results/test_matrix.csv
        done
    done
done

docker compose --profile tools run --rm --build report

echo
echo "Matriz concluida. Consulte results/summary.csv, results/RELATORIO.md e graphs/."

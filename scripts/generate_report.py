#!/usr/bin/env python3

import csv
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt


BASE_DIR = Path("/work")
RAW_DIR = BASE_DIR / "results" / "raw"
RESULTS_DIR = BASE_DIR / "results"
GRAPHS_DIR = BASE_DIR / "graphs"
PATTERN = re.compile(r"(?P<scenario>.+)_i(?P<instances>\d+)_u(?P<users>\d+)_stats\.csv$")

SCENARIO_LABELS = {
    "imagem_1mb": "Post com imagem de aproximadamente 1 MB",
    "texto_400kb": "Post com texto de aproximadamente 400 KB",
    "imagem_300kb": "Post com imagem de aproximadamente 300 KB",
}


def number(row, *names, default=0.0):
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return float(value)
    return default


def load_results():
    results = []
    for path in sorted(RAW_DIR.glob("*_stats.csv")):
        match = PATTERN.match(path.name)
        if not match:
            continue
        with path.open(newline="", encoding="utf-8-sig") as stream:
            rows = list(csv.DictReader(stream))
        aggregate = next(
            (row for row in rows if row.get("Name") in {"Aggregated", "Aggregate"}),
            rows[-1] if rows else None,
        )
        if not aggregate:
            continue
        results.append(
            {
                "scenario": match.group("scenario"),
                "instances": int(match.group("instances")),
                "users": int(match.group("users")),
                "requests": int(number(aggregate, "Request Count")),
                "failures": int(number(aggregate, "Failure Count")),
                "avg_response_ms": number(aggregate, "Average Response Time"),
                "median_response_ms": number(aggregate, "Median Response Time"),
                "p95_response_ms": number(aggregate, "95%"),
                "p99_response_ms": number(aggregate, "99%"),
                "requests_per_second": number(aggregate, "Requests/s"),
                "failures_per_second": number(aggregate, "Failures/s"),
            }
        )
    for row in results:
        row["failure_rate_percent"] = (
            row["failures"] / row["requests"] * 100 if row["requests"] else 0.0
        )
    return results


def write_summary(results):
    fields = [
        "scenario",
        "instances",
        "users",
        "requests",
        "failures",
        "failure_rate_percent",
        "avg_response_ms",
        "median_response_ms",
        "p95_response_ms",
        "p99_response_ms",
        "requests_per_second",
        "failures_per_second",
    ]
    with (RESULTS_DIR / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted(results, key=lambda item: (item["scenario"], item["instances"], item["users"])))


def grouped_bar(rows, x_key, series_key, metric, title, x_label, y_label, output):
    x_values = sorted({row[x_key] for row in rows})
    series_values = sorted({row[series_key] for row in rows})
    lookup = {(row[x_key], row[series_key]): row[metric] for row in rows}

    width = 0.8 / max(len(series_values), 1)
    positions = list(range(len(x_values)))
    fig, ax = plt.subplots(figsize=(10, 6))

    for index, series in enumerate(series_values):
        offset = (index - (len(series_values) - 1) / 2) * width
        values = [lookup.get((x, series), 0) for x in x_values]
        bars = ax.bar(
            [position + offset for position in positions],
            values,
            width=width,
            label=f"{series} {'instancia(s)' if series_key == 'instances' else 'usuarios'}",
        )
        for bar, value in zip(bars, values):
            ax.annotate(
                f"{value:.1f}",
                (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=7,
                rotation=45,
            )

    ax.set_title(title)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_xticks(positions, [str(value) for value in x_values])
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)


def create_graphs(results):
    GRAPHS_DIR.mkdir(parents=True, exist_ok=True)
    grouped = defaultdict(list)
    for row in results:
        grouped[row["scenario"]].append(row)

    outputs = []
    for scenario, rows in sorted(grouped.items()):
        label = SCENARIO_LABELS.get(scenario, scenario)
        graph_specs = [
            ("users", "instances", "avg_response_ms", "por_usuarios_tempo", "Número de usuários", "Tempo médio de resposta (ms)"),
            ("users", "instances", "requests_per_second", "por_usuarios_rps", "Número de usuários", "Requisições por segundo"),
            ("instances", "users", "avg_response_ms", "por_instancias_tempo", "Número de instâncias WordPress", "Tempo médio de resposta (ms)"),
            ("instances", "users", "requests_per_second", "por_instancias_rps", "Número de instâncias WordPress", "Requisições por segundo"),
        ]
        for x_key, series_key, metric, suffix, x_label, y_label in graph_specs:
            output = GRAPHS_DIR / f"{scenario}_{suffix}.png"
            grouped_bar(rows, x_key, series_key, metric, label, x_label, y_label, output)
            outputs.append(output)
    return outputs


def load_matrix_settings():
    matrix_path = RESULTS_DIR / "test_matrix.csv"
    if not matrix_path.exists():
        return [], []
    with matrix_path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    durations = sorted({int(row["duration_seconds"]) for row in rows if row.get("duration_seconds")})
    processes = sorted({int(row["locust_processes"]) for row in rows if row.get("locust_processes")})
    return durations, processes


def write_report(results, graphs):
    total_requests = sum(row["requests"] for row in results)
    total_failures = sum(row["failures"] for row in results)
    durations, processes = load_matrix_settings()
    duration_text = ", ".join(f"{value} s" for value in durations) or "não registrada"
    process_text = ", ".join(str(value) for value in processes) or "não registrado"
    lines = [
        "# Relatório dos testes de carga",
        "",
        f"Gerado em {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}.",
        "",
        "## Metodologia",
        "",
        "Foram combinados três cenários de conteúdo, três quantidades de usuários e três quantidades de instâncias WordPress. O Locust enviou as requisições ao Nginx, que as distribuiu entre as instâncias ativas.",
        "",
        f"- Execuções processadas: {len(results)}",
        f"- Duração registrada por execução: {duration_text}",
        f"- Processos do Locust por execução: {process_text}",
        f"- Requisições totais: {total_requests}",
        f"- Falhas totais: {total_failures}",
        "",
        "## Resultados consolidados",
        "",
        "| Cenário | Instâncias | Usuários | Requisições | Falhas | Taxa de falhas | Média (ms) | P95 (ms) | RPS |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted(results, key=lambda item: (item["scenario"], item["instances"], item["users"])):
        lines.append(
            f"| {SCENARIO_LABELS.get(row['scenario'], row['scenario'])} | {row['instances']} | {row['users']} | "
            f"{row['requests']} | {row['failures']} | {row['failure_rate_percent']:.2f}% | {row['avg_response_ms']:.1f} | "
            f"{row['p95_response_ms']:.1f} | {row['requests_per_second']:.2f} |"
        )

    low_load_rows = [row for row in results if row["users"] in {10, 100}]
    high_load_rows = [row for row in results if row["users"] == 1000]
    high_load_best_rps = {}
    for scenario in SCENARIO_LABELS:
        candidates = [row for row in high_load_rows if row["scenario"] == scenario]
        if candidates:
            high_load_best_rps[scenario] = max(candidates, key=lambda row: row["requests_per_second"])

    lines += [
        "",
        "## Análise dos resultados",
        "",
        f"- Nas {len(low_load_rows)} execuções com 10 ou 100 usuários não houve falhas, independentemente da quantidade de instâncias.",
        "- Com 1000 usuários, o aumento de instâncias elevou a vazão em vários casos, mas também expôs contenção nos recursos compartilhados. Por isso, RPS, latência e taxa de falhas devem ser analisados em conjunto.",
    ]
    for scenario, row in high_load_best_rps.items():
        lines.append(
            f"- Em **{SCENARIO_LABELS[scenario]}**, a maior vazão com 1000 usuários foi "
            f"{row['requests_per_second']:.2f} RPS com {row['instances']} instância(s), "
            f"acompanhada de {row['failure_rate_percent']:.2f}% de falhas."
        )
    lines += [
        "- Os resultados indicam que adicionar servidores WordPress isoladamente não garante maior confiabilidade: banco de dados, volume compartilhado e capacidade da própria máquina de testes também podem se tornar gargalos.",
        "- Os números representam esta máquina e esta duração de teste; repetições mais longas são recomendadas antes de extrapolar os resultados para produção.",
        "",
        "## Gráficos",
        "",
    ]
    for graph in graphs:
        lines.append(f"![{graph.stem}](../graphs/{graph.name})")
        lines.append("")
    (RESULTS_DIR / "RELATORIO.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    results = load_results()
    if not results:
        raise SystemExit("Nenhum arquivo *_stats.csv encontrado em results/raw")
    write_summary(results)
    graphs = create_graphs(results)
    write_report(results, graphs)
    print(f"Relatorio gerado com {len(results)} execucoes e {len(graphs)} graficos.")


if __name__ == "__main__":
    main()

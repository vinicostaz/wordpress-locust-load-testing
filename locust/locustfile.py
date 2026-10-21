import json
import os
from pathlib import Path

from locust import FastHttpUser, between, task


# O script de preparacao grava neste JSON os enderecos reais dos posts e imagens.
CONFIG_PATH = Path(os.getenv("SCENARIO_CONFIG", "/mnt/runtime/scenarios.json"))
# Permite reutilizar o mesmo locustfile para os tres cenarios da atividade.
SCENARIO = os.getenv("SCENARIO", "imagem_1mb")
HOST_HEADER = os.getenv("SITE_HOST_HEADER", "localhost:8080")


def load_scenario():
    """Carrega os caminhos do post e, quando existir, da imagem do cenario."""
    if not CONFIG_PATH.exists():
        raise RuntimeError(
            f"Arquivo {CONFIG_PATH} nao encontrado. Execute o content-setup antes dos testes."
        )

    scenarios = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if SCENARIO not in scenarios:
        valid = ", ".join(sorted(scenarios))
        raise RuntimeError(f"Cenario '{SCENARIO}' invalido. Opcoes: {valid}")
    return scenarios[SCENARIO]


SCENARIO_DATA = load_scenario()


class WordPressUser(FastHttpUser):
    # Cada objeto representa um usuario virtual. A pausa simula tempo de navegacao.
    wait_time = between(0.5, 1.5)

    @task
    def view_post(self):
        # Esta tarefa e repetida por cada usuario ate o fim do teste.
        headers = {"Host": HOST_HEADER}
        post_path = SCENARIO_DATA["post_path"]

        # Primeira requisicao: pagina dinamica do post no WordPress.
        with self.client.get(
            post_path,
            headers=headers,
            name=f"/{SCENARIO}/post",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}")

        # Cenarios de imagem fazem uma segunda requisicao para o arquivo estatico.
        # No cenario de texto asset_path nao existe e esta parte e ignorada.
        asset_path = SCENARIO_DATA.get("asset_path")
        if asset_path:
            with self.client.get(
                asset_path,
                headers=headers,
                name=f"/{SCENARIO}/asset",
                catch_response=True,
            ) as response:
                if response.status_code != 200:
                    response.failure(f"HTTP {response.status_code}")

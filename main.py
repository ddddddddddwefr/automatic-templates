# main.py
import json
import pathlib
import time
import uuid
from typing import Dict

import requests
import yaml
from jinja2 import Environment, FileSystemLoader
from jsonschema import ValidationError, validate
from rich import print
import typer

from Generators.mapper_xaml import to_xaml
from Generators.stubs import to_csharp, to_js

app = typer.Typer()
ROOT = pathlib.Path(__file__).parent


def load_template():
    tdir = ROOT / "Templates" / "SupportClassify"
    spec = yaml.safe_load((tdir / "template.yaml").read_text())
    schema = json.loads((tdir / "schema.json").read_text())
    env = Environment(loader=FileSystemLoader(str(tdir)))
    system = env.from_string(spec["system"])
    user = env.from_string(spec["user"])
    return spec, schema, system, user


def call_ollama(model: str, prompt: str) -> Dict:
    # Ollama REST API: POST /api/generate
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    # many models output text; ensure it's pure JSON:
    text = data.get("response", "").strip()
    return json.loads(text)


def call_lmstudio(
    base_url: str,
    model: str,
    system_message: str,
    user_message: str,
    schema: Dict | None = None,
    temperature: float = 0.1,
    timeout: int = 120,
) -> Dict:
    """Call an LM Studio local server (OpenAI-compatible /v1) and return parsed JSON.

    If a JSON Schema is provided, request structured output so the model returns
    JSON matching the schema in the message content.
    """
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
    ]
    payload: Dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "ticket_result", "schema": schema},
        }

    url = base_url.rstrip("/") + "/chat/completions"
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"]["content"].strip()
    return json.loads(content)


@app.command()
def run(
    ticket_path: str = "Data/ticket.txt",
    product: str = "X",
    severity: str = "high",
    model: str = "qwen2.5-coder-0.5b-instruct",
    provider: str = "lmstudio",  # lmstudio | ollama
    base_url: str = "http://192.168.100.81:3000/v1",
):
    spec, schema, system, user = load_template()
    ticket_text = pathlib.Path(ticket_path).read_text().strip()

    sys_msg = system.render(
        product=product, severity=severity, ticket_text=ticket_text
    )
    user_msg = user.render(
        product=product, severity=severity, ticket_text=ticket_text
    )

    t0 = time.time()
    if provider.lower() == "lmstudio":
        out = call_lmstudio(
            base_url=base_url,
            model=model,
            system_message=sys_msg,
            user_message=user_msg,
            schema=schema,
            temperature=float(spec["constraints"]["temperature"]),
        )
    elif provider.lower() == "ollama":
        prompt = sys_msg + "\n\n" + user_msg
        out = call_ollama(model, prompt)
    else:
        print(f"[red]Unknown provider:[/red] {provider}. Use 'lmstudio' or 'ollama'.")
        raise SystemExit(1)
    latency = time.time() - t0

    # Validate against JSON Schema (reject bad outputs)
    try:
        validate(out, schema)
    except ValidationError as e:
        print("[red]Schema validation failed:[/red]", e)
        raise SystemExit(1)

    # Save artifacts
    run_id = uuid.uuid4().hex[:8]
    (ROOT / "Logs").mkdir(exist_ok=True)
    (ROOT / "Workflows").mkdir(exist_ok=True)
    (ROOT / "Workflows" / f"RouteTicket_{run_id}.xaml").write_text(to_xaml(out))
    (ROOT / "Workflows" / f"Router_{run_id}.cs").write_text(to_csharp(out))
    (ROOT / "Workflows" / f"router_{run_id}.js").write_text(to_js(out))
    (ROOT / "Logs" / f"result_{run_id}.json").write_text(
        json.dumps({"result": out, "latency_s": round(latency, 3)}, indent=2)
    )

    print(
        f"[green]Done[/green] → label={out['label']} confidence={out['confidence']:.2f}  latency={latency:.2f}s"
    )
    print("See Workflows/ and Logs/ for outputs.")


if __name__ == "__main__":
    app()



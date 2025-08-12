Below is a **simple, copy-pasteable, step-by-step** guide to build a *tiny Autopilot-style mock* on your Mac using only easy, open-source tools. You’ll end up with a local project that:

* takes a support ticket text,
* calls a local LLM (or OpenAI/Azure if you want),
* validates a strict JSON schema, and
* writes a **fake UiPath-style workflow file** (`.xaml`) plus small C#/JS stubs you could glue into bigger automations later.
  Then you’ll push it to GitHub.

---

# What you’ll build

A small folder that looks like a UiPath project skeleton:

```
uipath-mock/
  Templates/        # prompt + schema
  Generators/       # code that turns JSON -> XAML / C# / JS
  Workflows/        # generated "workflow" files (XAML-like)
  Data/             # sample inputs
  Logs/             # run logs
  main.py           # run the pipeline
  requirements.txt
  README.md
```

The core flow:

1. Render a prompt → 2) Call LLM → 3) Validate JSON → 4) Generate a tiny **XAML** + **C#** + **JS** output.

---

# 0) What you need (once)

* **Homebrew** (Mac package manager). Install from homepage (one line script). ([Homebrew][1], [Homebrew Documentation][2])
* **Git** (version control): easiest on macOS is either `xcode-select --install` prompt or `brew install git`. ([Git][3], [theodinproject.com][4])
* **VS Code** (editor). Download for macOS. ([Visual Studio Code][5])
* **Python 3** via Homebrew (keeps things simple on Mac). ([Homebrew Documentation][6])
* **Ollama** (runs LLMs locally) – install with Homebrew. ([Homebrew Formulae][7])

---

# 1) Install tools (Terminal)

```bash
# 1) Install Homebrew (if you don't have it)
# Copy the command from https://brew.sh and paste here, then:
brew update                               # keep formulas fresh

# 2) Git + Python + Ollama
brew install git
brew install python
brew install ollama

# 3) Start Ollama (keeps an API running at http://localhost:11434)
ollama serve
```

* Homebrew install & prefixes: see official docs. ([Homebrew Documentation][2])
* Ollama formula and quick install command: `brew install ollama`. ([Homebrew Formulae][7])
* Ollama API listens on port **11434** (`ollama serve`). ([Postman][8])

**Pull a small model** (example):

```bash
# In another terminal tab:
ollama pull mistral   # or llama3:instruct if you prefer
ollama list           # see installed models
```

(You can call the REST API with `POST /api/generate` later.) ([ollama.readthedocs.io][9])

---

# 2) Create the project

```bash
mkdir -p uipath-mock/{Templates/SupportClassify,Generators,Workflows,Data,Logs}
cd uipath-mock
python3 -m venv .venv
source .venv/bin/activate
```

Create **requirements.txt**:

```txt
jinja2
jsonschema
requests
typer
rich
```

Install deps:

```bash
pip install -r requirements.txt
```

* Jinja2 is the template engine we’ll use. ([Jinja Documentation][10])
* `jsonschema` validates model output strictly. ([Homebrew Documentation][6])

---

# 3) Add a prompt template + schema

Create `Templates/SupportClassify/template.yaml`:

```yaml
meta:
  name: support.ticket.classify
  version: 1.0.0
  owner: "<ORG>-AI"
  tags: [classification, support]
variables:
  product: {type: string, required: true}
  severity: {type: string, required: true, enum: ["low","medium","high"]}
  ticket_text: {type: string, required: true, min_len: 20}
system: |
  You are a precise support classifier. Output JSON only, matching the schema.
user: |
  Classify the ticket for product "{{ product }}" severity "{{ severity }}".
  Ticket:
  """{{ ticket_text }}"""
  Labels: ["billing","technical","account","abuse","feature_request"]
constraints:
  output_format: json
  schema_path: "schema.json"
  temperature: 0.1
```

Create `Templates/SupportClassify/schema.json`:

```json
{
  "type": "object",
  "required": ["label", "confidence"],
  "properties": {
    "label": { "type": "string", "enum": ["billing","technical","account","abuse","feature_request"] },
    "confidence": { "type": "number", "minimum": 0, "maximum": 1 }
  },
  "additionalProperties": false
}
```

Add a sample ticket in `Data/ticket.txt`:

```
I upgraded my subscription yesterday and I was charged twice on my card.
```

---

# 4) Add the code (3 tiny files)

### 4.1 `Generators/mapper_xaml.py` — turn JSON → mini XAML

```python
# Generators/mapper_xaml.py
import uuid

def to_xaml(result: dict) -> str:
    label = result["label"]
    return f'''<Activity x:Class="Autogen_{uuid.uuid4().hex}"
 xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
 xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
 xmlns:ui="http://schemas.uipath.com/workflow/activities">
  <Sequence>
    <ui:LogMessage Level="Info" Text="Auto-generated route: {label}" />
    <If>
      <If.Condition>[="{label}"="billing"]</If.Condition>
      <If.Then>
        <ui:LogMessage Level="Info" Text="Send to Billing Queue" />
      </If.Then>
      <If.Else>
        <ui:LogMessage Level="Info" Text="Send to {label} Queue" />
      </If.Else>
    </If>
  </Sequence>
</Activity>'''
```

> UiPath workflows are XAML under the hood, with UiPath activity namespaces—this lets you *mimic* that structure locally. You can open generated files in Studio later if you want. ([Visual Studio Code][5])

### 4.2 `Generators/stubs.py` — create tiny C# / JS helpers

```python
# Generators/stubs.py
def to_csharp(result: dict) -> str:
    label = result["label"]
    return f'''// Autogen helper
public static class Router {{
  public static string RouteTicket(dynamic ticket) {{
    var label = "{label}";
    return label == "billing" ? "BillingQueue" : $"{label}Queue";
  }}
}}'''

def to_js(result: dict) -> str:
    label = result["label"]
    return f'''export function routeTicket(ticket) {{
  const label = "{label}";
  return label === "billing" ? "BillingQueue" : label + "Queue";
}}'''
```

### 4.3 `main.py` — render prompt → call LLM → validate → generate files

```python
# main.py
import json, pathlib, time, uuid
from typing import Dict
import yaml, requests
from jsonschema import validate, ValidationError
from jinja2 import Environment, FileSystemLoader
import typer
from rich import print
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
    r = requests.post("http://localhost:11434/api/generate",
                      json={"model": model, "prompt": prompt, "stream": False},
                      timeout=120)
    r.raise_for_status()
    data = r.json()
    # many models output text; ensure it's pure JSON:
    text = data.get("response", "").strip()
    return json.loads(text)

@app.command()
def run(ticket_path: str = "Data/ticket.txt",
        product: str = "X",
        severity: str = "high",
        model: str = "mistral"):
    spec, schema, system, user = load_template()
    ticket_text = pathlib.Path(ticket_path).read_text().strip()

    sys_msg = system.render(product=product, severity=severity, ticket_text=ticket_text)
    user_msg = user.render(product=product, severity=severity, ticket_text=ticket_text)

    prompt = sys_msg + "\n\n" + user_msg
    t0 = time.time()
    out = call_ollama(model, prompt)
    latency = time.time() - t0

    # Validate against JSON Schema (reject bad outputs)
    try:
        validate(out, schema)
    except ValidationError as e:
        print("[red]Schema validation failed:[/red]", e)
        raise SystemExit(1)

    # Save artifacts
    run_id = uuid.uuid4().hex[:8]
    (ROOT/"Logs").mkdir(exist_ok=True)
    (ROOT/"Workflows").mkdir(exist_ok=True)
    (ROOT/"Workflows"/f"RouteTicket_{run_id}.xaml").write_text(to_xaml(out))
    (ROOT/"Workflows"/f"Router_{run_id}.cs").write_text(to_csharp(out))
    (ROOT/"Workflows"/f"router_{run_id}.js").write_text(to_js(out))
    (ROOT/"Logs"/f"result_{run_id}.json").write_text(json.dumps({"result": out, "latency_s": round(latency, 3)}, indent=2))

    print(f"[green]Done[/green] → label={out['label']} confidence={out['confidence']:.2f}  latency={latency:.2f}s")
    print("See Workflows/ and Logs/ for outputs.")

if __name__ == "__main__":
    app()
```

Why these libraries?

* **Jinja2** renders variables into your prompt. ([Jinja Documentation][11])
* **jsonschema** ensures the model **must** return correctly-shaped JSON. (This is your main guardrail.) ([Homebrew Documentation][6])
* **Ollama** gives you a local **POST `/api/generate`** endpoint so you can develop without cloud keys. ([ollama.readthedocs.io][9])

---

# 5) Run the mock Autopilot locally

With `ollama serve` running:

```bash
source .venv/bin/activate
python main.py --ticket_path Data/ticket.txt --product X --severity high --model mistral
```

You should see something like:

```
Done → label=billing confidence=0.81  latency=0.94s
See Workflows/ and Logs/ for outputs.
```

Open `Workflows/RouteTicket_*.xaml` in your editor to see the tiny, UiPath-style XAML your mapper created. (Real UiPath projects add dependencies and activities; here we just mimic the structure for learning.) ([Visual Studio Code][5])

---

# 6) (Optional) Use OpenAI/Azure instead of local Ollama

If you prefer a hosted model:

1. Get an API key (OpenAI/Azure OpenAI).
2. Replace `call_ollama` with a small OpenAI call using their Chat Completions API and still **validate with jsonschema**.
3. Keep outputs the same (JSON → XAML/C#/JS), so the rest of the pipeline doesn’t change.

(We stay local by default to avoid any blockers.)

---

# 7) Add a quick Robot-style task (optional)

If you’d like to play with open-source RPA later, you can install **Robot Framework** + **RPA Framework** (by Robocorp) and write a small robot to read the label and “route” it (e.g., move a file to a folder). It’s optional, but the docs are friendly and open source. ([RPA Framework][12], [Robot Framework Documentation][13])

---

# 8) Push to GitHub

**A. Initialize git locally**

```bash
git init
git add .
git commit -m "Initial mock Autopilot project (local LLM + schema + XAML generator)"
```

**B. Create an empty repo on GitHub (web UI)** and copy its URL, e.g. `https://github.com/<you>/uipath-mock.git`. ([GitHub Docs][14])

**C. Link and push**

```bash
git branch -M main
git remote add origin https://github.com/<you>/uipath-mock.git
git push -u origin main
```

(Official GitHub “add local code” guide if you need step-by-step.) ([GitHub Docs][15])

> Tip: you can also use **GitHub CLI** (`gh auth login`, `gh repo create`) if you like a guided flow in the terminal. ([GitHub Docs][16])

---

# 9) Try a different model or prompt

* Change `--model mistral` to another local model you pulled, e.g., `llama3:instruct` (pull it first). ([ollama.readthedocs.io][9])
* Edit the YAML template variables or labels, and re-run. Jinja will re-render with your new values. ([Jinja Documentation][11])

---

# 10) What you just learned (and why it maps to UiPath)

* **Templates + variables** (YAML + Jinja) → like prompt assets in a catalog. ([Jinja Documentation][11])
* **Schema-first outputs** (`jsonschema`) → guardrail to stop junk before it reaches a robot. ([Homebrew Documentation][6])
* **Mappers** that turn JSON → **XAML / C# / JS** → the bridge from LLM → automation surface (UiPath uses XAML under the hood). ([Visual Studio Code][5])
* **Local LLM API** (**Ollama**) so you can build, test, and demo without an external account. You still use an HTTP POST with a body—exactly like a cloud model. ([ollama.readthedocs.io][9])

---

## (Bonus) One-file smoke test

Create `Data/ticket_short.txt` with a very short sentence (e.g., “Help”). Run again. You’ll likely get a **schema validation error**. That’s good—your guardrail is working.

---

## (Bonus) Minimal README.md

```md
# uipath-mock

Local, open-source mock of an Autopilot-like flow:

- Template (YAML + Jinja)
- LLM call (Ollama or OpenAI/Azure)
- JSON Schema validation
- Generators → UiPath-style XAML + small C#/JS stubs

## Quickstart
brew install python git ollama
ollama serve
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py --ticket_path Data/ticket.txt --product X --severity high --model mistral
```

---

### Where to go next

* Add a **RAG** step (retrieve text from a local folder and pass as context).
* Add a **second template** (reply formatter) and chain steps.
* Add a **GitHub Action** that runs `python main.py` on every PR and fails if JSON schema breaks.
* Add a small **Robot Framework** task to “route” tickets by moving files (optional). ([RPA Framework][12])

If you want, I can package this as a GitHub template repo for you and include a basic CI workflow that runs the script and uploads `Workflows/` as an artifact.

[1]: https://brew.sh/?utm_source=chatgpt.com "Homebrew — The Missing Package Manager for macOS (or ..."
[2]: https://docs.brew.sh/Installation?utm_source=chatgpt.com "Installation — Homebrew Documentation"
[3]: https://git-scm.com/book/en/v2/Getting-Started-Installing-Git?adobe_mc=MCMID%3D53435949000300021972311465250106216512%7CMCORGID%3DA8833BC75245AF9E0A490D4D%2540AdobeOrg%7CTS%3D1736698927&utm_source=chatgpt.com "1.5 Getting Started - Installing Git"
[4]: https://www.theodinproject.com/lessons/foundations-setting-up-git?utm_source=chatgpt.com "Setting up Git"
[5]: https://code.visualstudio.com/docs/setup/mac?utm_source=chatgpt.com "Visual Studio Code on macOS"
[6]: https://docs.brew.sh/Homebrew-and-Python?utm_source=chatgpt.com "Python — Homebrew Documentation"
[7]: https://formulae.brew.sh/formula/ollama?utm_source=chatgpt.com "ollama — Homebrew Formulae"
[8]: https://www.postman.com/postman-student-programs/ollama-api/documentation/suc47x8/ollama-rest-api?utm_source=chatgpt.com "Ollama REST API | Documentation"
[9]: https://ollama.readthedocs.io/en/api/?utm_source=chatgpt.com "API Reference - Ollama English Documentation"
[10]: https://jinja.palletsprojects.com/?utm_source=chatgpt.com "Jinja — Jinja Documentation (3.1.x)"
[11]: https://jinja.palletsprojects.com/en/stable/templates/?utm_source=chatgpt.com "Template Designer Documentation"
[12]: https://rpaframework.org/?utm_source=chatgpt.com "RPA Framework — RPA Framework documentation"
[13]: https://docs.robotframework.org/docs/different_libraries/rpa?utm_source=chatgpt.com "RPA Framework"
[14]: https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository?utm_source=chatgpt.com "Creating a new repository"
[15]: https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github?utm_source=chatgpt.com "Adding locally hosted code to GitHub"
[16]: https://docs.github.com/en/github-cli/github-cli/quickstart?utm_source=chatgpt.com "GitHub CLI quickstart"

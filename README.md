## Autopilot-style mock (Ollama or LM Studio)

This small project takes a plain-text support ticket and automatically:

- Turns it into a structured JSON prediction (label + confidence)
- Checks that the JSON is valid using a strict schema
- Generates three tiny “automation” artifacts you could plug into a larger workflow: 
  - UiPath-style XAML file
  - A C# helper stub
  - A JS helper stub

It runs locally and can use either Ollama or LM Studio as the model provider.

### What happens when you run it
1) A prompt template and a JSON Schema are loaded from `Templates/SupportClassify/`.
2) Your ticket text is inserted into the prompt using Jinja templating.
3) The model is called (Ollama or LM Studio). With LM Studio, we also request structured output so the model returns valid JSON.
4) The JSON is validated against the schema. If it doesn’t match, the run stops with a clear error.
5) On success, the program writes:
   - `Workflows/RouteTicket_<id>.xaml` (mini UiPath-style workflow)
   - `Workflows/Router_<id>.cs` (C# stub)
   - `Workflows/router_<id>.js` (JS stub)
   - `Logs/result_<id>.json` (raw result + latency)

### Why this is useful
- **Consistency and safety**: bad model outputs are caught by the schema before they hit any automation.
- **Bridging to automation**: the generated XAML + stubs show how LLM output can drive a workflow.
- **Local-first**: no cloud keys needed. You can still swap providers later.

## Project layout
```
Templates/SupportClassify/
  template.yaml   # Jinja prompt template
  schema.json     # JSON Schema guardrail
Generators/
  mapper_xaml.py  # JSON → XAML
  stubs.py        # JSON → C# / JS
Data/
  ticket.txt      # example input
Logs/             # run logs
Workflows/        # generated artifacts
main.py           # CLI entrypoint
requirements.txt
```

## Quickstart (Ollama)
- `brew install python git ollama`
- `ollama serve`
- `python3 -m venv .venv && source .venv/bin/activate`
- `pip install -r requirements.txt`
- Run:
```bash
python main.py --provider ollama \
  --ticket_path Data/ticket.txt \
  --product X \
  --severity high \
  --model mistral
```

## Quickstart (LM Studio)
1) Start LM Studio’s local server (Developer tab → Status: Running) or CLI:
   - `npx lmstudio install-cli`
   - `lms server start`
2) Find your model id with: `curl http://localhost:1234/v1/models` (or your server URL)
3) Run (example uses a LAN host and a Qwen model id):
```bash
python main.py --provider lmstudio \
  --base-url http://192.168.100.81:3000/v1 \
  --model qwen2.5-coder-0.5b-instruct \
  --ticket-path Data/ticket.txt \
  --product X \
  --severity high
```

## How the schema guardrail works
- The schema in `Templates/SupportClassify/schema.json` defines the exact shape of the model’s JSON.
- If the result is missing a field, has an extra field, or the value is wrong (e.g., label not in the list), validation fails and the run stops.
- With LM Studio, the request asks the model to use the same schema as a “structured output” hint, improving the odds of a perfect JSON reply.

## Customize
- **Change labels**: edit `Templates/SupportClassify/template.yaml` (the label list and variables) and `schema.json` (the label enum) to match your categories.
- **Change model**:
  - Ollama: pull a model (e.g., `ollama pull llama3:instruct`) and pass `--model llama3:instruct`.
  - LM Studio: pick a model id from `GET /v1/models` and pass it via `--model`.
- **Try short/invalid tickets**: replace `Data/ticket.txt` with very short text to see schema validation in action.

## Troubleshooting
- **Cannot connect**:
  - Ollama: ensure `ollama serve` on `http://localhost:11434` is running.
  - LM Studio: ensure the server is running (Developer tab or `lms server start`) and your `--base-url` matches, e.g. `http://localhost:1234/v1` or your LAN host.
- **Model id not found**: the `--model` must appear in `GET /v1/models` for LM Studio.
- **Schema validation failed**: the model returned JSON that doesn’t match the schema. Re-run, switch models, or adjust the schema and labels.
- **Imports fail**: run from the project root and activate the venv: `source .venv/bin/activate`.

## Notes
- All processing is local to your machine when using Ollama or LM Studio.
- The generated XAML is a minimal, UiPath-style structure for learning/demonstration.




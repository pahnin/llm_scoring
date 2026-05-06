# LLM Benchmark Suite

This repository contains a Bash script (`score_llms.sh`) designed to run a small set of qualitative benchmark prompts against a variety of locally-hosted Large Language Models (LLMs) accessed via OLLAMA. The goal is to compare how each model performs on a handful of real-world coding and reasoning tasks and to collect both raw responses and simple latency/token statistics.

## Project Overview

The benchmark evaluates LLMs across 5 distinct problems, measuring their ability to generate coherent and correct responses.

### Project Layout
This repository contains a simple Bash script that runs a small set of qualitative benchmark prompts against a variety of locally‑hosted LLMs (via OLLAMA).  The goal is to compare how each model performs on a handful of real‑world coding and reasoning tasks and to collect both raw responses and simple latency/token statistics.
├── bench/
## Project layout
│   └── <timestamp>/      # Directory for each benchmark session (e.g., results/1777977547/)
```
├── bench
│   └── prompts          # .txt files – one per benchmark problem
├── results                # per‑run JSON output + metrics.csv
│   └── <timestamp>/      # a directory per benchmark session
├── score_llms.sh          # driver script
└── README.md              # you are reading
```
2.  **Results Directory (`results/<timestamp>/`):** Contains all output for a single benchmark run.
- `bench/prompts/*.txt` – a problem description.  The script will send the file content as a user message.
- `results/<timestamp>/metrics.csv` – one row per run with *model, problem, run, latency, tokens, success, http_code*.
- `results/<timestamp>/*.json` – the raw streamed response for each run.  The JSON contains two keys:
  ```json
  {
    "content": "…",          // the decoded LLM reply
    "usage": {"total_tokens": 123}
  }
  ```

## Prerequisites

- Bash (any recent version)
- `curl` and `jq` installed
- OLLAMA running locally (default port 11434).  Set the environment variable `OLLAMA_URL` if you use a different address.

## Running the benchmark

```bash
# From the repository root
bash score_llms.sh
```

The script will:
1. Warm‑up each model.
2. Iterate over every prompt.
3. Run each prompt *RUNS* times (default = 3) and capture latency, token usage and raw response.
4. Store all results under `results/<unix‑timestamp>/`.

You can customize the list of models or the number of runs by editing the top of `score_llms.sh`.

## Qualitative comparison

1. **Open the JSON files** – they are small, human‑readable, and contain the actual text produced by the model.
   ```bash
   jq -r '.content' results/1777977547/deepseek-coder-v2_16b_problem1_run1.json
   ```
2. **Compare side‑by‑side** – use `diff`, `colordiff`, or any diff viewer to spot differences between runs or between models.
3. **Look at the `usage.total_tokens`** – gives an idea of how verbose each model was.
4. **Cross‑reference with `metrics.csv`** – check latency and success flags.

### Quick‑look script
You can generate a quick table of responses for a single problem:

```bash
#!/usr/bin/env bash
PROBLEM=problem1
for MODEL in $(ls results/1777977547 | grep "_${PROBLEM}_run1.json" | sed 's/_run1.json//'); do
  echo -e "\n=== $MODEL ==="
  jq -r '.content' results/1777977547/${MODEL}_${PROBLEM}_run1.json
done
```

## Hardware

All results in this repo were produced on an **RTX 5060 TI** with **16 GB VRAM**.  Performance may differ on other GPUs or CPU‑only setups.

## License

MIT – feel free to adapt or extend.

  jq -r '.content' results/$TIMESTAMP/"$MODEL"_$PROBLEM_run1.json
done
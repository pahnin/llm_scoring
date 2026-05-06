#!/usr/bin/env bash

set -euo pipefail

OLLAMA_URL="http://localhost:11434/v1/chat/completions"

MODELS=(
  "qwen3.5:9b"
  "qwen3.6:27b"
  "ministral-3:14b"
  "deepseek-coder-v2:16b"
  "devstral-small-2:24b"
  "gemma4:e2b"
)

PROMPT_DIR="bench/prompts"
RUNS=3
TIMEOUT=180

DAT="$(date +%s)"
OUTPUT_DIR="results/${DAT}"
mkdir -p "$OUTPUT_DIR"

CSV_FILE="$OUTPUT_DIR/metrics.csv"
echo "model,problem,run,latency_ms,tokens,success,http_code" > "$CSV_FILE"

# -------------------------
# helpers
# -------------------------

json_escape() {
  jq -Rs .
}

warmup_model() {
  local model="$1"
  echo "Warming up $model..."
  curl --silent --show-error --max-time 30 \
    "$OLLAMA_URL" \
    -H "Content-Type: application/json" \
    -d @- > /dev/null <<EOF || true
{
  "model": "$model",
  "messages": [
    {"role": "user", "content": "hi"}
  ],
  "temperature": 0,
  "max_tokens": 1,
  "stream": false
}
EOF
}

run_single() {
  local model="$1"
  local problem="$2"
  local prompt_file="$3"
  local run_id="$4"

  local prompt
  prompt=$(cat "$prompt_file" | json_escape)

  local start end latency response out_file tokens success http_code

  start=$(date +%s%3N)
  response=""
  tokens=0
  success=0
  http_code=200

  # -------------------------
  # Streaming request
  # -------------------------
  while IFS= read -r line; do
    # Skip empty lines
    [[ -z "$line" ]] && continue

    # SSE style: each line may start with "data: "
    if [[ "$line" == data:\ * ]]; then
      data="${line#data: }"
      [[ "$data" == "[DONE]" ]] && break

      # Extract token content if available
      delta=$(echo "$data" | jq -r '.choices[0].delta.content // empty' 2>/dev/null || true)
      [[ -n "$delta" ]] && response+="$delta"

      # Extract token count if available
      tk=$(echo "$data" | jq -r '.usage.total_tokens // empty' 2>/dev/null || true)
      [[ -n "$tk" ]] && tokens="$tk"
    fi
  done < <(
    curl --no-buffer --silent --show-error --max-time "$TIMEOUT" \
      -H "Content-Type: application/json" \
      -d @- \
      "$OLLAMA_URL"  <<EOF
{
  "model": "$model",
  "messages": [
    {
      "role": "system",
      "content": "You are a strict senior code reviewer. Be as concise as possible. Find real bugs, not style issues."
    },
    {
      "role": "user",
      "content": $prompt
    }
  ],
  "temperature": 0.5,
  "stream": true
}
EOF
  )

  end=$(date +%s%3N)
  latency=$((end - start))

  # Save streamed output
  out_file="$OUTPUT_DIR/${model//[:]/_}_${problem}_run${run_id}.json"
  echo "{\"content\": $(echo "$response" | jq -Rs .), \"usage\": {\"total_tokens\": $tokens}}" > "$out_file"

  # Mark success if we received content
  [[ -n "$response" ]] && success=1

  echo "$model,$problem,$run_id,$latency,$tokens,$success,$http_code" >> "$CSV_FILE"
  echo "  Run $run_id → ${latency} ms (tokens=$tokens, ok=$success)"
}

# -------------------------
# main
# -------------------------

for model in "${MODELS[@]}"; do
  echo "=============================="
  echo "MODEL: $model"

  warmup_model "$model"

  for prompt_file in "$PROMPT_DIR"/*.txt; do
    problem=$(basename "$prompt_file" .txt)
    echo " Problem: $problem"

    for ((i=1; i<=RUNS; i++)); do
      run_single "$model" "$problem" "$prompt_file" "$i"
    done
  done
done

echo "Done. Results in $OUTPUT_DIR"

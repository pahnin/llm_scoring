#!/usr/bin/env bash

OLLAMA_URL="http://localhost:11434/v1/chat/completions"

MODELS=(
  "qwen3.5:2b"
  "qwen3.5:9b"
  "qwen3.6:27b"
  "llama3:8b"
  "deepseek-r1:14b"
)

PROMPT_DIR="prompts"
OUTPUT_DIR="results"

mkdir -p "$OUTPUT_DIR"

RUNS=3

# CSV header
echo "model,problem,run,latency_ms,tokens" > "$OUTPUT_DIR/metrics.csv"

warmup_model () {
  local model=$1
  echo "Warming up $model..."

  curl -s $OLLAMA_URL \
    -H "Content-Type: application/json" \
    -d @- <<EOF > /dev/null
{
  "model": "$model",
  "messages": [
    {"role": "user", "content": "ready"}
  ],
  "stream": false
}
EOF

  sleep 1
}

run_single () {
  local model=$1
  local problem_name=$2
  local prompt_file=$3
  local run_id=$4

  START=$(date +%s%3N)

  RESPONSE=$(curl -s $OLLAMA_URL \
    -H "Content-Type: application/json" \
    -d @- <<EOF
{
  "model": "$model",
  "messages": [
    {"role": "system", "content": "You are a strict senior code reviewer. Find real bugs, not style issues."},
    {"role": "user", "content": "$(sed 's/"/\\"/g' $prompt_file)"}
  ],
  "stream": false,
  "temperature": 0.2
}
EOF
)

  END=$(date +%s%3N)
  LATENCY=$((END - START))

  TOKENS=$(echo "$RESPONSE" | jq '.usage.total_tokens // 0')

  # Save output
  OUT_FILE="$OUTPUT_DIR/${model//[:]/_}_${problem_name}_run${run_id}.json"
  echo "$RESPONSE" > "$OUT_FILE"

  echo "$model,$problem_name,$run_id,$LATENCY,$TOKENS" >> "$OUTPUT_DIR/metrics.csv"

  echo "  Run $run_id → ${LATENCY} ms"
}

# MAIN LOOP
for model in "${MODELS[@]}"; do
  echo "=============================="
  echo "MODEL: $model"

  warmup_model "$model"

  for prompt_file in "$PROMPT_DIR"/*.txt; do
    problem_name=$(basename "$prompt_file" .txt)

    echo " Problem: $problem_name"

    for ((i=1;i<=RUNS;i++)); do
      run_single "$model" "$problem_name" "$prompt_file" "$i"
    done
  done
done

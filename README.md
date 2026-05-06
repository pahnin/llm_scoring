LLM Benchmark Suite

This project evaluates how well different locally-run AI models (LLMs) solve real-world coding and debugging problems.

Instead of just measuring speed or token usage, it focuses on something more important:

👉 Did the model actually understand the problem and give a correct, consistent answer?

🎯 What This Benchmark Measures

Each model is tested on 5 practical programming problems (debugging, async bugs, API mismatches, etc.).

For every response, we evaluate:

1. ✅ Task Completion (Accuracy)
Did the model identify the actual bugs?
Did it explain why they happen?
Did it suggest correct fixes?

This is the most important signal.

2. 🔁 Consistency
If we ask the same question 3 times…
Does the model give similar quality answers, or does it fluctuate?

High consistency = reliable model
Low consistency = unpredictable model

3. 🧠 Uniqueness (Reasoning Depth)
Does the model produce meaningful insights, or repeat generic patterns?
Measures diversity of useful “facts” extracted from answers
4. 🤝 Agreement (Optional Signal)
Do multiple models agree on the same facts?
Helps detect widely “correct” reasoning patterns
🧮 Final Score Formula

Each model gets a combined score:

Final Score =
  50% Task Completion (accuracy)
+ 30% Consistency
+ 15% Uniqueness
+  5% Agreement

👉 This heavily favors correctness + reliability, not verbosity.

📊 Latest Results
Model                          | Tot | Uniq | U%   | Cons | C%   | Score
--------------------------------------------------------------------------------
ministral-3_14b                | 139 |   72 | 0.518 | 0.383 | 0.934 | 0.586
gemma4_e2b                     | 115 |   58 | 0.504 | 0.311 | 0.892 | 0.534
devstral-small-2_24b           | 127 |   51 | 0.402 | 0.303 | 0.720 | 0.468
deepseek-coder-v2_16b          | 133 |   67 | 0.504 | 0.191 | 0.812 | 0.450
qwen3.5_9b                     | 169 |   66 | 0.391 | 0.112 | 0.810 | 0.389
🧾 How to Read This Table
Tot → Total reasoning facts extracted from answers
Uniq → Unique facts (less repetition = better reasoning)
U% → Uniqueness ratio
Cons → Stability across runs (higher = more reliable)
C% → Agreement with other models
Score → Final weighted score
🔍 Key Takeaways
🥇 ministral-3_14b
Best overall performer
Strong balance of correctness + consistency
Most reliable for real-world use
🥈 gemma4_e2b
Very good accuracy
Slightly less consistent
Strong alternative
🥉 devstral-small-2_24b
Good but uneven
High variance across runs
⚖️ deepseek-coder-v2_16b
Produces rich insights (high uniqueness)
But inconsistent, which hurts reliability
⚠️ qwen3.5_9b
Generates lots of output
But low consistency and weaker correctness signals
⚠️ Important Notes
This is a small benchmark (5 problems) — results are directional, not absolute
Scoring uses heuristics + fuzzy matching, not perfect grading
Models are evaluated on reasoning quality, not just output length
▶️ How to Run
bash score_llms.sh
python build_kg.py

This will:

Run all models on all problems
Store raw outputs in results/
Build a knowledge graph of extracted facts
Generate rankings
📂 Project Structure
bench/prompts/        → Benchmark problems
results/<timestamp>/  → Raw model outputs
metrics.csv           → Latency + token stats
build_kg.py           → Scoring + ranking engine
🧠 Why This Approach?

Most benchmarks measure:

Speed
Tokens
Perplexity

This project instead measures:

👉 “Would I trust this model to debug real code?”

📌 Future Improvements
Better semantic matching (embeddings instead of keywords)
Per-problem scoring breakdown
Automatic ground-truth validation
Larger benchmark set
License

MIT – feel free to adapt or extend.



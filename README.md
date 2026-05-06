# LLM Benchmark Suite

This project evaluates how well different locally-run AI models (LLMs) solve real-world coding and debugging problems.

Instead of just measuring speed or token usage, it focuses on something more important:

👉 **Did the model actually understand the problem and give a correct, consistent answer?**

---

## 🎯 What This Benchmark Measures
On RTX 5060 TI 16 GB
Each model is tested on 5 practical programming problems (debugging, async bugs, API mismatches, etc.).
Feel free to run this on your GPU and update the problems if you like

For every response, we evaluate:

### 1. ✅ Task Completion (Accuracy)
- Did the model identify the actual bugs?
- Did it explain why they happen?
- Did it suggest correct fixes?

**This is the most important signal.**

---

### 2. 🔁 Consistency
- If we ask the same question 3 times…
- Does the model give similar quality answers, or does it fluctuate?

- High consistency = reliable model  
- Low consistency = unpredictable model  

---

### 3. 🧠 Uniqueness (Reasoning Depth)
- Does the model produce meaningful insights, or repeat generic patterns?
- Measures diversity of useful “facts” extracted from answers  

---

### 4. 🤝 Agreement (Optional Signal)
- Do multiple models agree on the same facts?
- Helps detect widely “correct” reasoning patterns  

---

## 🧮 Final Score Formula

Each model gets a combined score:


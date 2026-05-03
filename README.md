<div align="center">

# 🤖 Autonomous SRE Agent

### Self-Healing, Policy-Aware AI System for Kubernetes Operations

Detect → Diagnose → Decide → Enforce → Execute → Learn

<br/>

<img src="https://img.shields.io/badge/status-active-brightgreen?style=flat-square" />
<img src="https://img.shields.io/badge/python-3.11+-blue?style=flat-square&logo=python" />
<img src="https://img.shields.io/badge/kubernetes-k3s-326CE5?style=flat-square&logo=kubernetes" />
<img src="https://img.shields.io/badge/LLM-Groq%20%7C%20Llama%203.1-orange?style=flat-square" />
<img src="https://img.shields.io/badge/policy-OPA%20%2B%20Rego-purple?style=flat-square" />

<br/><br/>

🚨 **Your AI On-Call Engineer for Kubernetes**

</div>

---

## 🧠 What This Project Does

Modern SRE teams struggle with:
- Alert fatigue
- Slow incident resolution
- Non-scalable runbooks

This project solves that.

> **Autonomous SRE Agent is a multi-agent AI system that monitors your cluster, diagnoses failures, makes decisions, and safely executes fixes — automatically.**

---

## ⚡ Core Idea

Instead of humans reacting to alerts:

```

Metrics → AI → Decision → Policy → Action → Learning

```

This system:
- detects anomalies via Prometheus  
- diagnoses root cause using LLM  
- evaluates actions with risk scoring  
- enforces policies using OPA  
- executes fixes on Kubernetes  
- learns from every incident  

---

## 🧱 System Architecture

<img width="2816" height="1536" alt="Gemini_Generated_Image_54tjdc54tjdc54tj" src="https://github.com/user-attachments/assets/fa2c101b-9dff-472e-b403-515a071b1eb2" />

```
Prometheus → Monitor → Diagnose (LLM) → Decision Engine
↓
Memory (ChromaDB + Redis) ← Execute ← Policy (OPA)

````

---

## 🔥 Key Features

### 🔍 Intelligent Monitoring
- Detects:
  - CrashLoopBackOff
  - OOMKilled
  - CPU spikes
  - Memory pressure

---

### 🧠 AI Root Cause Analysis
- Powered by **Groq (Llama 3.1)**
- Uses **RAG with past incidents**
- Returns:
  - root cause
  - confidence score

---

### ⚖️ Decision Engine
- Generates multiple possible fixes
- Ranks by:
  - risk
  - confidence
  - effectiveness

---

### 🛡️ Policy Enforcement (Safety Layer)
- Open Policy Agent (OPA)
- Prevents unsafe actions
- Example:
  - ❌ Block production auto-actions
  - ❌ Block low-confidence fixes

---

### ⚙️ Autonomous Execution
- Kubernetes-native actions:
  - restart deployment
  - delete pod
  - scale services

---

### 💾 Self-Learning Memory
- ChromaDB → long-term memory
- Redis → short-term state
- Enables:
  - incident similarity search
  - improved future decisions

---

### 🖥️ Control Plane Dashboard
- Live anomaly feed
- Pipeline execution tracking
- Policy decisions
- Cluster health

---

## ⚙️ Tech Stack

| Layer | Tech |
|------|------|
| AI | Groq (Llama 3.1), RAG |
| Orchestration | LangGraph |
| Backend | FastAPI |
| Policy | Open Policy Agent (Rego) |
| Memory | ChromaDB + Redis |
| Infra | Kubernetes (k3s) |
| Observability | Prometheus + Grafana |
| Containers | Docker |

---

## 🚀 Quick Start

```bash
git clone https://github.com/AyaanShaheer/autonomous-sre-agent.git
cd autonomous-sre-agent

cp .env.example .env
# Add your GROQ_API_KEY
````

### Start services

```bash
docker-compose up -d
```

### Run API

```bash
uvicorn api.main:app --reload
```

---

## 🧪 Example Flow

```
🚨 Detected: CrashLoopBackOff

🧠 Diagnosis:
OOMKilled — insufficient memory (confidence: 88%)

⚖️ Decision:
restart_deployment (risk: medium)

🛡️ Policy:
ALLOW (staging environment)

⚙️ Execution:
Restart deployment

💾 Learning:
Incident stored for future use
```

---

## 📊 Why This Project Matters

This is not a demo.

This is a **real-world system design project** demonstrating:

* Multi-agent AI systems
* AI + DevOps integration
* Production safety via policy engines
* Autonomous decision-making systems
* End-to-end infra + backend + AI

---

## 🧠 Design Philosophy

### ❗ AI ≠ Autonomous Without Control

This system enforces:

* Policy constraints
* Confidence thresholds
* Human-in-the-loop for production

---

### ⚖️ Tradeoffs

| Decision        | Why                      |
| --------------- | ------------------------ |
| LLM over rules  | Handles unknown failures |
| OPA layer       | Hard safety boundary     |
| Groq API        | Speed + reliability      |
| Dry-run default | Safe experimentation     |

---

## 🗺️ Roadmap

* [x] Multi-agent pipeline
* [x] LLM diagnosis
* [x] Policy enforcement
* [x] Kubernetes execution
* [x] Memory layer
* [ ] Cloud deployment
* [ ] Multi-cluster support
* [ ] SaaS API

---

## 🤝 Contributing

PRs welcome.

If you're into:

* AI agents
* DevOps automation
* distributed systems

This repo is for you.

---

## 👨‍💻 Author

**Ayaan Shaheer**

Building AI-native infrastructure systems.

---

<div align="center">

⭐ Star this repo if you found it interesting

</div>


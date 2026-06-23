# 📈 Finsight: AI Financial Research Assistant

## Overview

Finsight is a Retrieval-Augmented Generation (RAG) powered financial intelligence platform that enables investors and analysts to query and analyze quarterly earnings call transcripts from leading companies such as Meta, NVIDIA, and Microsoft.

The system combines semantic search, vector databases, and Large Language Models (LLMs) to provide accurate, citation-backed answers grounded in company earnings discussions and financial disclosures.

---

## Features

* 📄 Automated ingestion of earnings call transcripts and financial documents
* ✂️ Intelligent document chunking and preprocessing
* 🔍 Hybrid retrieval using semantic vector search and keyword matching
* 🧠 Context-aware question answering with Hugging Face LLMs
* 📚 Source-grounded responses with document citations
* 📊 Analysis of quarter-over-quarter company performance
* 💬 Interactive Streamlit-based chat interface
* ⚡ Local-first architecture with no dependency on external APIs

---

## Architecture

```text
Financial Reports / Earnings Call Transcripts
                    │
                    ▼
            Document Loader
                    │
                    ▼
           Text Chunking Layer
                    │
                    ▼
          BGE-M3 Embeddings
                    │
                    ▼
          Chroma Vector Store
                    │
                    ▼
      Hybrid Retrieval (MMR)
                    │
                    ▼
        Context Construction
                    │
                    ▼
        Hugging Face LLM
                    │
                    ▼
      Citation-Backed Answers
                    │
                    ▼
          Streamlit Frontend
```

---

## Tech Stack

### AI & Machine Learning

* LangChain
* Hugging Face Transformers
* BAAI/bge-m3 Embeddings
* Qwen/Qwen2.5-0.5B-Instruct / Hugging Face LLMs

### Vector Database

* ChromaDB

### Data Processing

* PyMuPDF (fitz)
* RecursiveCharacterTextSplitter

### Frontend

* Streamlit

### Programming Language

* Python 3.11

---

## Results & Evaluation

Hybrid Retrieval Performance

| Metric                     | Score  |
| -------------------------- | ------ |
| Precision@K                | 74.29% |
| Hit@K                      | 88.89% |
| Mean Reciprocal Rank (MRR) | 0.857  |
| Keyword Recall@K           | 100%   |

### Key Insights

* Achieved perfect keyword recall across evaluation queries.
* High MRR indicates relevant chunks are consistently ranked near the top.
* Strong retrieval accuracy for earnings-call-specific financial questions.
* Improved answer grounding through hybrid retrieval and citation-based responses.

---

## Installation

### 1. Clone Repository

```bash
git clone https://github.com/ankur1902/finsight.git
cd finsight
```

### 2. Create Virtual Environment

```bash
python -m venv .venv
```

Activate:

Windows

```bash
.venv\Scripts\activate
```

Mac/Linux

```bash
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Add Documents

Place earnings call transcripts or financial reports inside:

```text
data/
```

Example:

```text
data/
├── meta-Q1-2025.pdf
├── nvidia-Q4-2025.pdf
└── microsoft-Q2-2025.pdf
```

### 5. Build Vector Database

```bash
python -m src.main
```

### 6. Launch Application

```bash
streamlit run app.py
```

---

## Example Questions

* How did NVIDIA's data center revenue change this quarter?
* What risks did Meta management highlight during the earnings call?
* Compare Microsoft's AI investments across recent quarters.
* What guidance did management provide for next quarter?
* Summarize key business highlights from the latest earnings call.

---



## Author

Ankur Singh

Built as a Retrieval-Augmented Generation (RAG) system for financial intelligence and earnings call analysis.

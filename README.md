# DataCleaner Agent

Agentic data-quality application built with Streamlit, LangGraph, Groq and Pandas.

## Supported files
- CSV
- XLSX
- XLS

## Main flow
1. Upload a dataset.
2. Pandas profiles the complete tabular dataset.
3. A LangGraph agent powered by Groq chooses local tools dynamically.
4. The agent can use Browser Search only when an external factual reference is actually useful.
5. The agent submits a structured cleaning plan.
6. The user reviews every proposed action.
7. A deterministic allow-listed Pandas cleaning engine applies only selected actions.
8. The result can be exported as CSV or Excel.

## Install on Windows PowerShell
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```
Edit `.env` and set `GROQ_API_KEY`.

Run:
```powershell


```

## Important design choice
The LLM never executes arbitrary generated Python. It can only propose actions from the cleaning engine allow-list.

# AI Text-to-SQL (with a clarification engine)

Upload a CSV / Excel / TSV / JSON file, ask questions in plain English, get answers in plain English.

## Run

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env  -> then add your GROQ_API_KEY
streamlit run app.py
```

Try it with `sample_data/employees.csv`: "What is the average salary of all employees?"

## Pipeline

upload -> file_handler -> data_processor (clean names/types/dates) -> SQLite (in memory, read-only)
-> schema_analyzer -> **clarification_engine** (ask only if truly ambiguous)
-> sql_generator -> sql_validator -> query_executor (self-repairs on error) -> response_generator

## Tests

```bash
pytest
```

# Contributing to Ghost Records 👻

Thank you for your interest in contributing to **Ghost Records**! We welcome contributions from developers, data engineers, security researchers, and UI designers.

Ghost Records is an open-source, local-first data quality auditor designed to run 100% on local hardware using deterministic Python validation rules and local open-weight LLMs (Ollama + Gemma).

---

## Code of Conduct

We are committed to providing a welcoming, inclusive, and harassment-free environment for everyone. Please be respectful and constructive in all discussions, pull requests, and issue reports.

---

## Ways to Contribute

### 1. Add New Detection Rules
New rules can be implemented in `ghost_records/scanner.py`. Every rule must:
- Be deterministic, independently testable, and isolated in a dedicated function.
- Generate a stable finding ID using `_generate_finding_id`.
- Never invent data or assume business semantics without configuration.
- Return structured evidence matching the `Finding` dataclass.
- Include automated unit tests in `tests/`.

### 2. Add Database Adapters
Ghost Records currently audits CSV files and SQLite databases in read-only mode.
Planned adapters include:
- PostgreSQL read-only adapter
- DuckDB local parquet/arrow adapter
- MySQL read-only adapter

When implementing a database adapter, ensure:
- Connections are strictly read-only (`mode=ro`).
- Queries use parameterized SQL to prevent SQL injection.
- Remediation never modifies the source database; transformations apply only to derived copies.

### 3. Improve Local Model Prompts
Prompt templates live in `ghost_records/ai/prompts.py`.
Guidelines for prompts:
- Keep evidence payloads minimal and bounded to respect context limits.
- Never send raw confidential columns (e.g. passwords, SSNs, unrelated fields).
- Enforce strict negative constraints: model must not invent replacement values or claim external database lookups.
- Maintain Pydantic JSON schema compatibility (`ghost_records/ai/schemas.py`).

### 4. Improve UI & Visual Experience
The user interface is built with Streamlit and custom CSS located in `ghost_records/ui_utils.py`.
- Maintain the **dark forensic workspace** aesthetic.
- Color conventions:
  - Critical: `#f85149` (restrained red)
  - High: `#f0883e` (amber-orange)
  - Medium: `#d97706` (muted gold)
  - Low: `#58a6ff` (calm blue)
  - Info: `#8b949e` (cool slate)
  - Success: `#3fb950` (muted green)

### 5. Add Unit and Integration Tests
Add test cases in `tests/`:
- `tests/test_duplicates.py`
- `tests/test_foreign_keys.py`
- `tests/test_profiling.py`
- `tests/test_remediation.py`
- `tests/test_reporting.py`
- `tests/test_ai_client.py`

Run all tests locally with:
```bash
python -m pytest -v
```

Lint and format code before committing:
```bash
python -m ruff check --fix ghost_records tests pages app.py
```

---

## Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yashr5120/Ghost-Records.git
   cd Ghost-Records
   ```

2. **Set up a virtual environment (Python 3.11+):**
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Start local Ollama (Optional for deterministic tests, required for AI explanations):**
   ```bash
   ollama serve
   ollama list
   ```

5. **Run the Streamlit application:**
   ```bash
   streamlit run app.py
   ```

---

## Submitting Pull Requests

1. Fork the repo and create a descriptive branch: `git checkout -b feature/new-validation-rule`.
2. Commit your changes with clear commit messages.
3. Verify that all 17+ automated tests pass: `python -m pytest -v`.
4. Run `ruff` linting: `python -m ruff check ghost_records tests pages app.py`.
5. Open a Pull Request describing:
   - The problem being solved.
   - Ground-truth evaluation or sample data used.
   - Any new configuration options added.

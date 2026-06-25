# Auto Prompter

Sends prompts to the `claude` CLI on a schedule (one-time or recurring),
targeting a new chat in a chosen folder or an existing discovered chat.
Cross-platform (Linux/macOS/Windows). No answer-parsing — it only sends.

## Requirements
- Python 3.9+
- The `claude` CLI installed and on PATH (`claude --version` should work)

## Setup
```bash
python -m venv venv
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate
pip install -r requirements.txt
```

## Run
```bash
python app.py
```
Open http://localhost:5000.

**Note:** prompts fire only while `python app.py` is running.

## Tests
```bash
pytest
```

# Himagent - Automated Test Plan Generation

This project generates comprehensive, structured Excel-based test plans (`.xlsx` files) from the Flask web application.

## Prerequisites

Ensure you have Python 3 installed. Install the required libraries:

```bash
pip install flask openpyxl Pillow google-generativeai pydantic
```

## How to Run

### 1. Web-based Generator (Flask App)
Start the local Flask server to run the interactive generator:

```bash
python app.py
```
Open your web browser and navigate to:
```
http://localhost:5000
```

### 2. Generate Test Plans
Use the web application to generate and download test plan spreadsheets. Python recreate scripts are optional and off by default.

## Generated Artifacts
Generated files are saved under the `outputs/` directory, grouped by module.

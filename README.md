# Himagent - Automated Test Plan Generation

This project generates comprehensive, structured Excel-based test plans (`.xlsx` files) and self-contained Python scripts for web application modules.

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

### 2. Standalone Test Plan Generators
To run the pre-built generators directly and output the styled `.xlsx` spreadsheets:

```bash
# Create Project Module
python testplan_createProject.py

# AI Image Generator Module
python testplan_imageGen.py

# AI Video Generator Module
python testplan_videoGen.py
```

## Generated Artifacts
Running the scripts above will generate the following Excel spreadsheets in the root directory:
* `testplan_createProject.xlsx`
* `testplan_imageGen.xlsx`
* `testplan_videoGen.xlsx`

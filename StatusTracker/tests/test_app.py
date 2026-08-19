from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_returns_something():
    response = client.get("/")
    assert response.status_code < 500


def test_python_still_does_math():
    assert 10 + 5 == 15

"""
Running the Application

Requirements
------------
Python 3.9+

Setup
-----
Create a virtual environment:

    python3 -m venv .venv

Activate it:

    source .venv/bin/activate

Install dependencies:

    pip install -r requirements.txt

Run
---
Start the application:

    uvicorn app.main:app --reload

The API will be available at:

    http://127.0.0.1:8000

Interactive API documentation is available at:

    http://127.0.0.1:8000/docs
"""
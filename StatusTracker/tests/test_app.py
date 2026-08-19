from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

def test_root_returns_something():
    response = client.get("/")
    assert response.status_code < 500

def test_create_task():
    response = client.post("/tasks", json={"title": "Test Task", "description": "Test Description"})
    assert response.status_code == 201

# def test_get_task():
#     response = client.get("/tasks/x") # TODO: Get the task id from the database and replace x with the id
#     assert response.status_code == 200

def test_update_task():
    response = client.put("/tasks/1", json={"title": "Updated Task", "description": "Updated Description"})
    assert response.status_code == 200

def test_delete_task():
    response = client.delete("/tasks/1")
    assert response.status_code == 204

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
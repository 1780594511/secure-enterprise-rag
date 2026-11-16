"""Run from the repository root after starting the application."""

import httpx

with httpx.Client(base_url="http://127.0.0.1:8781/api", headers={"X-RAG-Request": "1"}) as client:
    client.post("/login", json={"username": "employee", "password": "Orchid-Demo-26"}).raise_for_status()
    response = client.post("/query", json={"question": "访客登记点在哪里？"})
    response.raise_for_status()
    result = response.json()
    print(result["answer"])
    for source in result["refs"]:
        detail = client.get("/references/" + source["id"])
        detail.raise_for_status()
        print(source["id"], detail.json()["body"])
    client.post("/logout").raise_for_status()

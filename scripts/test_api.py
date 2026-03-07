import requests

def test_api():
    url = "http://localhost:8000/api/v1/chat"
    payload = {
        "user_id": "b323bd39-7359-42b7-8ce6-a6fc1209b52c",
        "message": "Em học trường nào?"
    }
    try:
        response = requests.post(url, json=payload, timeout=20)
        print("Status:", response.status_code)
        print("Response:", response.text)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_api()

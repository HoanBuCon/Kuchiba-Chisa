"""Interactive terminal chat against a running Chisa API (development tool).

The script never writes users or accounts into the database. It obtains a
server-minted anonymous web session from ``/api/v1/auth/anonymous-session`` exactly
like the browser does, so it exercises the real identity boundary and leaves no
pre-seeded test account behind.
"""

import asyncio
import os

import httpx

API_BASE = os.environ.get("CHISA_API_BASE", "http://localhost:8000/api/v1")


async def main() -> None:
    print("========================================")
    print("🌸 CHISA AI - INTERACTIVE TERMINAL CHAT 🌸")
    print("========================================\n")
    print("[*] Type 'quit' or 'exit' to stop, '/clear' to erase this session's memory.\n")

    async with httpx.AsyncClient(timeout=120.0) as client:
        session = await client.post(f"{API_BASE}/auth/anonymous-session")
        session.raise_for_status()
        data = session.json()
        headers = {"Authorization": f"Bearer {data['access_token']}"}
        subject_id = data["subject_id"]
        print("[*] Anonymous session established (no database account created).\n")

        while True:
            try:
                user_input = input("👤 You: ")
                if user_input.lower() in ("quit", "exit"):
                    print("\n🌸 Chisa: Goodbye! See you next time~")
                    break
                if not user_input.strip():
                    continue
                if user_input.strip() == "/clear":
                    cleared = await client.delete(
                        f"{API_BASE}/chat/clear/{subject_id}", headers=headers
                    )
                    print(f"[*] Clear status: HTTP {cleared.status_code}\n")
                    continue

                response = await client.post(
                    f"{API_BASE}/chat", json={"message": user_input}, headers=headers
                )
                response.raise_for_status()
                print(f"🤖 Chisa: {response.json()['response']}\n")
            except httpx.HTTPStatusError as error:
                print(f"\n❌ API Error: HTTP {error.response.status_code}\n")
            except httpx.RequestError:
                print("\n❌ Connection Error: is the API server running?\n")
            except KeyboardInterrupt:
                print("\n\n🌸 Chisa: Interrupted! Goodbye~")
                break


if __name__ == "__main__":
    asyncio.run(main())

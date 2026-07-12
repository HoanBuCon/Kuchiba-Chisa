import httpx
import urllib.parse
import json

async def test_fandom_search(query: str):
    url = "https://wutheringwaves.fandom.com/api.php"
    
    # Step 1: Search by title first
    search_params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 3,
        "srwhat": "title",
        "srinfo": "suggestion",
        "format": "json"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }
    
    async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
        response = await client.get(url, params=search_params)
        print("Search Response status:", response.status_code)
        data = response.json()
        
        search_results = data.get("query", {}).get("search", [])
        suggestion = data.get("query", {}).get("searchinfo", {}).get("suggestion")
        
        print("Search results:")
        print(json.dumps(search_results, indent=2, ensure_ascii=False))
        print("Suggestion:", suggestion)
        
        # If title search returned nothing but suggestion is present, retry with suggestion
        if not search_results and suggestion:
            print(f"Retrying search with suggestion: {suggestion}")
            search_params["srsearch"] = suggestion
            response = await client.get(url, params=search_params)
            data = response.json()
            search_results = data.get("query", {}).get("search", [])
            print("Retried Search results:")
            print(json.dumps(search_results, indent=2, ensure_ascii=False))
            
        # If still no results, fallback to text search
        if not search_results:
            print("No title results, falling back to text search...")
            search_params["srsearch"] = query
            search_params["srwhat"] = "text"
            response = await client.get(url, params=search_params)
            data = response.json()
            search_results = data.get("query", {}).get("search", [])
            print("Text Search results:")
            print(json.dumps(search_results, indent=2, ensure_ascii=False))
            
        if not search_results:
            print("No results found in Fandom Wiki.")
            return
            
        # Step 2: Extract content of the top result
        top_title = search_results[0]["title"]
        print(f"\nTop search result title: {top_title}")
        
        extract_params = {
            "action": "query",
            "prop": "extracts",
            "exintro": 1,
            "explaintext": 1,
            "redirects": 1,
            "titles": top_title,
            "format": "json"
        }
        
        extract_resp = await client.get(url, params=extract_params)
        extract_data = extract_resp.json()
        pages = extract_data.get("query", {}).get("pages", {})
        
        print("\nExtract response:")
        for page_id, page_info in pages.items():
            title = page_info.get("title")
            extract = page_info.get("extract", "")
            print(f"Page ID: {page_id}")
            print(f"Title: {title}")
            print(f"Extract (preview 300 chars): {extract[:300]}")

import asyncio
asyncio.run(test_fandom_search("Rinascita"))
# Also test with a typo
asyncio.run(test_fandom_search("Rinasita"))

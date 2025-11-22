import os
import requests

def google_search(query):
    """
    Perform a Google search using the Custom Search JSON API.
    """
    api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
    cx = os.getenv("GOOGLE_SEARCH_CX")

    if not api_key or not cx:
        return "⚠️ Google Search API Key or CX not configured."

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "num": 3 # Limit to top 3 results
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        results = response.json().get("items", [])
        
        if not results:
            return "No results found."

        formatted_results = "*Search Results:*\n"
        for item in results:
            title = item.get("title")
            link = item.get("link")
            snippet = item.get("snippet")
            formatted_results += f"• [{title}]({link})\n_{snippet}_\n\n"
        
        return formatted_results
    except Exception as e:
        return f"Error performing search: {str(e)}"

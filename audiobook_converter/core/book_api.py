import requests
import logging
from typing import Dict, Optional


def search_google_books(query: str, multiple: bool = False) -> Optional[Dict]:
    """
    Search Google Books API and return book metadata.
    Args:
        query: Search query string
        multiple: If True, return a list of all results. If False, return only the best match.
    Returns:
        A dictionary with standardized metadata fields, or a list of such dictionaries if multiple=True
    """
    try:
        # Clean up query by removing common audiobook indicators
        clean_query = query.lower().replace("audiobook", "").strip()

        # Google Books API endpoint
        url = f"https://www.googleapis.com/books/v1/volumes"
        params = {
            "q": clean_query,
            "maxResults": 10,  # Get more results when searching
            "langRestrict": "en",  # Restrict to English results
            "orderBy": "relevance",  # Order by relevance
        }

        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if "items" not in data or not data["items"]:
            logging.warning(f"No results found for query: {query}")
            return [] if multiple else None

        results = []
        for item in data["items"]:
            info = item.get("volumeInfo", {})

            # Extract and standardize metadata
            metadata = {
                "title": info.get("title", ""),
                "artist": (info.get("authors", [""])[0] if info.get("authors") else ""),
                "album_artist": "",  # Narrator (not available in Google Books)
                "album": (
                    info.get("series", {}).get("title", "")
                    if info.get("series")
                    else ""
                ),
                "track": (
                    str(
                        info.get("series", {})
                        .get("seriesInfo", {})
                        .get("seriesPosition", "")
                    )
                    if info.get("series")
                    else ""
                ),
                "genre": (
                    info.get("categories", [""])[0] if info.get("categories") else ""
                ),
                "date": (
                    info.get("publishedDate", "")[:4]
                    if info.get("publishedDate")
                    else ""
                ),  # Just get the year
                "description": info.get("description", ""),
            }

            # If there's a thumbnail image, include its URL
            if info.get("imageLinks", {}).get("thumbnail"):
                metadata["cover_url"] = info["imageLinks"]["thumbnail"].replace(
                    "http://", "https://"
                )

            results.append(metadata)

        if multiple:
            return results

        # If not returning multiple results, find the best match
        best_match = None
        max_info_count = 0

        for metadata in results:
            info_count = sum(
                1
                for field in [
                    "title",
                    "artist",
                    "description",
                    "date",
                    "genre",
                ]
                if metadata.get(field)
            )

            if info_count > max_info_count:
                max_info_count = info_count
                best_match = metadata

        return best_match

    except Exception as e:
        logging.error(f"Error fetching book metadata: {str(e)}")
        return [] if multiple else None

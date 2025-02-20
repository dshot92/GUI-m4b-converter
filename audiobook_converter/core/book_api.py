import requests
import logging
from typing import Dict, Optional
from PIL import Image
from io import BytesIO


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
            # Get full volume details to access all image sizes
            volume_id = item.get("id")
            if volume_id:
                volume_url = f"https://www.googleapis.com/books/v1/volumes/{volume_id}"
                volume_response = requests.get(volume_url)
                if volume_response.status_code == 200:
                    item = volume_response.json()

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

            # Try to get the highest quality cover image
            if info.get("imageLinks"):
                # Try different image sizes in order of preference
                image_sizes = [
                    "extraLarge",
                    "large",
                    "medium",
                    "small",
                    "thumbnail",
                    "smallThumbnail",
                ]
                cover_url = None

                for size in image_sizes:
                    if size in info["imageLinks"]:
                        cover_url = info["imageLinks"][size]
                        break

                if cover_url:
                    # Convert to HTTPS and enhance quality
                    cover_url = cover_url.replace("http://", "https://")

                    # Try different URL patterns to get highest quality
                    patterns = [
                        ("&zoom=1", "&zoom=10"),
                        ("&zoom=5", "&zoom=10"),
                        ("&edge=curl", "&edge=none"),
                        ("w=128", "w=2048"),
                        ("h=192", "h=3072"),
                        ("&pg=PP1", "&printsec=frontcover"),
                        ("&img=1", "&img=2"),
                        ("&fife=", "&fife=w2048-h3072"),
                    ]

                    for old, new in patterns:
                        cover_url = cover_url.replace(old, new)

                    # Add additional parameters for quality
                    if "?" in cover_url:
                        cover_url += "&source=gbs_api&printsec=frontcover&dq=isbn"

                    metadata["cover_url"] = cover_url

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


def get_book_cover(isbn):
    # Try Google Books API first
    google_books_url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    google_response = requests.get(google_books_url)

    if google_response.status_code == 200:
        google_data = google_response.json()
        if "items" in google_data and google_data["items"]:
            google_item = google_data["items"][0]
            if (
                "volumeInfo" in google_item
                and "imageLinks" in google_item["volumeInfo"]
            ):
                google_image_links = google_item["volumeInfo"]["imageLinks"]
                # Prioritize the largest image size
                if "extraLarge" in google_image_links:
                    google_cover_url = google_image_links["extraLarge"]
                elif "large" in google_image_links:
                    google_cover_url = google_image_links["large"]
                elif "thumbnail" in google_image_links:
                    google_cover_url = google_image_links["thumbnail"]
                else:
                    logging.warning(f"No suitable image size found for ISBN: {isbn}")
                    google_cover_url = None

                if google_cover_url:
                    google_cover_response = requests.get(google_cover_url)
                    if google_cover_response.status_code == 200:
                        return google_cover_response.content

    # If Google Books API fails, try Open Library API
    open_library_url = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"
    open_library_response = requests.get(open_library_url)

    if open_library_response.status_code == 200:
        return open_library_response.content

    # If both APIs fail, try Goodreads API
    goodreads_url = (
        f"https://www.goodreads.com/book/isbn/{isbn}?key=YOUR_GOODREADS_API_KEY"
    )
    goodreads_response = requests.get(goodreads_url)

    if goodreads_response.status_code == 200:
        goodreads_data = goodreads_response.json()
        if "book" in goodreads_data and "image_url" in goodreads_data["book"]:
            goodreads_cover_url = goodreads_data["book"]["image_url"]
            goodreads_cover_response = requests.get(goodreads_cover_url)
            if goodreads_cover_response.status_code == 200:
                return goodreads_cover_response.content

    # If all APIs fail, log a warning and return None
    logging.warning(f"Failed to fetch book cover for ISBN: {isbn}")
    return None

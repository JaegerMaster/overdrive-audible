import json
import tldextract
from time import sleep
from typing import Dict, Optional, List
from urllib import parse, request
from urllib.error import HTTPError
from dataclasses import dataclass
from datetime import datetime

# Constants
AUDIBLE_ENDPOINTS = {
    "au": "https://api.audible.com.au/1.0/catalog/products",
    "ca": "https://api.audible.ca/1.0/catalog/products",
    "de": "https://api.audible.de/1.0/catalog/products",
    "es": "https://api.audible.es/1.0/catalog/products",
    "fr": "https://api.audible.fr/1.0/catalog/products",
    "in": "https://api.audible.in/1.0/catalog/products",
    "it": "https://api.audible.it/1.0/catalog/products",
    "jp": "https://api.audible.co.jp/1.0/catalog/products",
    "us": "https://api.audible.com/1.0/catalog/products",
    "uk": "https://api.audible.co.uk/1.0/catalog/products"
}
AUDIBLE_REGIONS = set(AUDIBLE_ENDPOINTS.keys())
AUDNEX_ENDPOINT = "https://api.audnex.us"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 "
    "Chrome/35.0.1916.47 Safari/537.36"
)

@dataclass
class Author:
    name: str
    asin: Optional[str] = None

@dataclass
class Narrator:
    name: str
    asin: Optional[str] = None

@dataclass
class Series:
    name: str
    asin: Optional[str] = None
    position: Optional[str] = None

@dataclass
class Genre:
    name: str
    asin: Optional[str] = None

@dataclass
class Chapter:
    title: str
    length_ms: int = 0
    start_offset_ms: int = 0
    start_offset_sec: float = 0.0

    @classmethod
    def from_dict(cls, data: Dict) -> 'Chapter':
        """Create a Chapter instance from a dictionary."""
        return cls(
            title=data.get('title', 'Unknown Chapter'),
            length_ms=int(data.get('lengthMs', 0)),
            start_offset_ms=int(data.get('startOffsetMs', 0)),
            start_offset_sec=float(data.get('startOffsetSec', 0.0))
        )

@dataclass
class BookChapters:
    chapters: List[Chapter]
    is_accurate: bool = True

    @classmethod
    def from_audnex_chapter_info(cls, data: Dict):
        chapters = []
        for chapter_data in data.get('chapters', []):
            try:
                chapters.append(Chapter.from_dict(chapter_data))
            except Exception as e:
                print(f"Error processing chapter: {e}")
                continue
        return cls(
            chapters=chapters,
            is_accurate=data.get('isAccurate', True)
        )

@dataclass
class Book:
    asin: str
    title: str
    subtitle: Optional[str]
    authors: List[Author]
    narrators: List[Narrator]
    series: Optional[Series]
    genres: List[Genre]
    runtime_length_ms: int
    release_date: str
    publisher: str
    language: str
    region: str
    summary_html: str
    summary_markdown: str
    image_url: str

    @classmethod
    def from_audnex_book(cls, data: Dict):
        authors = [Author(name=a.get("name", "Unknown Author"), asin=a.get("asin")) 
                  for a in data.get("authors", [])]
        
        narrators = [Narrator(name=n.get("name", "Unknown Narrator"), asin=n.get("asin")) 
                    for n in data.get("narrators", [])]
        
        series_data = data.get("series")
        series = None
        if series_data:
            series = Series(
                name=series_data.get("name", "Unknown Series"),
                asin=series_data.get("asin"),
                position=series_data.get("position")
            )
        
        genres = [Genre(name=g.get("name", "Unknown Genre"), asin=g.get("asin")) 
                 for g in data.get("genres", [])]

        return cls(
            asin=data.get("asin", ""),
            title=data.get("title", "Unknown Title"),
            subtitle=data.get("subtitle"),
            authors=authors,
            narrators=narrators,
            series=series,
            genres=genres,
            runtime_length_ms=data.get("runtime_length_ms", 0),
            release_date=data.get("release_date", ""),
            publisher=data.get("publisher", "Unknown Publisher"),
            language=data.get("language", ""),
            region=data.get("region", ""),
            summary_html=data.get("summary_html", ""),
            summary_markdown=data.get("summary_markdown", ""),
            image_url=data.get("image_url", "")
        )

def make_request(url: str) -> bytes:
    """Makes a request to the specified url and returns received response."""
    num_retries = 3
    sleep_time = 2
    for n in range(num_retries):
        try:
            req = request.Request(url, headers={"User-Agent": USER_AGENT})
            with request.urlopen(req) as response:
                return response.read()
        except HTTPError as e:
            if e.code == 404:
                raise
            if e.code == 429:
                reset_seconds = int(e.headers.get('retry-after', '5'))
                sleep_time = reset_seconds + 1
            if n < num_retries - 1:
                sleep(sleep_time)
                sleep_time *= 2
            else:
                raise

def format_timestamp(seconds: float) -> str:
    """Convert seconds to timestamp format (HH:MM:SS.mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int((seconds * 1000) % 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"

def search_audible(keywords: str, region: str = "us") -> Dict:
    """Search Audible for books matching the keywords."""
    params = {
        "response_groups": "contributors,product_attrs,product_desc,product_extended_attrs,series",
        "num_results": 10,
        "products_sort_by": "Relevance",
        "keywords": keywords,
    }
    query = parse.urlencode(params)
    try:
        response = json.loads(make_request(f"{AUDIBLE_ENDPOINTS[region]}?{query}"))
        if 'products' in response:
            return response
        
        # Use Audnex API as fallback
        response = json.loads(make_request(
            f"{AUDNEX_ENDPOINT}/search/{region}?title={parse.quote(keywords)}"
        ))
        return response
    except Exception as e:
        print(f"Error during search: {e}")
        return {"products": []}

def get_book_info(asin: str, region: str = "us"):
    """Get detailed book information including chapters."""
    try:
        book_response = json.loads(make_request(
            f"{AUDNEX_ENDPOINT}/books/{asin}?region={region}&update=1"))
        chapter_response = json.loads(make_request(
            f"{AUDNEX_ENDPOINT}/books/{asin}/chapters?region={region}&update=1"))
        
        book = Book.from_audnex_book(book_response)
        book_chapters = BookChapters.from_audnex_chapter_info(chapter_response)
        return book, book_chapters
    except Exception as e:
        print(f"Error getting book info: {e}")
        return None, None

def search_and_get_chapters(author: str, title: str, region: str = "us", output_file: str = "chapters.txt"):
    """Search for a book and create a chapters file."""
    try:
        if region not in AUDIBLE_REGIONS:
            print(f"Invalid region. Available regions: {', '.join(sorted(AUDIBLE_REGIONS))}")
            return
        
        query = f"{title} {author}"
        print(f"Searching for: {query} in region: {region}")
        
        # Search for the book
        results = search_audible(query, region)
        products = results.get("products", [])
        
        if not products:
            print("No results found")
            return
        
        # Display search results
        print("\nSearch Results:")
        for i, book in enumerate(products, 1):
            series_info = ""
            if book.get("series"):
                series = book["series"][0] if isinstance(book["series"], list) else book["series"]
                series_info = f" - {series.get('name', '')}"
                if series.get('position'):
                    series_info += f" #{series['position']}"
            
            authors = [a.get('name', '') for a in book.get('authors', [])]
            narrators = [n.get('name', '') for n in book.get('narrators', [])]
            
            print(f"{i}. {book.get('title', '')}{series_info}")
            if authors:
                print(f"   By: {', '.join(authors)}")
            if narrators:
                print(f"   Narrated by: {', '.join(narrators)}")
            if book.get('release_date'):
                print(f"   Release Date: {book['release_date']}")
            print()
        
        # Let user select a book
        while True:
            try:
                choice = input("\nSelect a book number (0 to exit): ").strip()
                if not choice or choice == "0":
                    return
                choice = int(choice)
                if 1 <= choice <= len(products):
                    break
                print("Invalid choice. Please try again.")
            except ValueError:
                print("Please enter a valid number.")
        
        selected_book = products[choice - 1]
        asin = selected_book.get("asin")
        if not asin:
            print("Error: Could not find ASIN for selected book")
            return
        
        # Get detailed book and chapter information
        book, chapters = get_book_info(asin, region)
        if not book or not chapters:
            print("Error: Could not fetch book details")
            return
        
        # Write chapters to file
        with open(output_file, "w", encoding='utf-8') as f:
            for chapter in chapters.chapters:
                timestamp = format_timestamp(chapter.start_offset_sec)
                f.write(f"{timestamp} {chapter.title}\n")
        
        print(f"\nChapters have been saved to {output_file}")
        if not chapters.is_accurate:
            print("Note: Chapter timestamps may be approximate")
            
    except Exception as e:
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    print(f"Available regions: {', '.join(sorted(AUDIBLE_REGIONS))}")
    region = input("Enter region code (default: us): ").strip().lower() or "us"
    author = input("Enter author name: ").strip()
    title = input("Enter book title: ").strip()
    
    if not author or not title:
        print("Both author and title are required.")
    else:
        search_and_get_chapters(author, title, region)

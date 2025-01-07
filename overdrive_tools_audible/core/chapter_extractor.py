import os
import re
import json
from typing import Dict, List, Optional, Tuple
from urllib import parse, request
from urllib.error import HTTPError
from time import sleep
from rich.console import Console
from rich.prompt import Prompt
import xml.etree.ElementTree as ET

console = Console()

# Audible API Constants
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
AUDNEX_ENDPOINT = "https://api.audnex.us"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

def format_timestamp(seconds: float) -> str:
    """Convert seconds to timestamp format (HH:MM:SS.mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int((seconds * 1000) % 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"

def parse_odm_file(file_path: str) -> Dict[str, str]:
    """Parse ODM file to extract book metadata."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        metadata_text = "Metadata>"
        metadata_start = content.find("<" + metadata_text)
        metadata_end = content.find("</" + metadata_text) + len(metadata_text) + 2

        if metadata_start == -1 or metadata_end == -1:
            cdata_start = content.find("<![CDATA[<" + metadata_text)
            if cdata_start != -1:
                metadata_start = cdata_start + 9
                cdata_end = content.find("]]>", metadata_start)
                if cdata_end != -1:
                    metadata_end = cdata_end

        if metadata_start == -1 or metadata_end == -1:
            raise ValueError("Could not find Metadata section in ODM file")

        metadata = content[metadata_start:metadata_end]
        root = ET.fromstring(metadata)

        book_info = {
            'title': root.find('.//Title').text if root.find('.//Title') is not None else None,
            'author': None,
            'series': root.find('.//Series').text if root.find('.//Series') is not None else None,
        }

        # Extract author
        for creator in root.findall('.//Creator'):
            if creator.get('role') == 'Author':
                book_info['author'] = creator.text
                break

        return book_info

    except Exception as e:
        console.print(f"[yellow]Warning: Error parsing ODM file: {str(e)}[/yellow]")
        return {'title': None, 'author': None, 'series': None}

class ChapterExtractor:
    def __init__(self, directory: str):
        """Initialize chapter extractor with directory path."""
        self.directory = os.path.abspath(directory)

    def _get_book_info(self) -> Dict[str, str]:
        """Get book info from ODM file or directory name."""
        # First try ODM file
        odm_files = [f for f in os.listdir(self.directory) if f.endswith('.odm')]
        if odm_files:
            book_info = parse_odm_file(os.path.join(self.directory, odm_files[0]))
            if book_info['title'] and book_info['author']:
                return book_info

        # Try directory name
        dir_name = os.path.basename(self.directory)
        if ' - ' in dir_name:
            author, title = dir_name.split(' - ', 1)
            return {'author': author, 'title': title}

        # Ask user
        console.print("[yellow]Could not determine book information automatically.[/yellow]")
        author = Prompt.ask("Enter author name")
        title = Prompt.ask("Enter book title")
        return {'author': author, 'title': title}

    def _get_chapters(self, asin: str, region: str) -> Dict:
        """Get chapter information for a specific book."""
        try:
            url = f"{AUDNEX_ENDPOINT}/books/{asin}/chapters?region={region}&update=1"
            console.print(f"[blue]Fetching chapters from: {url}[/blue]")
            
            # Make request with proper headers
            headers = {"User-Agent": USER_AGENT}
            req = request.Request(url, headers=headers)
            with request.urlopen(req) as response:
                data = response.read()
            
            response = json.loads(data)
            console.print("[green]Successfully retrieved chapter data[/green]")

            chapters = []
            for chapter in response.get('chapters', []):
                chapters.append({
                    'title': chapter.get('title', 'Unknown Chapter'),
                    'start_offset_sec': float(chapter.get('startOffsetSec', 0)),
                    'length_ms': int(chapter.get('lengthMs', 0))
                })

            return {'chapters': chapters, 'is_accurate': response.get('isAccurate', True)}

        except Exception as e:
            console.print(f"[red]Error getting chapters: {str(e)}[/red]")
            return {'chapters': [], 'is_accurate': False}

    def _search_audible(self, author: str, title: str, region: str) -> Dict:
        """Search Audible for books matching the keywords."""
        query = f"{title} {author}"
        params = {
            "response_groups": "contributors,product_attrs,product_desc,product_extended_attrs,series",
            "num_results": 10,
            "products_sort_by": "Relevance",
            "keywords": query,
        }

        query_string = parse.urlencode(params)
        endpoint = AUDIBLE_ENDPOINTS.get(region, AUDIBLE_ENDPOINTS["us"])

        try:
            headers = {"User-Agent": USER_AGENT}
            req = request.Request(f"{endpoint}?{query_string}", headers=headers)
            with request.urlopen(req) as response:
                response_data = response.read()
            
            response = json.loads(response_data)
            if 'products' in response:
                return response

            # Fallback to Audnex API
            req = request.Request(
                f"{AUDNEX_ENDPOINT}/search/{region}?title={parse.quote(query)}",
                headers=headers
            )
            with request.urlopen(req) as response:
                response_data = response.read()
            
            return json.loads(response_data)

        except Exception as e:
            console.print(f"[red]Error searching Audible: {str(e)}[/red]")
            return {"products": []}

    def _display_search_results(self, products: List[Dict]) -> Optional[str]:
        """Display search results and get user selection."""
        if not products:
            return None

        console.print("\n[cyan]Search Results:[/cyan]")
        for i, book in enumerate(products, 1):
            series_info = ""
            if book.get("series"):
                series = book["series"][0] if isinstance(book["series"], list) else book["series"]
                series_info = f" - {series.get('name', '')}"
                if series.get('position'):
                    series_info += f" #{series['position']}"

            authors = [a.get('name', '') for a in book.get('authors', [])]
            narrators = [n.get('name', '') for n in book.get('narrators', [])]

            console.print(f"{i}. {book.get('title', '')}{series_info}")
            if authors:
                console.print(f"   By: {', '.join(authors)}")
            if narrators:
                console.print(f"   Narrated by: {', '.join(narrators)}")
            if book.get('release_date'):
                console.print(f"   Release Date: {book['release_date']}")
            console.print()

        while True:
            try:
                choice = Prompt.ask(
                    "\nSelect a book number (0 to exit)",
                    default="1"
                )
                if choice == "0":
                    return None
                choice_num = int(choice)
                if 1 <= choice_num <= len(products):
                    return products[choice_num - 1].get('asin')
                console.print("[red]Invalid choice. Please try again.[/red]")
            except ValueError:
                console.print("[red]Please enter a valid number.[/red]")

    def extract_chapters(self) -> bool:
        """Extract chapters from Audible and save to file."""
        try:
            # Get book information
            book_info = self._get_book_info()
            if not book_info['author'] or not book_info['title']:
                console.print("[red]Could not determine book information[/red]")
                return False

            # Get region from user
            console.print("\n[blue]Available regions: au, ca, de, es, fr, in, it, jp, us, uk[/blue]")
            region = Prompt.ask("Enter region code", default="us").lower()

            # Search for the book
            console.print(f"\n[blue]Searching for: {book_info['title']} by {book_info['author']}[/blue]")
            results = self._search_audible(book_info['author'], book_info['title'], region)

            # Display results and get selection
            asin = self._display_search_results(results.get('products', []))
            if not asin:
                console.print("[yellow]No book selected[/yellow]")
                return False

            # Get chapter information
            chapter_info = self._get_chapters(asin, region)
            if not chapter_info['chapters']:
                console.print("[red]No chapters found[/red]")
                return False

            # Write chapters to file
            chapters_file = os.path.join(self.directory, "chapters.txt")
            with open(chapters_file, "w", encoding='utf-8') as f:
                for chapter in chapter_info['chapters']:
                    timestamp = format_timestamp(chapter['start_offset_sec'])
                    f.write(f"{timestamp} {chapter['title']}\n")

            console.print(f"[green]Successfully extracted {len(chapter_info['chapters'])} chapters to {chapters_file}[/green]")
            if not chapter_info['is_accurate']:
                console.print("[yellow]Note: Chapter timestamps may be approximate[/yellow]")

            return True

        except Exception as e:
            console.print(f"[red]Error extracting chapters: {str(e)}[/red]")
            return False

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Extract chapters from Audible books")
    parser.add_argument("--directory", default=".", help="Directory containing book information")
    args = parser.parse_args()
    
    extractor = ChapterExtractor(args.directory)
    if extractor.extract_chapters():
        exit(0)
    else:
        exit(1)

if __name__ == "__main__":
    main()

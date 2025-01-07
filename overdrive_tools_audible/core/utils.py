# overdrive_tools/core/utils.py

import re
import os
import uuid
import base64
import hashlib
import xml.etree.ElementTree as ET
from typing import Dict, Tuple
from urllib.parse import quote
from rich.console import Console

console = Console()

def sanitize(text: str) -> str:
    """Replace filename-unfriendly characters with a hyphen and trim leading/trailing hyphens/spaces."""
    sanitized = re.sub(r'[^\w\s._-]', '-', text)
    return sanitized.strip('- ')

def parse_timestamp(timestamp: str) -> float:
    """Convert HH:MM:SS.mmm to seconds"""
    hours, minutes, seconds = timestamp.split(':')
    seconds, milliseconds = seconds.split('.')
    total_seconds = int(hours) * 3600 + int(minutes) * 60 + int(seconds)
    total_seconds += float(f"0.{milliseconds}")
    return total_seconds

def format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS.mmm format"""
    hours = int(seconds // 3600)
    seconds = seconds % 3600
    minutes = int(seconds // 60)
    seconds = seconds % 60
    whole_seconds = int(seconds)
    milliseconds = int((seconds - whole_seconds) * 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"

def generate_client_id() -> Tuple[str, str]:
    """Generate client ID and hash for OverDrive authentication."""
    from ..config import Config
    
    client_id = str(uuid.uuid4()).upper()
    raw_hash = f"{client_id}|{Config.OMC}|{Config.OS}|ELOSNOC*AIDEM*EVIRDREVO"
    raw_hash_bytes = raw_hash.encode('utf-16le')
    hash_value = base64.b64encode(hashlib.sha1(raw_hash_bytes).digest()).decode('ascii')
    
    return client_id, hash_value

def get_metadata_info(metadata_path: str) -> Dict[str, str]:
    """Extract author and title from metadata file."""
    try:
        with open(metadata_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        if not content.strip().startswith('<'):
            content = '<Metadata>' + content + '</Metadata>'
            
        root = ET.fromstring(content)
        
        author = "Unknown Author"
        for creator in root.findall(".//Creator"):
            if creator.get("role", "").startswith("Author"):
                author = creator.text if creator.text else "Unknown Author"
                break
                
        title = "Unknown Title"
        title_elem = root.find(".//Title")
        if title_elem is not None and title_elem.text:
            title = title_elem.text
            
        if title != "Unknown Title":
            title = sanitize(title)
            
        return {"author": author, "title": title}
        
    except Exception as e:
        console.print(f"[red]Error parsing metadata: {str(e)}[/red]")
        return {"author": "Unknown Author", "title": "Unknown Title"}

def ensure_dir_exists(path: str) -> None:
    """Create directory if it doesn't exist."""
    os.makedirs(path, exist_ok=True)

def get_file_size(file_path: str) -> int:
    """Get file size in bytes."""
    try:
        return os.path.getsize(file_path)
    except OSError:
        return 0

# overdrive_tools/core/downloader.py

import os
import requests
import xml.etree.ElementTree as ET
from typing import Optional
from urllib.parse import quote
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.console import Console
from ..config import Config
from . import utils

console = Console()

class OverDriveDownloader:
    def __init__(self, odm_path: str):
        """Initialize OverDrive downloader with ODM file path."""
        self.odm_path = odm_path
        self.metadata_path = f"{odm_path}.metadata"
        self.license_path = f"{odm_path}.license"
        
    def extract_metadata(self) -> None:
        """Extract metadata from ODM file."""
        if os.path.exists(self.metadata_path) and utils.get_file_size(self.metadata_path) > 0:
            return

        try:
            with open(self.odm_path, 'r', encoding='utf-8') as f:
                content = f.read()

            metadata_text = "Metadata>"
            metadata_start = content.find("<" + metadata_text)
            metadata_end = content.find("</" + metadata_text) + len("</" + metadata_text)
            
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
            
            with open(self.metadata_path, 'w', encoding='utf-8') as f:
                f.write(metadata)
                
        except Exception as e:
            raise Exception(f"Error extracting metadata: {str(e)}")

    def acquire_license(self) -> None:
        """Acquire license from OverDrive server."""
        if os.path.exists(self.license_path) and utils.get_file_size(self.license_path) > 0:
            return

        client_id, hash_value = utils.generate_client_id()
        
        tree = ET.parse(self.odm_path)
        root = tree.getroot()
        
        acquisition_url = root.find(".//AcquisitionUrl").text
        media_id = root.get("id")
        
        params = {
            "MediaID": media_id,
            "ClientID": client_id,
            "OMC": Config.OMC,
            "OS": Config.OS,
            "Hash": hash_value
        }
        
        headers = {"User-Agent": Config.USER_AGENT}
        
        response = requests.get(acquisition_url, params=params, headers=headers)
        response.raise_for_status()
        
        with open(self.license_path, 'w') as f:
            f.write(response.text)

    def _download_part(self, url: str, headers: dict, output_path: str, 
                      progress: Optional[Progress] = None, task_id: Optional[str] = None) -> None:
        """Download a single part of the audiobook."""
        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024
        downloaded = 0

        with open(output_path, 'wb') as f:
            for data in response.iter_content(block_size):
                f.write(data)
                downloaded += len(data)
                if progress and task_id and total_size:
                    progress.update(task_id, completed=(downloaded / total_size) * 100)

    def download(self) -> str:
        """Download all parts of the audiobook and return the output directory."""
        self.extract_metadata()
        self.acquire_license()
        
        info = utils.get_metadata_info(self.metadata_path)
        author, title = info["author"], info["title"]
        
        output_dir = Config.DIR_FORMAT.replace("@AUTHOR", author).replace("@TITLE", title)
        utils.ensure_dir_exists(output_dir)

        with open(self.license_path) as f:
            license_content = f.read().strip()
        root = ET.fromstring(license_content)
        client_id = root.find(".//{*}ClientID").text

        odm_tree = ET.parse(self.odm_path)
        odm_root = odm_tree.getroot()
        base_url = odm_root.find(".//Protocol[@method='download']").get("baseurl")
        
        # Download parts
        parts = odm_root.findall(".//Part")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            for idx, part in enumerate(parts, 1):
                filename = part.get("filename")
                filename = quote(filename).replace("{", "%7B").replace("}", "%7D")
                suffix = filename.split("-")[-1]
                output_path = os.path.join(output_dir, suffix)

                if os.path.exists(output_path):
                    continue

                headers = {
                    "User-Agent": Config.USER_AGENT,
                    "License": license_content,
                    "ClientID": client_id
                }

                task_id = progress.add_task(
                    f"Downloading part {idx}/{len(parts)}",
                    total=100
                )

                self._download_part(
                    f"{base_url}/{filename}",
                    headers,
                    output_path,
                    progress,
                    task_id
                )

        # Download cover image
        self._download_cover(output_dir)
        
        # Create chapters.txt
        self._create_chapters_file(output_dir, parts)

        return output_dir

    def _download_cover(self, output_dir: str) -> None:
        """Download cover image if available."""
        try:
            metadata_tree = ET.parse(self.metadata_path)
            metadata_root = metadata_tree.getroot()
            cover_url = metadata_root.find(".//CoverUrl")
            
            if cover_url is not None and cover_url.text:
                cover_url_text = cover_url.text.replace("{", "%7B").replace("}", "%7D")
                cover_path = os.path.join(output_dir, "folder.jpg")
                
                response = requests.get(
                    cover_url_text,
                    headers={"User-Agent": Config.USER_AGENT}
                )
                response.raise_for_status()
                
                with open(cover_path, 'wb') as f:
                    f.write(response.content)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not download cover image: {str(e)}[/yellow]")

    def _create_chapters_file(self, output_dir: str, parts: list) -> None:
        """Create chapters.txt file."""
        cumulative_time = 0
        with open(os.path.join(output_dir, "chapters.txt"), "w") as f:
            for part in parts:
                duration_str = part.get("duration")
                minutes, seconds = map(int, duration_str.split(":"))
                duration = minutes * 60 + seconds
                
                timestamp = utils.format_timestamp(cumulative_time)
                part_name = part.get("name", f"Part {part.get('number')}")
                f.write(f"{timestamp} {part_name}\n")
                
                cumulative_time += duration

    def early_return(self) -> None:
        """Process an early return for an OverDrive book loan."""
        tree = ET.parse(self.odm_path)
        root = tree.getroot()
        
        return_url = root.find(".//EarlyReturnURL").text
        response = requests.get(return_url, headers={"User-Agent": Config.USER_AGENT})
        response.raise_for_status()

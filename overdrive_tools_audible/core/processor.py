
import os
import re
import subprocess
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass
from mutagen.mp3 import MP3
import mutagen.id3 as id3
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from . import utils
from ..config import Config

console = Console()

@dataclass
class Chapter:
    """Represents a chapter in the audiobook."""
    title: str
    start: float
    end: Optional[float] = None

    def __str__(self) -> str:
        """String representation of the chapter."""
        return f"{self.title}: {utils.format_timestamp(self.start)} -> {utils.format_timestamp(self.end) if self.end else 'END'}"

class AudioProcessor:
    def __init__(self, directory: str):
        """Initialize the audio processor with the input directory."""
        self.directory = os.path.abspath(directory)
        self.chapters_file = os.path.join(self.directory, 'chapters.txt')
        self._validate_directory()

    def _validate_directory(self) -> None:
        """Validate that the directory and required files exist."""
        if not os.path.isdir(self.directory):
            raise ValueError(f"Directory does not exist: {self.directory}")
        if not os.path.isfile(self.chapters_file):
            raise ValueError(f"Chapters file not found: {self.chapters_file}")
        if not any(f.endswith('.mp3') for f in os.listdir(self.directory)):
            raise ValueError(f"No MP3 files found in directory: {self.directory}")

    def _get_total_duration(self) -> float:
        """Calculate total duration of all MP3 files."""
        total_duration = 0
        for file in sorted(os.listdir(self.directory)):
            if file.endswith('.mp3'):
                audio = MP3(os.path.join(self.directory, file))
                total_duration += audio.info.length
        return total_duration

    def _get_file_boundaries(self) -> List[Tuple[float, float, str]]:
        """Get time boundaries for each MP3 file."""
        boundaries = []
        current_time = 0
        
        for file in sorted(f for f in os.listdir(self.directory) if f.endswith('.mp3')):
            audio = MP3(os.path.join(self.directory, file))
            duration = audio.info.length
            boundaries.append((current_time, current_time + duration, file))
            current_time += duration
            
        return boundaries

    def read_chapters(self) -> List[Chapter]:
        """Read and parse the chapters.txt file."""
        chapters = []
        
        try:
            with open(self.chapters_file, 'r') as f:
                lines = f.readlines()

            for i, line in enumerate(lines):
                match = re.match(r'(\d{2}:\d{2}:\d{2}\.\d{3})\s+(.*)', line.strip())
                if not match:
                    continue

                timestamp, title = match.groups()
                start_time = utils.parse_timestamp(timestamp)
                chapter = Chapter(title, start_time)
                
                if i > 0:
                    chapters[i-1].end = start_time

                chapters.append(chapter)

            if chapters:
                chapters[-1].end = self._get_total_duration()

            return chapters
            
        except Exception as e:
            console.print(f"[red]Error reading chapters file: {str(e)}[/red]")
            raise

    def _split_chapter(self, chapter: Chapter, chapter_num: int, 
                      file_info: Tuple[float, float, str], output_dir: str) -> bool:
        """Split a single chapter from the source audio file."""
        start_time, end_time, input_file = file_info
        chapter_title = re.sub(r'[<>:"/\\|?*]', '_', chapter.title)
        output_file = os.path.join(output_dir, f"{str(chapter_num).zfill(2)} - {chapter_title}.mp3")

        try:
            input_path = os.path.join(self.directory, input_file)
            relative_start = chapter.start - start_time
            duration = chapter.end - chapter.start

            # Extract chapter using ffmpeg
            cmd = [
                'ffmpeg', '-y',
                '-i', input_path,
                '-ss', str(relative_start),
                '-t', str(duration),
                '-acodec', 'copy',
                output_file
            ]
            subprocess.run(cmd, check=True, capture_output=True)

            # Update metadata
            self._update_metadata(output_file, chapter, chapter_num)
            
            return True
            
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Error processing chapter {chapter_num}: {str(e)}[/red]")
            return False
        except Exception as e:
            console.print(f"[red]Unexpected error processing chapter {chapter_num}: {str(e)}[/red]")
            return False

    def _update_metadata(self, file_path: str, chapter: Chapter, chapter_num: int) -> None:
        """Update MP3 metadata tags."""
        try:
            audio = MP3(file_path)
            
            if not audio.tags:
                audio.tags = id3.ID3()

            # Remove OverDrive MediaMarkers if present
            if 'TXXX:OverDrive MediaMarkers' in audio.tags:
                del audio.tags['TXXX:OverDrive MediaMarkers']

            # Update title and track number
            audio.tags.add(id3.TIT2(encoding=3, text=chapter.title))
            audio.tags.add(id3.TRCK(encoding=3, text=str(chapter_num)))

            audio.save(v2_version=3)
            
        except Exception as e:
            console.print(f"[red]Error updating metadata for chapter {chapter_num}: {str(e)}[/red]")
            raise

    def process_chapters(self) -> bool:
        """Process and split audio files by chapters."""
        try:
            chapters = self.read_chapters()
            if not chapters:
                console.print("[red]No chapters found in chapters.txt[/red]")
                return False

            # Create output directory
            dir_name = os.path.basename(os.path.normpath(self.directory))
            output_dir = os.path.join(os.path.dirname(self.directory), f"{dir_name}_split")
            utils.ensure_dir_exists(output_dir)

            # Get file boundaries for all MP3s
            file_boundaries = self._get_file_boundaries()

            # Process chapters
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                console=console
            ) as progress:
                task = progress.add_task(
                    "Processing chapters",
                    total=len(chapters)
                )

                for i, chapter in enumerate(chapters, 1):
                    # Find which input file contains this chapter
                    for boundary in file_boundaries:
                        if chapter.start >= boundary[0] and chapter.start < boundary[1]:
                            if self._split_chapter(chapter, i, boundary, output_dir):
                                progress.update(task, advance=1)
                                break

            return True
            
        except Exception as e:
            console.print(f"[red]Error processing chapters: {str(e)}[/red]")
            return False

    def cleanup_original_files(self) -> bool:
        """Remove all original files and folders after successful processing."""
        try:
            for root, dirs, files in os.walk(self.directory, topdown=False):
                for name in files:
                    file_path = os.path.join(root, name)
                    os.remove(file_path)
                for name in dirs:
                    dir_path = os.path.join(root, name)
                    os.rmdir(dir_path)
            os.rmdir(self.directory)
            return True
            
        except Exception as e:
            console.print(f"[red]Error during cleanup: {str(e)}[/red]")
            return False

    def import_to_library(self, lib_type: str = 'beets') -> bool:
        """Import processed files to media library."""
        try:
            dir_name = os.path.basename(os.path.normpath(self.directory))
            split_dir = os.path.join(os.path.dirname(self.directory), f"{dir_name}_split")
            
            if lib_type == 'beets':
                cmd = ["beet", "import", "-m", split_dir]
                subprocess.run(cmd, check=True)
                return True
            else:
                console.print(f"[yellow]Unsupported library type: {lib_type}[/yellow]")
                return False
                
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Error importing to library: {str(e)}[/red]")
            return False
        except Exception as e:
            console.print(f"[red]Unexpected error during library import: {str(e)}[/red]")
            return False

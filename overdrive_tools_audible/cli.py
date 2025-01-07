#!/usr/bin/env python3

import os
import sys
import argparse
from typing import List
from rich.console import Console
from rich.table import Table

from .core.downloader import OverDriveDownloader
from .core.processor import AudioProcessor
from .core.chapter_extractor import ChapterExtractor
from .config import Config

console = Console()

def validate_odm_file(file_path: str) -> bool:
    """Validate that the file exists and has .odm extension."""
    if not file_path.endswith('.odm'):
        console.print(f"[red]Error: {file_path} is not an ODM file[/red]")
        return False
    if not os.path.exists(file_path):
        console.print(f"[red]Error: File not found: {file_path}[/red]")
        return False
    return True

def handle_download(args: argparse.Namespace) -> None:
    """Handle the download command."""
    for odm_file in args.files:
        if not validate_odm_file(odm_file):
            continue
            
        try:
            console.print(f"\n[cyan]Processing: {odm_file}[/cyan]")
            downloader = OverDriveDownloader(odm_file)
            output_dir = downloader.download()
            
            if args.process:
                console.print("\n[cyan]Processing chapters...[/cyan]")
                processor = AudioProcessor(output_dir)
                if processor.process_chapters():
                    if args.cleanup:
                        processor.cleanup_original_files()
                    if args.import_to:
                        processor.import_to_library(args.import_to)
                        
            console.print(f"\n[green]Successfully processed: {odm_file}[/green]")
            
        except Exception as e:
            console.print(f"[red]Error processing {odm_file}: {str(e)}[/red]")

def handle_return(args: argparse.Namespace) -> None:
    """Handle the return command."""
    for odm_file in args.files:
        if not validate_odm_file(odm_file):
            continue
            
        try:
            console.print(f"\n[cyan]Returning: {odm_file}[/cyan]")
            downloader = OverDriveDownloader(odm_file)
            downloader.early_return()
            console.print(f"[green]Successfully returned: {odm_file}[/green]")
            
        except Exception as e:
            console.print(f"[red]Error returning {odm_file}: {str(e)}[/red]")

def handle_process(args: argparse.Namespace) -> None:
    """Handle the process command."""
    for directory in args.directories:
        if not os.path.isdir(directory):
            console.print(f"[red]Error: Directory not found: {directory}[/red]")
            continue
            
        try:
            console.print(f"\n[cyan]Processing directory: {directory}[/cyan]")
            processor = AudioProcessor(directory)
            
            if processor.process_chapters():
                if args.cleanup:
                    processor.cleanup_original_files()
                if args.import_to:
                    processor.import_to_library(args.import_to)
                    
            console.print(f"[green]Successfully processed: {directory}[/green]")
            
        except Exception as e:
            console.print(f"[red]Error processing {directory}: {str(e)}[/red]")

def handle_extract(args: argparse.Namespace) -> None:
    """Handle the extract command."""
    for directory in args.directories:
        if not os.path.isdir(directory):
            console.print(f"[red]Error: Directory not found: {directory}[/red]")
            continue
            
        try:
            console.print(f"\n[cyan]Extracting chapters from: {directory}[/cyan]")
            extractor = ChapterExtractor(directory)
            if extractor.extract_chapters():
                console.print(f"[green]Successfully extracted chapters from: {directory}[/green]")
                
                if args.process:
                    console.print("\n[cyan]Processing chapters...[/cyan]")
                    processor = AudioProcessor(directory)
                    if processor.process_chapters():
                        if args.cleanup:
                            processor.cleanup_original_files()
                        if args.import_to:
                            processor.import_to_library(args.import_to)
            
        except Exception as e:
            console.print(f"[red]Error processing {directory}: {str(e)}[/red]")

def create_parser() -> argparse.ArgumentParser:
    """Create and return the argument parser."""
    parser = argparse.ArgumentParser(
        description="OverDrive Tools - Download and process OverDrive audiobooks",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--version', action='version', 
                       version=f'OverDrive Tools v{Config.VERSION}')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Print detailed progress')

    subparsers = parser.add_subparsers(dest='command', required=True)

    # Download command
    download_parser = subparsers.add_parser('download', 
                                          help='Download audiobooks from ODM files')
    download_parser.add_argument('files', nargs='+', help='ODM files to process')
    download_parser.add_argument('-p', '--process', action='store_true',
                               help='Process chapters after downloading')
    download_parser.add_argument('-c', '--cleanup', action='store_true',
                               help='Clean up original files after processing')
    download_parser.add_argument('-i', '--import-to', choices=['beets'],
                               help='Import to media library after processing')
    download_parser.add_argument('-o', '--output-format',
                               help='Output directory format (default: @AUTHOR - @TITLE)')

    # Return command
    return_parser = subparsers.add_parser('return',
                                        help='Return borrowed audiobooks')
    return_parser.add_argument('files', nargs='+', help='ODM files to return')

    # Process command
    process_parser = subparsers.add_parser('process',
                                         help='Process downloaded audiobooks')
    process_parser.add_argument('directories', nargs='+',
                              help='Directories containing audiobook files')
    process_parser.add_argument('-c', '--cleanup', action='store_true',
                              help='Clean up original files after processing')
    process_parser.add_argument('-i', '--import-to', choices=['beets'],
                              help='Import to media library after processing')

    # Extract command
    extract_parser = subparsers.add_parser('extract',
                                         help='Extract chapters from OverDrive MP3 files')
    extract_parser.add_argument('directories', nargs='+',
                              help='Directories containing MP3 files')
    extract_parser.add_argument('-p', '--process', action='store_true',
                              help='Process chapters after extraction')
    extract_parser.add_argument('-c', '--cleanup', action='store_true',
                              help='Clean up original files after processing')
    extract_parser.add_argument('-i', '--import-to', choices=['beets'],
                              help='Import to media library after processing')

    return parser

def main(args: List[str] = None) -> None:
    """Main entry point for the CLI."""
    parser = create_parser()
    args = parser.parse_args(args)

    try:
        # Only set output format if it's a download command and format is specified
        if args.command == 'download' and hasattr(args, 'output_format') and args.output_format:
            Config.DIR_FORMAT = args.output_format

        if args.command == 'download':
            handle_download(args)
        elif args.command == 'return':
            handle_return(args)
        elif args.command == 'process':
            handle_process(args)
        elif args.command == 'extract':
            handle_extract(args)
            
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error: {str(e)}[/red]")
        sys.exit(1)

if __name__ == "__main__":
    main()

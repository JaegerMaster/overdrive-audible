# OverDrive Tools Audible

A set of tools for managing OverDrive audiobooks, including downloading, chapter extraction, and processing.

## Installation
```bash
pip3 install .
```

## Usage
The package provides several commands:
1. Download audiobooks:
```bash
overdrive-tools-audible download file.odm
```
2. Extract chapters:
```bash
overdrive-tools-audible extract /path/to/audiobook
```
3. Process chapters:
```bash
overdrive-tools-audible process /path/to/audiobook
```
4. Return a borrowed book:
```bash
overdrive-tools-audible return file.odm
```

Each command supports additional options. Use `--help` to see all options:
```bash
overdrive-tools-audible --help
```

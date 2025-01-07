"""
OverDrive Tools Package
A tool for downloading and processing OverDrive audiobooks
"""

from .core.downloader import OverDriveDownloader
from .core.processor import AudioProcessor, Chapter
from .config import Config
from . import core

__version__ = Config.VERSION

# Define what's available when using 'from overdrive_tools import *'
__all__ = [
    'OverDriveDownloader',
    'AudioProcessor',
    'Chapter',
    'Config',
    'core',
    '__version__'
]

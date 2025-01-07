from setuptools import setup, find_packages

# Read requirements from requirements.txt
with open('requirements.txt') as f:
    required = f.read().splitlines()
setup(
    name="overdrive-tools-audible", 
    version="3.0.0",
    packages=find_packages(),
    install_requires=required,
    entry_points={
        'console_scripts': [
            'overdrive-tools-audible=overdrive_tools_audible.cli:main',  # Updated this line
        ],
    },
    author="JaegerMaster",
    description="Tools for managing OverDrive audiobooks",
    python_requires=">=3.7",
)

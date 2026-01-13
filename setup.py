from __future__ import annotations

from pathlib import Path

from setuptools import find_packages, setup

# Read README for long description
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

setup(
    # Package metadata
    name="mailq",
    version="0.1.0",
    author="Justin Koufopoulos",
    author_email="justin@example.com",  # Update this
    description="Intelligent email classification using AI and rules",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/mailq-prototype",  # Update this
    # Package discovery
    packages=find_packages(exclude=["tests", "experiments", "extension"]),
    # Dependencies
    install_requires=[
        "fastapi==0.104.1",
        "uvicorn==0.24.0",
        "pydantic==2.5.0",
        "google-cloud-aiplatform>=1.38.0",
        "python-dotenv>=1.0.0",
    ],
    # Optional dependencies (for development)
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "black>=23.0.0",
            "mypy>=1.0.0",
            "ruff>=0.1.0",
        ],
        "experiments": [
            "jupyter>=1.0.0",
            "matplotlib>=3.5.0",
            "pandas>=1.5.0",
        ],
    },
    # CLI commands
    entry_points={
        "console_scripts": [
            "mailq-api=mailq.api:main",
            "mailq-check=scripts.check_schema:main",
        ],
    },
    # Python version requirement
    python_requires=">=3.8",
    # PyPI classifiers
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)

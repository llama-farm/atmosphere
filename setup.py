"""
Atmosphere - The Internet of Intent
Zero-configuration AI mesh networking
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="atmosphere",
    version="1.0.0",
    author="Rownd AI",
    author_email="hello@rownd.ai",
    description="Semantic mesh routing for AI capabilities",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/rowndai/atmosphere",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: System :: Distributed Computing",
        "Topic :: System :: Networking",
    ],
    python_requires=">=3.10",
    install_requires=[
        "aiohttp>=3.9.0",
        "cryptography>=41.0.0",
        "fastapi>=0.109.0",
        "uvicorn>=0.25.0",
        "numpy>=1.24.0",
        "click>=8.0.0",
        "rich>=13.0.0",
        "zeroconf>=0.131.0",  # mDNS discovery
        "pydantic>=2.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.23.0",
            "httpx>=0.26.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "atmosphere=atmosphere.cli:main",
        ],
    },
)

from setuptools import setup, find_packages

setup(
    name="bunkrd",
    version="1.0.0",
    description="A tool to download files from Bunkr and Cyberdrop",
    author="BunkrDownloader Contributors",
    packages=find_packages(),
    install_requires=[
        "requests",
        "bs4",
        "argparse",
        "tqdm",
        "pysocks",        # For SOCKS proxy support
        "urllib3>=1.26.0" # For robust proxy support
    ],
    entry_points={
        "console_scripts": [
            "bunkrd=bunkrd.cli:main",
            "bunkrdownloader=bunkrd.cli:main",  # Keep old name as alias for backward compatibility
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
    python_requires=">=3.6",
)
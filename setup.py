from setuptools import setup, find_packages

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="ce-lib-wizard",
    version="0.1.0",
    description="CLI tool to add libraries to Compiler Explorer",
    author="",
    packages=find_packages(),
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "ce-lib-wizard=cli.main:main",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
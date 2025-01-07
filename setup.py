from setuptools import setup, find_packages

setup(
    name="mus1", 
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "numpy",
        "pandas", 
        "deeplabcut",
        "pyside6",
        "matplotlib"
    ],
    author="Lukas Platil",
    description="Mouse behavior analysis tool built on DeepLabCut",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/llplatil/mus-1",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "Programming Language :: Python :: 3.10",
    ],
    python_requires=">=3.10",
) 
# MUS1: Mouse Behavior Analysis Tool

A Python-based tool designed to streamline the analysis of DeepLabCut-processed mouse behavior data.

## Overview

MUS1 takes the CSV tracking files and arena images from your DeepLabCut projects and makes it easy to:
1. Visualize mouse movement patterns
2. Experiment with different behavior analysis parameters
3. Batch process multiple experiments using optimized settings

The project uses a "subjects/" directory structure to organize mouse-specific data.

## Current Focus (v0.1.0)

The initial version focuses on creating a smooth workflow where users can:
- Uplaod DeepLabCut-processed tracking files (CSV)
- Uplaod DLC config file 
- Upload corresponding arena images
- Visually explore movement patterns
- Test different analysis approaches through the Methods Explorer
- Apply successful analysis parameters across multiple experiments with multiple mouse IDs (batches)

## Project Status
Currently in early development. See our [Development Roadmap](docs/ROADMAP.md) for details.

## Documentation
- [Architecture Overview](docs/ARCHITECTURE.md)
- [Contributing Guide](docs/CONTRIBUTING.md)

## Future Goals
- drag drop file upload 
- Additional behavior analysis modules
- Automated parameter optimization
- Automated arena and object detection





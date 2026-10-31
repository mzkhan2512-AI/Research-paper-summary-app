---
title: PaperBrief AI
author: PaperBrief
emoji: 📄
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# PaperBrief AI — Research Paper Summarizer

Upload PDF or DOCX documents, read a Transformer-generated summary, and download it.

## Hosting

This repository is ready for a Hugging Face **Docker Space**. In a new Space choose Docker as SDK and upload the top-level files and the `static` directory. The Dockerfile installs the CPU version of PyTorch and starts the FastAPI app on port 7860.

**Important:** Hosting platform eligibility, quotas, free compute access, and billing policies can change. Check Hugging Face Spaces pricing before creating the Space. The first request downloads the DistilBART model; CPU summarization may be slow for long documents.

## Safety / privacy

A public Space permits internet visitors to upload documents. Uploaded contents are processed by the backend. Generated text files may be retained temporarily for download. Do not upload private material. This project is a classroom demo, not a hardened production service.

#!/usr/bin/env bash
cd "$(dirname "$0")/.." || exit 1
uv run streamlit run app/main.py

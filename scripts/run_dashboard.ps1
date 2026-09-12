# 네이버 마켓 인사이트 대시보드 실행 스크립트
Set-Location (Split-Path $PSScriptRoot -Parent)
uv run streamlit run app/main.py

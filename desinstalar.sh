#!/bin/bash

# Script de desinstalação do Busca Emprego Fácil

# Cores para o output
VERDE="\033[1;32m"
AMARELO="\033[1;33m"
VERMELHO="\033[1;31m"
RESET="\033[0m"

echo -e "${AMARELO}Iniciando a remoção dos componentes do Busca Emprego Fácil...${RESET}\n"

# 1. Remover arquivo desktop (atalho)
DESKTOP_FILE="$HOME/.local/share/applications/buscaempregofacil.desktop"
if [ -f "$DESKTOP_FILE" ]; then
    rm "$DESKTOP_FILE"
    echo -e "${VERDE}[OK]${RESET} Atalho de aplicativo removido: $DESKTOP_FILE"
else
    echo -e "${AMARELO}[Aviso]${RESET} Atalho de aplicativo não encontrado."
fi

# 2. Remover ícone
ICON_FILE="$HOME/.local/share/icons/buscaempregofacil.png"
if [ -f "$ICON_FILE" ]; then
    rm "$ICON_FILE"
    echo -e "${VERDE}[OK]${RESET} Ícone de aplicativo removido: $ICON_FILE"
else
    echo -e "${AMARELO}[Aviso]${RESET} Ícone de aplicativo não encontrado."
fi

# 3. Remover arquivos de log
LOG_DIR="$HOME/.local/log"
if [ -d "$LOG_DIR" ]; then
    # Remove apenas logs criados por este aplicativo
    find "$LOG_DIR" -type f -name "job_hunter_*.log" -delete
    echo -e "${VERDE}[OK]${RESET} Arquivos de log do Busca Emprego Fácil removidos de $LOG_DIR"
fi

# 4. Remover ambiente virtual .venv do projeto
VENV_DIR="$(dirname "$0")/.venv"
if [ -d "$VENV_DIR" ]; then
    rm -rf "$VENV_DIR"
    echo -e "${VERDE}[OK]${RESET} Pasta do ambiente virtual (.venv) removida."
fi

# 5. Remover arquivos de configuração gerados
CONFIG_FILE="$(dirname "$0")/config_vagas.json"
if [ -f "$CONFIG_FILE" ]; then
    rm "$CONFIG_FILE"
    echo -e "${VERDE}[OK]${RESET} Arquivo config_vagas.json removido."
fi

# 6. Notificar o sistema sobre a atualização dos atalhos desktop
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$HOME/.local/share/applications" &> /dev/null
fi

echo -e "\n${VERDE}Desinstalação concluída com sucesso!${RESET}"

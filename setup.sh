#!/bin/bash
# Atmosphere - Zero-Friction Setup Script
# One command to join the mesh

set -e

BOLD="\033[1m"
GREEN="\033[0;32m"
BLUE="\033[0;34m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
NC="\033[0m" # No Color

echo -e "${BOLD}${BLUE}"
echo "    ╔═══════════════════════════════════════════════════╗"
echo "    ║         🌐 ATMOSPHERE - Internet of Intent        ║"
echo "    ╚═══════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)

if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 10 ]); then
    echo -e "${RED}Error: Python 3.10+ required (found $PYTHON_VERSION)${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION detected"

# Create virtual environment if not exists
if [ ! -d ".venv" ]; then
    echo -e "${BLUE}→${NC} Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Install package in editable mode
echo -e "${BLUE}→${NC} Installing Atmosphere..."
pip install -q -e .

# Run initialization
echo ""
echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}Running Atmosphere Initialization...${NC}"
echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""

atmosphere init

echo ""
echo -e "${BOLD}${GREEN}════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${GREEN}                   Setup Complete! 🎉${NC}"
echo -e "${BOLD}${GREEN}════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "Quick Start Commands:"
echo -e "  ${BLUE}atmosphere serve${NC}       Start the API server"
echo -e "  ${BLUE}atmosphere mesh create${NC} Create a new mesh network"
echo -e "  ${BLUE}atmosphere mesh join${NC}   Join an existing mesh"
echo -e "  ${BLUE}atmosphere status${NC}      Show node status"
echo ""
echo -e "Activate the virtual environment:"
echo -e "  ${YELLOW}source .venv/bin/activate${NC}"
echo ""

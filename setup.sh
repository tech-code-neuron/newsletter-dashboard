#!/bin/bash

# Press Release Pipeline Setup Script
# Run this once to set up everything

set -e  # Exit on error

echo "====================================="
echo "Press Release Pipeline System Setup"
echo "====================================="
echo ""

# Check Python version
echo "Checking Python version..."
python3 --version || { echo "Python 3 not found. Please install Python 3.8+"; exit 1; }

# Create virtual environment
echo ""
echo "Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt
echo "✓ Dependencies installed"

# Set up .env file
echo ""
if [ ! -f ".env" ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "✓ .env file created"
    echo ""
    echo "⚠️  IMPORTANT: Edit .env and add your ANTHROPIC_API_KEY"
    echo "   Get your API key at: https://console.anthropic.com/"
else
    echo "✓ .env file already exists"
fi

# Create directories
echo ""
echo "Creating data directories..."
mkdir -p data
mkdir -p data/newsletters
mkdir -p logs
echo "✓ Directories created"

# Initialize database
echo ""
echo "Initializing database..."
python core/models.py
echo "✓ Database initialized"

# Load companies
echo ""
echo "Would you like to load the companies now? (y/n)"
read -r response
if [[ "$response" =~ ^[Yy]$ ]]; then
    echo "Loading companies (this may take a few minutes)..."
    python scripts/load_companies.py
    echo "✓ Companies loaded"
else
    echo "Skipping company load. Run 'python scripts/load_companies.py' later to load companies."
fi

echo ""
echo "====================================="
echo "Setup Complete! 🎉"
echo "====================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Edit .env and add your ANTHROPIC_API_KEY"
echo "   Get one at: https://console.anthropic.com/"
echo ""
echo "2. Start the web interface:"
echo "   source venv/bin/activate"
echo "   python app.py"
echo ""
echo "3. Open http://localhost:5001 in your browser"
echo ""
echo "4. Click 'Run Scraper' to fetch press releases"
echo ""
echo "For full documentation, see README.md"
echo ""

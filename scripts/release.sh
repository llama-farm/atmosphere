#!/bin/bash
# =============================================================================
# Atmosphere Release Script
# Builds and prepares a release package
# =============================================================================
#
# Usage:
#   ./scripts/release.sh [VERSION]
#
# Examples:
#   ./scripts/release.sh          # Uses version from pyproject.toml
#   ./scripts/release.sh 1.1.0    # Sets specific version
#   ./scripts/release.sh patch    # Bump patch version (1.0.0 -> 1.0.1)
#   ./scripts/release.sh minor    # Bump minor version (1.0.0 -> 1.1.0)
#   ./scripts/release.sh major    # Bump major version (1.0.0 -> 2.0.0)
#
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------

log_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

get_current_version() {
    grep '^version = ' pyproject.toml | cut -d'"' -f2
}

bump_version() {
    local current=$1
    local part=$2
    
    IFS='.' read -ra parts <<< "$current"
    local major=${parts[0]}
    local minor=${parts[1]}
    local patch=${parts[2]}
    
    case $part in
        major) echo "$((major + 1)).0.0" ;;
        minor) echo "$major.$((minor + 1)).0" ;;
        patch) echo "$major.$minor.$((patch + 1))" ;;
        *) echo "$part" ;;  # Assume it's a version string
    esac
}

update_version() {
    local new_version=$1
    
    # Update pyproject.toml
    sed -i '' "s/^version = \".*\"/version = \"$new_version\"/" pyproject.toml
    
    # Update atmosphere/__init__.py if it has a version
    if grep -q '__version__' atmosphere/__init__.py 2>/dev/null; then
        sed -i '' "s/__version__ = \".*\"/__version__ = \"$new_version\"/" atmosphere/__init__.py
    fi
}

# -----------------------------------------------------------------------------
# Main script
# -----------------------------------------------------------------------------

echo ""
echo -e "${BLUE}🚀 Atmosphere Release Builder${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Get current version
CURRENT_VERSION=$(get_current_version)
log_info "Current version: $CURRENT_VERSION"

# Determine new version
if [ -n "$1" ]; then
    case $1 in
        major|minor|patch)
            NEW_VERSION=$(bump_version "$CURRENT_VERSION" "$1")
            ;;
        *)
            NEW_VERSION="$1"
            ;;
    esac
else
    NEW_VERSION="$CURRENT_VERSION"
fi

if [ "$NEW_VERSION" != "$CURRENT_VERSION" ]; then
    log_info "Bumping to version: $NEW_VERSION"
    update_version "$NEW_VERSION"
fi

VERSION="$NEW_VERSION"

echo ""
echo -e "${BLUE}Building version $VERSION${NC}"
echo ""

# Step 1: Clean previous builds
log_info "Cleaning previous builds..."
rm -rf dist/ build/ *.egg-info atmosphere_mesh.egg-info
log_success "Cleaned"

# Step 2: Build UI (if exists)
if [ -d "ui" ] && [ -f "ui/package.json" ]; then
    log_info "Building UI..."
    cd ui
    npm ci 2>/dev/null || npm install
    npm run build
    cd ..
    
    # Bundle UI into package
    rm -rf atmosphere/ui/dist
    mkdir -p atmosphere/ui
    cp -r ui/dist atmosphere/ui/
    log_success "UI built and bundled"
else
    log_warning "No UI directory found, skipping UI build"
fi

# Step 3: Build Python package
log_info "Building Python package..."
python -m build
log_success "Package built"

# Step 4: Verify package
log_info "Verifying package..."
if command -v twine &> /dev/null; then
    twine check dist/*
    log_success "Package verified"
else
    log_warning "twine not installed, skipping verification"
fi

# Step 5: Test install in clean venv
log_info "Testing installation in clean virtualenv..."
TEMP_VENV=$(mktemp -d)
python -m venv "$TEMP_VENV"
source "$TEMP_VENV/bin/activate"
pip install --quiet dist/atmosphere_mesh-${VERSION}-py3-none-any.whl

# Test CLI
if atmosphere --help > /dev/null 2>&1; then
    log_success "CLI works"
else
    log_error "CLI test failed"
    deactivate
    rm -rf "$TEMP_VENV"
    exit 1
fi

deactivate
rm -rf "$TEMP_VENV"
log_success "Installation test passed"

# Step 6: Show results
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✨ Build complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Built packages:"
ls -la dist/
echo ""

# Step 7: Show next steps
echo "Next steps:"
echo ""
echo "  1. Test locally:"
echo "     pip install dist/atmosphere_mesh-${VERSION}-py3-none-any.whl"
echo ""
echo "  2. Upload to TestPyPI:"
echo "     twine upload --repository testpypi dist/*"
echo ""
echo "  3. Test from TestPyPI:"
echo "     pip install --index-url https://test.pypi.org/simple/ atmosphere-mesh"
echo ""
echo "  4. Upload to PyPI:"
echo "     twine upload dist/*"
echo ""
echo "  5. Create git tag:"
echo "     git add -A"
echo "     git commit -m 'Release v${VERSION}'"
echo "     git tag -a 'v${VERSION}' -m 'Version ${VERSION}'"
echo "     git push && git push --tags"
echo ""
echo "  6. Build Docker image:"
echo "     docker build -t llama-farm/atmosphere:${VERSION} ."
echo "     docker push llama-farm/atmosphere:${VERSION}"
echo ""

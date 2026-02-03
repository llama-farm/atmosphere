# Homebrew formula for Atmosphere
# The Internet of Intent - semantic mesh routing for AI capabilities

class Atmosphere < Formula
  include Language::Python::Virtualenv

  desc "The Internet of Intent - semantic mesh routing for AI capabilities"
  homepage "https://github.com/llama-farm/atmosphere"
  url "https://files.pythonhosted.org/packages/source/a/atmosphere-mesh/atmosphere-mesh-1.0.0.tar.gz"
  sha256 "REPLACE_WITH_ACTUAL_SHA256_AFTER_PYPI_UPLOAD"
  license "Apache-2.0"
  head "https://github.com/llama-farm/atmosphere.git", branch: "main"

  depends_on "python@3.12"
  depends_on "rust" => :build  # For cryptography

  # Core dependencies - generate with: poet --resources atmosphere-mesh
  # Run: pip install homebrew-pypi-poet && poet --resources atmosphere-mesh
  
  resource "aiohttp" do
    url "https://files.pythonhosted.org/packages/source/a/aiohttp/aiohttp-3.9.0.tar.gz"
    sha256 "REPLACE_WITH_SHA256"
  end

  resource "click" do
    url "https://files.pythonhosted.org/packages/source/c/click/click-8.1.7.tar.gz"
    sha256 "ca9853ad459e787e2192211578cc907e7594e294c7ccc834310722b41b9ca6de"
  end

  resource "cryptography" do
    url "https://files.pythonhosted.org/packages/source/c/cryptography/cryptography-41.0.7.tar.gz"
    sha256 "REPLACE_WITH_SHA256"
  end

  resource "fastapi" do
    url "https://files.pythonhosted.org/packages/source/f/fastapi/fastapi-0.109.0.tar.gz"
    sha256 "REPLACE_WITH_SHA256"
  end

  resource "httpx" do
    url "https://files.pythonhosted.org/packages/source/h/httpx/httpx-0.26.0.tar.gz"
    sha256 "REPLACE_WITH_SHA256"
  end

  resource "numpy" do
    url "https://files.pythonhosted.org/packages/source/n/numpy/numpy-1.26.3.tar.gz"
    sha256 "REPLACE_WITH_SHA256"
  end

  resource "pydantic" do
    url "https://files.pythonhosted.org/packages/source/p/pydantic/pydantic-2.5.3.tar.gz"
    sha256 "REPLACE_WITH_SHA256"
  end

  resource "psutil" do
    url "https://files.pythonhosted.org/packages/source/p/psutil/psutil-5.9.8.tar.gz"
    sha256 "REPLACE_WITH_SHA256"
  end

  resource "PyYAML" do
    url "https://files.pythonhosted.org/packages/source/P/PyYAML/PyYAML-6.0.1.tar.gz"
    sha256 "bfdf460b1736c775f2ba9f6a92bca30bc2095067b8a9d77876d1fad6cc3b4a43"
  end

  resource "rich" do
    url "https://files.pythonhosted.org/packages/source/r/rich/rich-13.7.0.tar.gz"
    sha256 "REPLACE_WITH_SHA256"
  end

  resource "uvicorn" do
    url "https://files.pythonhosted.org/packages/source/u/uvicorn/uvicorn-0.25.0.tar.gz"
    sha256 "REPLACE_WITH_SHA256"
  end

  resource "zeroconf" do
    url "https://files.pythonhosted.org/packages/source/z/zeroconf/zeroconf-0.131.0.tar.gz"
    sha256 "REPLACE_WITH_SHA256"
  end

  # Additional transitive dependencies would be added here
  # Use `poet --resources atmosphere-mesh` to generate complete list

  def install
    # Install Python package into virtualenv
    virtualenv_install_with_resources

    # Generate shell completions
    generate_completions_from_executable(
      bin/"atmosphere",
      shells: [:bash, :zsh, :fish],
      shell_parameter_format: :click
    )
  end

  def post_install
    # Create data directory
    (var/"atmosphere").mkpath
    (var/"log/atmosphere").mkpath
  end

  def caveats
    <<~EOS
      Atmosphere has been installed!

      To get started:
        atmosphere init           # Initialize this node
        atmosphere serve          # Start the API server
        atmosphere scan           # Scan for AI backends

      To start atmosphere as a background service:
        brew services start atmosphere

      Data is stored in:
        #{var}/atmosphere

      Logs are stored in:
        #{var}/log/atmosphere

      For more information:
        atmosphere --help
        https://github.com/llama-farm/atmosphere
    EOS
  end

  # Background service definition (launchd on macOS)
  service do
    run [opt_bin/"atmosphere", "serve"]
    working_dir var/"atmosphere"
    log_path var/"log/atmosphere/atmosphere.log"
    error_log_path var/"log/atmosphere/atmosphere-error.log"
    keep_alive true
    environment_variables PATH: std_service_path_env
  end

  test do
    # Basic CLI test
    assert_match "Atmosphere", shell_output("#{bin}/atmosphere --version")

    # Help test
    assert_match "Commands", shell_output("#{bin}/atmosphere --help")

    # Scan help test
    assert_match "scan", shell_output("#{bin}/atmosphere scan --help")
  end
end

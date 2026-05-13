import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

project = "ALine"
copyright = "2026, ALine Contributors"
author = "ALine Contributors"
version = "0.3"
release = "0.3.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

templates_path = ["_templates"]
exclude_patterns = []
language = "zh_CN"

html_theme = "alabaster"
html_static_path = ["_static"]

master_doc = "index"

autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
    "special-members": "__init__",
}

intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}

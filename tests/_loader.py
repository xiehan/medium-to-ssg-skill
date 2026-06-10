"""Shared helpers for the helper-script test suite.

The two scripts under test live inside skill directories and are meant to be
run directly (``python3 scrape_publication.py``), not imported as a package.
They are loaded here by file path with ``importlib`` so the tests can exercise
their pure functions without any packaging changes to the scripts themselves.
Both modules guard ``main()`` behind ``if __name__ == "__main__"``, so importing
them has no side effects.
"""
import importlib.util
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONVERT_MEDIUM_PATH = os.path.join(
    REPO_ROOT, ".agents", "skills", "medium-to-ssg", "scripts", "convert_medium.py"
)
SCRAPE_PUBLICATION_PATH = os.path.join(
    REPO_ROOT,
    ".agents",
    "skills",
    "medium-publication-export",
    "scripts",
    "scrape_publication.py",
)


def load_module(name, path):
    """Import a standalone script by file path."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

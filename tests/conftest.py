"""
Shared pytest configuration.
Changes working directory to project root so all relative paths
(static/, data/) resolve correctly regardless of where pytest is invoked from.
"""
import os
import sys

# ── Project root on sys.path ─────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)
sys.path.insert(0, PROJECT_ROOT)

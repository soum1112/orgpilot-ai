#!/usr/bin/env python
"""Django command-line entry point for the shared OrgPilot AI project (run from the repo root)."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orgpilot_platform.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()

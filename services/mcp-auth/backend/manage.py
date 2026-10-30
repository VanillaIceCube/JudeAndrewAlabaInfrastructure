#!/usr/bin/env python
"""Django's maintained management entry point; no implicit deployment/startup."""
import os
os.umask(0o077)
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "auth_service.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)

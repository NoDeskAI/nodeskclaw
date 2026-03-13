"""Entrypoint wrapper: inject security layer then start nanobot CLI."""

import sys

from nanobot_security_layer.injector import inject_security_layer

inject_security_layer()

sys.argv = ["nanobot"] + sys.argv[1:]

from nanobot.cli import main  # noqa: E402

sys.exit(main())

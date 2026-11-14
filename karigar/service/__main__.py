"""`python -m karigar.service` starts the HTTP service (what Render runs)."""
import sys

from karigar.service.http import main

sys.exit(main())

from __future__ import annotations

import sys

from main import main, rewrite_source_first_argv


if __name__ == "__main__":
    sys.argv = rewrite_source_first_argv(sys.argv)
    main()

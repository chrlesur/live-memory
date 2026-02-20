# -*- coding: utf-8 -*-
"""
Point d'entrée pour python -m live_mem.

Permet de démarrer le serveur avec :
    cd src && python -m live_mem
    # ou
    cd src && python -m live_mem.server
"""

from .server import main

if __name__ == "__main__":
    main()

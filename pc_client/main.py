"""
Punto de entrada principal para DroidLens en Windows.
"""

import sys
import os

# Asegurar que 'src' esté en el sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from ui.app_window import DroidLensApp

def main():
    app = DroidLensApp()
    app.mainloop()

if __name__ == "__main__":
    main()

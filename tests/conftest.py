import sys
import os

# Append the project `src/` directory to the path so pytest can find it
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

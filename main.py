import sys
import os

# Get the directory where main.py resides
current_dir = os.path.dirname(os.path.abspath(__file__))

# Add the directory to sys.path so Python can find modules
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Now it should be able to import from the same folder
try:
    from engine import GesturePuzzleApp
except ImportError as e:
    print(f"Import Error: {e}")
    print(f"Current Directory: {current_dir}")
    print(f"Files in folder: {os.listdir(current_dir)}")
    sys.exit(1)

if __name__ == "__main__":
    app = GesturePuzzleApp()
    app.run()
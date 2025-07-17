# run_dev.py
"""
A development-only script that uses `watchgod` to run the main PySide6
application and automatically restart it upon file changes.
"""
import multiprocessing
import sys
from pathlib import Path

from watchgod import watch
from watchgod.watcher import DefaultWatcher

def run_app():
    """The target function for the subprocess."""
    import main
    main.main()

class PythonSourceWatcher(DefaultWatcher):
    """
    A custom watchgod watcher that only triggers for changes to .py files
    and ignores common development/data directories.
    """
    def __init__(self, root_path):
        # --- CORRECTED: Call the parent class's constructor ---
        super().__init__(root_path)
        # ---------------------------------------------------
        
        self.ignored_dirs = {
            str(root_path / '.venv'),
            str(root_path / '.git'),
            str(root_path / 'data'),
            str(root_path / 'dist'),
            str(root_path / 'build'),
        }
        for p in Path(root_path).rglob('__pycache__'):
            self.ignored_dirs.add(str(p))

    def should_watch_dir(self, entry):
        # Prevent descending into ignored directories
        if not super().should_watch_dir(entry):
            return False
        return entry.path not in self.ignored_dirs

    def should_watch_file(self, entry):
        # Only watch .py files
        return entry.name.endswith('.py')

if __name__ == "__main__":
    if sys.platform in ["win32", "darwin"]:
        multiprocessing.set_start_method("spawn")

    print("--- Starting development watcher for Python source files ---")
    
    watch_path = Path(__file__).parent
    
    process = multiprocessing.Process(target=run_app, daemon=True)
    process.start()
    print(f"--- Started application process [PID: {process.pid}] ---")

    try:
        # Use the `watcher_cls` argument to pass our custom watcher class.
        for changes in watch(watch_path, watcher_cls=PythonSourceWatcher):
            print("\n--- Detected Python code changes ---")
            for change_type, path in changes:
                print(f"  - {change_type.name.capitalize()}: {Path(path).relative_to(watch_path)}")
            
            print(f"--- Terminating old process [PID: {process.pid}]... ---")
            process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                print("--- Process did not terminate gracefully, killing... ---")
                process.kill()
            
            print("--- Restarting application... ---")
            
            process = multiprocessing.Process(target=run_app, daemon=True)
            process.start()
            print(f"--- Started new application process [PID: {process.pid}] ---")
            
    except KeyboardInterrupt:
        print("\n--- Watcher stopped by user. Shutting down application. ---")
        process.terminate()
        process.join(timeout=2)
        print("--- Shutdown complete. ---")
import os
import shutil

# Ensure the download directory exists and return its absolute path.
# - dirfile: relative or absolute path where files should be stored.
# - Creates the folder if missing, to avoid errors on later file writes.
def setupDownloadDir(dirfile="downloads"):
    download_dir = os.path.abspath(dirfile)
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)
    return download_dir

# Remove all contents of the download directory, preserving the directory itself.
# - Handles files, symlinks, and subdirectories.
# - Logs but ignores individual delete errors to keep cleanup robust.
def clearDownloadDir(download_dir):
    for entry in os.listdir(download_dir):
        path = os.path.join(download_dir, entry)
        try:
            if os.path.isfile(path) or os.path.islink(path):
                os.unlink(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
        except Exception as e:
            print(f"Could not remove {path}: {e}")
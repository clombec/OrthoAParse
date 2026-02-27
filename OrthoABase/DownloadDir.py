import os
import shutil

def setupDownloadDir(dirfile="downloads", noclean=False):
    download_dir = os.path.abspath(dirfile)
    if os.path.exists(download_dir) and not noclean:
        for entry in os.listdir(download_dir):
            path = os.path.join(download_dir, entry)
            try:
                if os.path.isfile(path) or os.path.islink(path):
                    os.unlink(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)
            except Exception as e:
                print(f"Could not remove {path}: {e}")
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)
    return download_dir
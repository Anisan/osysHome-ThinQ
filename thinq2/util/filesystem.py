from app.core.lib.cache import getFullFilename

class TempDir:
    def __init__(self):
        pass

    def file(self, name, content: str = None):
        file_path = getFullFilename(name,"ThinQ")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return file_path

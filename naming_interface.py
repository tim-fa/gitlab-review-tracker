import os
import json

class NamingInterface:

    def __init__(self):
        self.constants = {}
        with open(os.path.join(os.path.dirname(__file__), "constants.json"), "r", encoding="utf-8") as f:
            self.constants = json.load(f)

    def get_attr(self, key: str) -> str:
        return self.constants.get(key, "")
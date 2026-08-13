import re
from typing import Optional

class IncrementalJsonParser:
    """
    Parser that extracts incremental text tokens from a streaming JSON response
    where the target field is 'response': "...".
    """
    def __init__(self, target_key: str = "response"):
        self.target_key = target_key
        self.buffer = ""
        self.inside_target = False
        self.escaped = False
        self.matched_index = 0
        self.key_pattern = f'"{target_key}"'

    def feed(self, chunk: str) -> str:
        """
        Feed a raw chunk from LLM streaming and return newly emitted target text characters.
        """
        if not chunk:
            return ""

        self.buffer += chunk
        emitted = []

        while self.matched_index < len(self.buffer):
            char = self.buffer[self.matched_index]

            if not self.inside_target:
                # Look for target_key and colon then opening quote
                idx = self.buffer.find(self.key_pattern, self.matched_index)
                if idx != -1:
                    colon_idx = self.buffer.find(":", idx + len(self.key_pattern))
                    if colon_idx != -1:
                        # Find opening quote
                        quote_idx = -1
                        for i in range(colon_idx + 1, len(self.buffer)):
                            if self.buffer[i].isspace():
                                continue
                            if self.buffer[i] == '"':
                                quote_idx = i
                                break
                            else:
                                break
                        if quote_idx != -1:
                            self.inside_target = True
                            self.matched_index = quote_idx + 1
                            continue
                break
            else:
                if self.escaped:
                    if char == 'n':
                        emitted.append('\n')
                    elif char == 't':
                        emitted.append('\t')
                    elif char == 'r':
                        emitted.append('\r')
                    elif char == '"':
                        emitted.append('"')
                    elif char == '\\':
                        emitted.append('\\')
                    else:
                        emitted.append(char)
                    self.escaped = False
                elif char == '\\':
                    self.escaped = True
                elif char == '"':
                    self.inside_target = False
                    self.matched_index += 1
                    break
                else:
                    emitted.append(char)

                self.matched_index += 1

        return "".join(emitted)

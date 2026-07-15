"""
Utility for parsing streamed JSON responses incrementally.
Specially designed for extracting the "response" field from a JSON object
being streamed from an LLM.
"""

import re

class IncrementalJsonParser:
    """
    Parses a JSON stream chunk by chunk, extracting only the value of the "response" key.
    Handles basic string escaping (newlines, tabs, quotes).
    """

    def __init__(self):
        self.buffer = ""
        self.found_key = False
        self.in_string = False
        self.escaped = False
        self.finished = False
        self._key_regex = re.compile(r'"response"\s*:\s*"')

    def feed(self, chunk: str) -> str:
        """
        Feeds a chunk of text into the parser and returns the parsed characters for the "response" field.
        """
        if self.finished:
            return ""

        output = []
        if not self.found_key:
            self.buffer += chunk
            match = self._key_regex.search(self.buffer)
            if match:
                self.found_key = True
                self.in_string = True
                remaining = self.buffer[match.end():]
                self.buffer = ""
                self._process_chars(remaining, output)
        else:
            if self.in_string:
                self._process_chars(chunk, output)

        return "".join(output)

    def _process_chars(self, chars: str, output: list[str]) -> None:
        for char in chars:
            if self.escaped:
                if char == 'n':
                    output.append('\n')
                elif char == 't':
                    output.append('\t')
                else:
                    output.append(char)
                self.escaped = False
            elif char == '\\':
                self.escaped = True
            elif char == '"':
                self.in_string = False
                self.finished = True
                break
            else:
                output.append(char)

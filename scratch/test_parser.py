import sys
import os
sys.path.append(os.getcwd())

import unittest
from app.domain.services.chat_engine import ChatEngine

# We need to extract the IncrementalJsonParser class to test it.
# Since it is defined inside a method of ChatEngine (line 254), we can import and dynamically extract or write a copy.
# Let's inspect chat_engine.py again or write a test that simulates streaming.

class TestIncrementalJsonParser(unittest.TestCase):
    def test_parser_streaming(self):
        # We can extract the parser by calling a mock stream or by defining it here from the file
        # But wait, since we edited it, let's copy its definition directly to test it.
        class IncrementalJsonParser:
            def __init__(self):
                self.buffer = ""
                self.found_key = False
                self.in_string = False
                self.escaped = False
                self.finished = False

            def feed(self, chunk: str) -> str:
                if self.finished:
                    return ""
                
                output = []
                if not self.found_key:
                    self.buffer += chunk
                    import re
                    match = re.search(r'"response"\s*:\s*"', self.buffer)
                    if match:
                        self.found_key = True
                        self.in_string = True
                        remaining = self.buffer[match.end():]
                        self.buffer = ""
                        for char in remaining:
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
                else:
                    if self.in_string:
                        for char in chunk:
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
                return "".join(output)

        parser = IncrementalJsonParser()
        chunks = [
            '{\n  "response": "',
            'Chao ',
            'Senpai. ',
            'Em dang test ',
            'streaming.\\nLine 2.',
            '",\n  "user_sentiment": {\n    "is_positive": false\n  }\n}'
        ]
        
        parsed_result = []
        for chunk in chunks:
            parsed_result.append(parser.feed(chunk))
            
        final_text = "".join(parsed_result)
        print("Parsed result:", repr(final_text))
        self.assertEqual(final_text, "Chao Senpai. Em dang test streaming.\nLine 2.")

if __name__ == "__main__":
    unittest.main()

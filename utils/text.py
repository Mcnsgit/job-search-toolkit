from html.parser import HTMLParser
import re

class _HTMLTagStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = []

    def handle_data(self, d):
        self.text.append(d)

    def get_data(self):
        return "".join(self.text)

def clean_html(raw_html: str) -> str:
    """Converts raw HTML strings into clean text using standard library HTMLParser."""
    if not raw_html:
        return ""
    stripper = _HTMLTagStripper()
    stripper.feed(raw_html)
    text = stripper.get_data()
    # Normalize excessive whitespace
    return re.sub(r"\s+", " ", text).strip()
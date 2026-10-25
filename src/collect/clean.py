"""Turn raw job-board HTML into clean plain text for the model to read."""
import html
import re
from html.parser import HTMLParser

# Tags that start a new line on a web page. Inline tags (strong, span, a, em)
# don't, so their text stays on the same line.
BLOCK_TAGS = {
    "p", "div", "br", "hr", "ul", "ol", "li", "tr", "table", "section",
    "h1", "h2", "h3", "h4", "h5", "h6",
}


class _TextExtractor(HTMLParser):
    """Collects the visible text, adding line breaks where the page would."""

    def __init__(self):
        # convert_charrefs: turn &amp; &nbsp; &#8377; into & (space) ₹ inside text
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            self.parts.append("\n- ")  # keep bullets: requirements are often lists
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in BLOCK_TAGS and tag != "li":  # the next <li> already starts a new line
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def tidy_whitespace(text):
    """Collapse the spacing mess left behind by HTML into readable lines."""
    text = text.replace("\xa0", " ")  # non-breaking space (&nbsp;) -> normal space
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"(?m)^-\n+(?=\S)", "- ", text)  # "<li><p>x</p></li>" left "-" alone on a line
    text = re.sub(r"(?m)^(- .*)\n\n(?=- )", r"\1\n", text)  # no blank line between bullets
    text = re.sub(r"\n{3,}", "\n\n", text)  # at most one blank line in a row
    return text.strip()


def html_to_text(markup):
    """Plain text from normal HTML (what Lever sends)."""
    parser = _TextExtractor()
    parser.feed(markup or "")
    parser.close()
    return tidy_whitespace("".join(parser.parts))


def escaped_html_to_text(markup):
    """Plain text from escaped HTML (what Greenhouse sends: &lt;p&gt; instead of <p>).

    Unescape exactly once to get real HTML, then parse it. Unescaping twice
    would turn a literal "&lt;" in the text into "<" and the parser would
    mistake it for the start of a tag.
    """
    return html_to_text(html.unescape(markup or ""))

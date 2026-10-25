from src.collect.clean import escaped_html_to_text, html_to_text


def test_inline_tags_stay_on_one_line():
    assert html_to_text("<p>Use <strong>Python</strong> daily</p>") == "Use Python daily"


def test_paragraphs_become_separate_lines():
    assert html_to_text("<p>About us</p><p>We build things.</p>") == "About us\n\nWe build things."


def test_list_items_become_bullets():
    assert html_to_text("<ul><li>Python</li><li>SQL</li></ul>") == "- Python\n- SQL"


def test_list_items_wrapping_paragraphs():
    # Common in Greenhouse postings: <li><p>...</p></li>
    markup = "<ul><li><p>Python</p></li><li><p>SQL</p></li></ul>"
    assert html_to_text(markup) == "- Python\n- SQL"


def test_entities_in_normal_html():
    assert html_to_text("<p>R&amp;D&nbsp;team</p>") == "R&D team"


def test_messy_whitespace_collapsed():
    assert html_to_text("<p>  lots   of\tspace </p><br><br><br><p>next</p>") == "lots of space\n\nnext"


def test_escaped_html_is_unescaped_once():
    # Greenhouse: the HTML itself is escaped, and entities inside it are escaped again.
    markup = "&lt;p&gt;R&amp;amp;D&amp;nbsp;team&lt;/p&gt;"
    assert escaped_html_to_text(markup) == "R&D team"


def test_rupee_sign_survives():
    markup = "&lt;p&gt;Stipend: &amp;#8377;15K/month&lt;/p&gt;"
    assert escaped_html_to_text(markup) == "Stipend: ₹15K/month"


def test_literal_angle_brackets_are_not_treated_as_tags():
    # A frontend posting talking about HTML. Unescaping twice would turn
    # "<table>" into a real tag and silently delete the word.
    markup = "&lt;p&gt;Write semantic &amp;lt;table&amp;gt; markup&lt;/p&gt;"
    assert escaped_html_to_text(markup) == "Write semantic <table> markup"


def test_missing_content_gives_empty_string():
    assert html_to_text(None) == ""
    assert escaped_html_to_text("") == ""

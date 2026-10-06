import pytest
from app.qa.render_verify import reordered_math_glyphs


@pytest.mark.parametrize('expected,extracted',[
    ('Notation:∇f','Notation:f∇'),
    ('x0=[3;4]⟹f(x0)=x0','x0=[3;4]f(x⟹0)=x0T'),
    ('dx=[.001;.002]⟹(3.001)2+(4.002)2=25.022005','dx=[.001;.002](3.001)⟹2+(4.002)2=25.022005'),
])
def test_fallback_math_font_extraction_is_identified(expected,extracted):
    assert reordered_math_glyphs(expected,extracted)


@pytest.mark.parametrize('expected,extracted',[
    ('Notation:∇f','Notation:f'),  # absent symbol
    ('x⟹y','x⇒y'),  # changed symbol
    ('x⟹y','y⟹x'),  # changed wording order
    ('x∇∇f','x∇f'),  # missing repeated symbol
    ('abcdef','fedcba'),  # arbitrary reordering is not math-font extraction
    ('∇','∇'),  # symbol alone provides no ordered-wording evidence
])
def test_missing_or_changed_content_is_not_dismissed(expected,extracted):
    assert not reordered_math_glyphs(expected,extracted)

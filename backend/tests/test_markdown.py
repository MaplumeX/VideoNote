from app.services.markdown import normalize_note_markdown


def test_normalize_note_markdown_removes_markdown_fence() -> None:
    markdown = """```markdown
## Summary

- One point
```"""

    assert normalize_note_markdown(markdown) == "## Summary\n\n- One point"


def test_normalize_note_markdown_removes_plain_outer_fence() -> None:
    markdown = """```
## Summary
```"""

    assert normalize_note_markdown(markdown) == "## Summary"


def test_normalize_note_markdown_preserves_inner_code_block() -> None:
    markdown = """## Summary

```python
print("hello")
```"""

    assert normalize_note_markdown(markdown) == markdown

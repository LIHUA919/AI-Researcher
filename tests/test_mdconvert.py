"""Tests for MarkdownConverter with sample inputs."""

import io
import os
import tempfile

import pytest

from research_agent.inno.environment.markdown_browser.mdconvert import (
    DocumentConverterResult,
    HtmlConverter,
    MarkdownConverter,
    PlainTextConverter,
)


class TestPlainTextConverter:
    def test_converts_txt(self, tmp_dir):
        path = os.path.join(tmp_dir, "test.txt")
        with open(path, "w") as f:
            f.write("Hello world")
        conv = PlainTextConverter()
        result = conv.convert(path, file_extension=".txt")
        assert result is not None
        assert "Hello world" in result.text_content

    def test_rejects_binary(self, tmp_dir):
        path = os.path.join(tmp_dir, "test.bin")
        with open(path, "wb") as f:
            f.write(b"\x00\x01\x02")
        conv = PlainTextConverter()
        result = conv.convert(path, file_extension=".bin")
        assert result is None


class TestHtmlConverter:
    def test_converts_html(self, tmp_dir):
        path = os.path.join(tmp_dir, "test.html")
        with open(path, "w") as f:
            f.write("<html><body><h1>Title</h1><p>Content</p></body></html>")
        conv = HtmlConverter()
        result = conv.convert(path, file_extension=".html")
        assert result is not None
        assert "Title" in result.text_content
        assert "Content" in result.text_content

    def test_rejects_non_html(self, tmp_dir):
        path = os.path.join(tmp_dir, "test.py")
        with open(path, "w") as f:
            f.write("print('hi')")
        conv = HtmlConverter()
        result = conv.convert(path, file_extension=".py")
        assert result is None


class TestMarkdownConverter:
    def test_convert_stream(self):
        mc = MarkdownConverter()
        html = "<html><body><h1>Test</h1></body></html>"
        result = mc.convert_stream(io.StringIO(html), file_extension=".html")
        assert result is not None
        assert "Test" in result.text_content

    def test_convert_local_txt(self, tmp_dir):
        path = os.path.join(tmp_dir, "readme.txt")
        with open(path, "w") as f:
            f.write("readme content here")
        mc = MarkdownConverter()
        result = mc.convert_local(path)
        assert result is not None
        assert "readme content here" in result.text_content

"""安全 XML 入口在解析前检查解码后的声明，不读取外部实体文件。"""
import base64
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class XmlSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="XML安全 ' ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.entity = self.base / 'harmless.txt'
        self.entity.write_text('HARMLESS_EXTERNAL_ENTITY_CONTENT')

    def validate(self, content):
        candidate = self.base / 'candidate.xml'; candidate.write_bytes(content)
        return subprocess.run([
            '/bin/bash', '-c',
            'source "$1/scripts/lib/common.sh"; source "$1/scripts/lib/idea-project.sh"; _idea_xml_valid "$2"',
            'xml-test', str(ROOT / 'dev-kit/.support'), str(candidate),
        ], text=True, capture_output=True, timeout=10)

    def test_utf7_encoded_doctype_is_rejected_before_parsing(self):
        body = f'<!DOCTYPE project [<!ENTITY leak SYSTEM "{self.entity.as_uri()}">]><project>&leak;</project>'
        # 将整个 DTD 藏在 UTF-7 移位序列中；原始字节不含 DOCTYPE/ENTITY。
        shifted = base64.b64encode(body.encode('utf-16-be')).rstrip(b'=')
        content = b'<?xml version="1.0" encoding="UTF-7"?>+' + shifted + b'-'
        result = self.validate(content)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('HARMLESS_EXTERNAL_ENTITY_CONTENT', result.stdout + result.stderr)

    def test_ibm037_encoded_declaration_and_doctype_are_rejected_before_parsing(self):
        content = f'<?xml version="1.0" encoding="IBM037"?><!DOCTYPE project [<!ENTITY leak SYSTEM "{self.entity.as_uri()}">]><project>&leak;</project>'
        result = self.validate(content.encode('cp037'))
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('HARMLESS_EXTERNAL_ENTITY_CONTENT', result.stdout + result.stderr)

    def test_plain_supported_xml_encodings_remain_readable(self):
        cases = [
            ('UTF-8', 'utf-8'), ('US-ASCII', 'ascii'),
            ('UTF-16', 'utf-16'), ('UTF-16LE', 'utf-16-le'), ('UTF-16BE', 'utf-16-be'),
        ]
        for declaration, encoding in cases:
            with self.subTest(encoding=encoding):
                result = self.validate(f'<?xml version="1.0" encoding="{declaration}"?><project />'.encode(encoding))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for content in [b'<project />', b'\xef\xbb\xbf<project />', '<project name="中文" />'.encode('utf-8')]:
            with self.subTest(content=content):
                result = self.validate(content)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_utf16_doctype_is_still_rejected(self):
        content = f'<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE project [<!ENTITY leak SYSTEM "{self.entity.as_uri()}">]><project>&leak;</project>'
        result = self.validate(content.encode('utf-16'))
        self.assertNotEqual(result.returncode, 0)

    def test_encoding_declaration_must_match_decoded_bytes(self):
        for declaration, encoding in [('UTF-16', 'utf-8'), ('UTF-16BE', 'utf-16-le'), ('UTF-7', 'utf-16')]:
            with self.subTest(declaration=declaration, encoding=encoding):
                result = self.validate(f'<?xml version="1.0" encoding="{declaration}"?><project />'.encode(encoding))
                self.assertNotEqual(result.returncode, 0)

    def test_unsupported_encoding_is_rejected_without_invoking_xml_parser(self):
        bin_dir = self.base / 'bin'; bin_dir.mkdir()
        record = self.base / 'parser-calls'
        parser = bin_dir / 'xmllint'
        parser.write_text('#!/bin/sh\nprintf "parser\\n" >> "$XML_PARSE_RECORD"\nexit 0\n')
        parser.chmod(0o755)
        for declaration, encoding in [('UTF-7', 'utf-7'), ('IBM037', 'cp037'),
                                       ('UTF-32BE', 'utf-32-be'), ('ISO-8859-1', 'latin-1')]:
            with self.subTest(declaration=declaration):
                candidate = self.base / 'candidate.xml'
                candidate.write_bytes(f'<?xml version="1.0" encoding="{declaration}"?><project />'.encode(encoding))
                result = subprocess.run([
                    '/bin/bash', '-c',
                    'source "$1/scripts/lib/common.sh"; source "$1/scripts/lib/idea-project.sh"; _idea_xml_valid "$2"',
                    'xml-test', str(ROOT / 'dev-kit/.support'), str(candidate),
                ], env={**os.environ, 'PATH': str(bin_dir) + ':/usr/bin:/bin', 'XML_PARSE_RECORD': str(record)},
                    text=True, capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(record.exists(), 'unsupported encoding must be rejected before XML parsing')

    def test_decode_failure_cannot_parse_a_valid_partial_prefix(self):
        bin_dir = self.base / 'bin'; bin_dir.mkdir()
        record = self.base / 'parser-calls'
        parser = bin_dir / 'xmllint'
        parser.write_text('#!/bin/sh\nprintf "parser\\n" >> "$XML_PARSE_RECORD"\nexit 0\n')
        parser.chmod(0o755)
        candidate = self.base / 'candidate.xml'; candidate.write_bytes(b'<project />\xff')
        before = set(self.base.iterdir())
        result = subprocess.run([
            '/bin/bash', '-c',
            'source "$1/scripts/lib/common.sh"; source "$1/scripts/lib/idea-project.sh"; _idea_xml_valid "$2"',
            'xml-test', str(ROOT / 'dev-kit/.support'), str(candidate),
        ], env={**os.environ, 'PATH': str(bin_dir) + ':/usr/bin:/bin', 'XML_PARSE_RECORD': str(record)},
            text=True, capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(record.exists())
        self.assertEqual(before, set(self.base.iterdir()))


if __name__ == '__main__':
    unittest.main()

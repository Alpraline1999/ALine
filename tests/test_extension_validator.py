from __future__ import annotations

import unittest

from core.extension_definition import (
    ExtensionConfigField,
    ProcessingExtension,
)
from core.extension_validator import ExtensionValidator


class TestExtensionValidator(unittest.TestCase):

    def setUp(self):
        self.validator = ExtensionValidator()

    # ── validate_extension ──────────────────────────────────────────

    def test_validate_valid_extension(self):
        ext = ProcessingExtension(
            type="valid",
            name="Valid",
            handler=lambda l, p: l[0],
            version="1.0.0",
            source_kind="builtin",
        )
        errors = self.validator.validate_extension(ext)
        self.assertEqual(errors, [])

    def test_validate_missing_type(self):
        ext = ProcessingExtension(
            type="",
            name="",
            handler=None,
            source_kind="",
        )
        errors = self.validator.validate_extension(ext)
        self.assertTrue(any("type" in e for e in errors))
        self.assertTrue(any("name" in e for e in errors))
        self.assertTrue(any("handler" in e for e in errors))

    def test_validate_bad_version(self):
        ext = ProcessingExtension(
            type="v",
            name="V",
            handler=lambda l, p: l[0],
            version="bad",
            source_kind="builtin",
        )
        errors = self.validator.validate_extension(ext)
        self.assertTrue(any("版本" in e for e in errors))

    def test_validate_invalid_source_kind(self):
        ext = ProcessingExtension(
            type="sk",
            name="SK",
            handler=lambda l, p: l[0],
            source_kind="foobar",
        )
        errors = self.validator.validate_extension(ext)
        self.assertTrue(any("source_kind" in e for e in errors))

    def test_validate_config_fields_missing_key(self):
        ext = ProcessingExtension(
            type="cf",
            name="CF",
            handler=lambda l, p: l[0],
            source_kind="builtin",
            config_fields=[
                ExtensionConfigField(key="", label=""),
            ],
        )
        errors = self.validator.validate_extension(ext)
        self.assertTrue(any("key" in e for e in errors))

    def test_validate_config_fields_missing_label(self):
        ext = ProcessingExtension(
            type="cf2",
            name="CF2",
            handler=lambda l, p: l[0],
            source_kind="builtin",
            config_fields=[
                ExtensionConfigField(key="some_key", label=""),
            ],
        )
        errors = self.validator.validate_extension(ext)
        self.assertTrue(any("label" in e for e in errors))

    def test_validate_config_fields_multiple_field_indices(self):
        ext = ProcessingExtension(
            type="cf3",
            name="CF3",
            handler=lambda l, p: l[0],
            source_kind="builtin",
            config_fields=[
                ExtensionConfigField(key="ok", label="OK"),
                ExtensionConfigField(key="", label=""),
            ],
        )
        errors = self.validator.validate_extension(ext)
        self.assertTrue(any("config_fields[1]" in e for e in errors))

    def test_validate_lines_number_invalid(self):
        # Use a plain object to bypass ProcessingExtension.__post_init__ validation
        class _MockExt:
            type = "ln"
            name = "LN"
            handler = lambda l, p: l[0]  # noqa: E731
            source_kind = "builtin"
            lines_number = [5, 2]  # lower > upper
            config_fields = ()

        errors = self.validator.validate_extension(_MockExt)
        self.assertTrue(any("lines_number" in e for e in errors))

    def test_validate_lines_number_valid_none(self):
        ext = ProcessingExtension(
            type="ln2",
            name="LN2",
            handler=lambda l, p: l[0],
            source_kind="builtin",
            lines_number=None,
        )
        errors = self.validator.validate_extension(ext)
        self.assertEqual(errors, [])

    def test_validate_no_config_fields(self):
        ext = ProcessingExtension(
            type="nc",
            name="NC",
            handler=lambda l, p: l[0],
            source_kind="builtin",
        )
        errors = self.validator.validate_extension(ext)
        self.assertEqual(errors, [])

    # ── check_compatibility ─────────────────────────────────────────

    def test_check_compatibility_ok(self):
        ext = ProcessingExtension(
            type="c",
            name="C",
            handler=lambda l, p: l[0],
            source_kind="builtin",
            api_version=">=0.3",
        )
        with self.subTest("current version meets minimum"):
            warnings = self.validator.check_compatibility(ext, "0.3.0")
            self.assertEqual(warnings, [])

        with self.subTest("current version exceeds minimum"):
            warnings = self.validator.check_compatibility(ext, "0.5.0")
            self.assertEqual(warnings, [])

    def test_check_compatibility_too_new(self):
        ext = ProcessingExtension(
            type="c2",
            name="C2",
            handler=lambda l, p: l[0],
            source_kind="builtin",
            api_version=">=0.5",
        )
        warnings = self.validator.check_compatibility(ext, "0.3.0")
        self.assertTrue(any("0.5" in w for w in warnings))
        self.assertTrue(any("0.3.0" in w for w in warnings))

    def test_check_compatibility_no_declaration(self):
        ext = ProcessingExtension(
            type="c3",
            name="C3",
            handler=lambda l, p: l[0],
            source_kind="builtin",
        )
        warnings = self.validator.check_compatibility(ext, "0.3.0")
        self.assertEqual(warnings, [])

    def test_check_compatibility_blank_declaration(self):
        ext = ProcessingExtension(
            type="c4",
            name="C4",
            handler=lambda l, p: l[0],
            source_kind="builtin",
            api_version="",
        )
        warnings = self.validator.check_compatibility(ext, "0.3.0")
        self.assertEqual(warnings, [])

    def test_check_compatibility_invalid_format(self):
        ext = ProcessingExtension(
            type="c5",
            name="C5",
            handler=lambda l, p: l[0],
            source_kind="builtin",
            api_version=">=bad",
        )
        warnings = self.validator.check_compatibility(ext, "0.3.0")
        self.assertTrue(len(warnings) > 0)

    # ── validate_param_value ────────────────────────────────────────

    def test_param_valid_integer(self):
        field = ExtensionConfigField(key="count", field_type="integer", min_value=0, max_value=100)
        error = self.validator.validate_param_value("count", 5, field)
        self.assertIsNone(error)

    def test_param_integer_not_int(self):
        field = ExtensionConfigField(key="count", field_type="integer")
        error = self.validator.validate_param_value("count", "abc", field)
        self.assertIsNotNone(error)
        self.assertIn("整数", error)

    def test_param_integer_below_min(self):
        field = ExtensionConfigField(key="count", field_type="integer", min_value=10)
        error = self.validator.validate_param_value("count", 5, field)
        self.assertIsNotNone(error)
        self.assertIn("不能小于", error)

    def test_param_integer_above_max(self):
        field = ExtensionConfigField(key="count", field_type="integer", max_value=100)
        error = self.validator.validate_param_value("count", 200, field)
        self.assertIsNotNone(error)
        self.assertIn("不能大于", error)

    def test_param_valid_number(self):
        field = ExtensionConfigField(key="ratio", field_type="number", min_value=0.0, max_value=1.0)
        error = self.validator.validate_param_value("ratio", 0.5, field)
        self.assertIsNone(error)

    def test_param_number_not_numeric(self):
        field = ExtensionConfigField(key="ratio", field_type="number")
        error = self.validator.validate_param_value("ratio", "xyz", field)
        self.assertIsNotNone(error)
        self.assertIn("数值", error)

    def test_param_selective_valid(self):
        field = ExtensionConfigField(key="mode", field_type="selective", choices=("a", "b", "c"))
        error = self.validator.validate_param_value("mode", "b", field)
        self.assertIsNone(error)

    def test_param_selective_invalid(self):
        field = ExtensionConfigField(key="mode", field_type="selective", choices=("a", "b", "c"))
        error = self.validator.validate_param_value("mode", "z", field)
        self.assertIsNotNone(error)
        self.assertIn("不在可选范围", error)

    def test_param_selective_no_choices(self):
        field = ExtensionConfigField(key="mode", field_type="selective", choices=())
        error = self.validator.validate_param_value("mode", "z", field)
        self.assertIsNone(error)  # empty choices = no restriction

    def test_param_boolean_valid(self):
        field = ExtensionConfigField(key="flag", field_type="boolean")
        error = self.validator.validate_param_value("flag", True, field)
        self.assertIsNone(error)

    def test_param_boolean_invalid(self):
        field = ExtensionConfigField(key="flag", field_type="boolean")
        error = self.validator.validate_param_value("flag", "yes", field)
        self.assertIsNotNone(error)
        self.assertIn("布尔值", error)

    def test_param_default_string_type(self):
        field = ExtensionConfigField(key="name")
        error = self.validator.validate_param_value("name", "anything", field)
        self.assertIsNone(error)


class TestVersionCompatibility(unittest.TestCase):
    """测试 ExtensionValidator.check_api_compatibility 版本兼容性检查。"""

    def test_compatible_exact(self):
        self.assertEqual(
            ExtensionValidator.check_api_compatibility("0.3", "0.3.0"),
            "compatible",
        )

    def test_compatible_minimum(self):
        self.assertEqual(
            ExtensionValidator.check_api_compatibility(">=0.3", "0.3.0"),
            "compatible",
        )
        self.assertEqual(
            ExtensionValidator.check_api_compatibility(">=0.2", "0.3.0"),
            "compatible",
        )

    def test_incompatible_too_new(self):
        self.assertEqual(
            ExtensionValidator.check_api_compatibility(">=0.5", "0.3.0"),
            "incompatible",
        )

    def test_incompatible_wrong_exact(self):
        self.assertEqual(
            ExtensionValidator.check_api_compatibility("0.4", "0.3.0"),
            "incompatible",
        )

    def test_no_declaration(self):
        self.assertEqual(
            ExtensionValidator.check_api_compatibility("", "0.3.0"),
            "compatible",
        )

    def test_range(self):
        self.assertEqual(
            ExtensionValidator.check_api_compatibility(">=0.3,<0.5", "0.3.0"),
            "compatible",
        )
        self.assertEqual(
            ExtensionValidator.check_api_compatibility(">=0.3,<0.5", "0.5.0"),
            "incompatible",
        )

    def test_range_with_space(self):
        self.assertEqual(
            ExtensionValidator.check_api_compatibility(">=0.3, <0.5", "0.3.0"),
            "compatible",
        )

    def test_invalid_format_returns_warning(self):
        self.assertEqual(
            ExtensionValidator.check_api_compatibility(">=bad", "0.3.0"),
            "warning",
        )

    def test_range_below_minimum(self):
        self.assertEqual(
            ExtensionValidator.check_api_compatibility(">=0.3,<0.5", "0.2.0"),
            "incompatible",
        )


if __name__ == "__main__":
    unittest.main()

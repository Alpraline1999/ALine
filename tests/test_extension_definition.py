from __future__ import annotations

import unittest

from core.extension_definition import (
    AnalysisExtension,
    CurveStyleExtension,
    DigitizeExtension,
    ExtensionConfigField,
    PlotExtension,
    PlotStyleExtension,
    ProcessingExtension,
    _EXTENSION_CATEGORY_LABELS,
    _EXTENSION_ORIGIN_LABELS,
    _EXTENSION_SOURCE_HINTS,
    _EXTENSION_SOURCE_KINDS,
    _EXTENSION_SOURCE_LABELS,
    _EXTENSION_TOOL_TIER_LABELS,
    _NON_EXTENSION_MODULE_FILENAMES,
    compare_extension_versions,
    extension_lines_number,
    extension_lines_picker_visible,
    extension_lines_support_text,
    normalize_extension_field_type,
    normalize_extension_lines_config,
    normalize_extension_lines_list,
    normalize_extension_lines_number,
    normalize_extension_source_kind,
    normalize_extension_tool_tier,
    normalize_extension_version,
    normalize_plot_extension_phases,
    parse_extension_version,
    validate_extension_lines_list,
)


def _noop_handler(*args, **kwargs):
    return None


class TestExtensionDefinition(unittest.TestCase):

    def test_normalize_field_type_bool(self):
        self.assertEqual(normalize_extension_field_type("bool"), "boolean")
        self.assertEqual(normalize_extension_field_type("boolean"), "boolean")
        self.assertEqual(normalize_extension_field_type("checkbox"), "boolean")

    def test_normalize_field_type_int(self):
        self.assertEqual(normalize_extension_field_type("int"), "integer")
        self.assertEqual(normalize_extension_field_type("integer"), "integer")
        self.assertEqual(normalize_extension_field_type("spinbox"), "integer")

    def test_normalize_field_type_float(self):
        self.assertEqual(normalize_extension_field_type("float"), "number")
        self.assertEqual(normalize_extension_field_type("double"), "number")
        self.assertEqual(normalize_extension_field_type("number"), "number")

    def test_normalize_field_type_string_default(self):
        self.assertEqual(normalize_extension_field_type(None), "string")
        self.assertEqual(normalize_extension_field_type(""), "string")
        self.assertEqual(normalize_extension_field_type("unknown"), "string")

    def test_normalize_field_type_color_variants(self):
        self.assertEqual(normalize_extension_field_type("color"), "color")
        self.assertEqual(normalize_extension_field_type("colour"), "color")
        self.assertEqual(normalize_extension_field_type("colorpicker"), "color")

    def test_normalize_field_type_choices_force_selective(self):
        self.assertEqual(
            normalize_extension_field_type("string", choices=["a", "b"]),
            "selective",
        )

    def test_normalize_field_type_key_hint_for_color(self):
        self.assertEqual(
            normalize_extension_field_type("string", key="stroke_color"),
            "color",
        )

    def test_normalize_field_type_lines(self):
        self.assertEqual(normalize_extension_field_type("lines"), "lines")
        self.assertEqual(normalize_extension_field_type("line"), "line")

    def test_normalize_field_type_selective(self):
        self.assertEqual(normalize_extension_field_type("choice"), "selective")
        self.assertEqual(normalize_extension_field_type("select"), "selective")
        self.assertEqual(normalize_extension_field_type("enum"), "selective")
        self.assertEqual(normalize_extension_field_type("combobox"), "selective")


    def test_normalize_version_valid(self):
        self.assertEqual(normalize_extension_version("1.0.0"), "1.0.0")
        self.assertEqual(normalize_extension_version("2.3.4"), "2.3.4")
        self.assertEqual(normalize_extension_version("0.0.1"), "0.0.1")

    def test_normalize_version_invalid(self):
        with self.assertRaises(ValueError):
            normalize_extension_version("1.0")
        with self.assertRaises(ValueError):
            normalize_extension_version("v1.0.0")
        with self.assertRaises(ValueError):
            normalize_extension_version("1.0.0.0")
        with self.assertRaises(ValueError):
            normalize_extension_version("abc")

    def test_normalize_version_default(self):
        self.assertEqual(normalize_extension_version(None), "1.0.0")
        self.assertEqual(normalize_extension_version(""), "1.0.0")

    def test_parse_extension_version(self):
        self.assertEqual(parse_extension_version("2.3.4"), (2, 3, 4))
        self.assertEqual(parse_extension_version(None), (1, 0, 0))

    def test_compare_extension_versions(self):
        self.assertEqual(compare_extension_versions("1.0.0", "1.0.0"), 0)
        self.assertLess(compare_extension_versions("1.0.0", "2.0.0"), 0)
        self.assertGreater(compare_extension_versions("2.0.0", "1.0.0"), 0)
        self.assertLess(compare_extension_versions("1.0.0", "1.1.0"), 0)


    def test_normalize_source_kind_valid(self):
        self.assertEqual(normalize_extension_source_kind("builtin"), "builtin")
        self.assertEqual(normalize_extension_source_kind("base"), "base")
        self.assertEqual(normalize_extension_source_kind("external"), "external")

    def test_normalize_source_kind_invalid_defaults_external(self):
        self.assertEqual(normalize_extension_source_kind("nonsense"), "external")
        self.assertEqual(normalize_extension_source_kind(None), "builtin")


    def test_normalize_tool_tier_valid(self):
        self.assertEqual(normalize_extension_tool_tier("tool"), "tool")
        self.assertEqual(normalize_extension_tool_tier("experimental"), "experimental")

    def test_normalize_tool_tier_invalid(self):
        with self.assertRaises(ValueError):
            normalize_extension_tool_tier("premium")


    def test_normalize_lines_number_none(self):
        self.assertIsNone(normalize_extension_lines_number(None))

    def test_normalize_lines_number_empty_string(self):
        self.assertEqual(normalize_extension_lines_number(""), (1, 1))

    def test_normalize_lines_number_empty_list(self):
        self.assertEqual(normalize_extension_lines_number([]), (1, 1))

    def test_normalize_lines_number_valid_range(self):
        self.assertEqual(normalize_extension_lines_number((1, 1)), (1, 1))
        self.assertEqual(normalize_extension_lines_number([2, -1]), (2, -1))
        self.assertEqual(normalize_extension_lines_number((0, 5)), (0, 5))

    def test_normalize_lines_number_invalid_lower_negative(self):
        with self.assertRaises(ValueError):
            normalize_extension_lines_number((-1, 5))

    def test_normalize_lines_number_invalid_upper_negative2(self):
        with self.assertRaises(ValueError):
            normalize_extension_lines_number((1, -2))

    def test_normalize_lines_number_lower_gt_upper(self):
        with self.assertRaises(ValueError):
            normalize_extension_lines_number((5, 3))

    def test_normalize_lines_number_not_sequence(self):
        with self.assertRaises(ValueError):
            normalize_extension_lines_number(42)


    def test_extension_lines_number_from_instance(self):
        ext = ProcessingExtension(type="t", name="n", handler=_noop_handler, lines_number=(2, 4))
        self.assertEqual(extension_lines_number(ext), (2, 4))

    def test_extension_lines_support_text(self):
        self.assertEqual(extension_lines_support_text(None), "")
        self.assertEqual(extension_lines_support_text((3, 3)), "3 条")
        self.assertEqual(extension_lines_support_text((2, -1)), "2 条及以上")
        self.assertEqual(extension_lines_support_text((0, 5)), "0 到 5 条")
        self.assertEqual(extension_lines_support_text((1, 3)), "1 到 3 条")

    def test_extension_lines_picker_visible(self):
        self.assertFalse(extension_lines_picker_visible(None))
        self.assertFalse(extension_lines_picker_visible((1, 1)))
        self.assertTrue(extension_lines_picker_visible((2, -1)))
        self.assertTrue(extension_lines_picker_visible((1, 3)))

    # normalize_extension_lines_list / validate_extension_lines_list

    def test_normalize_lines_list_none(self):
        self.assertEqual(normalize_extension_lines_list(None), [])

    def test_normalize_lines_list_string(self):
        self.assertEqual(normalize_extension_lines_list("1,2,3"), [1, 2, 3])
        self.assertEqual(normalize_extension_lines_list("1;2;3"), [1, 2, 3])

    def test_normalize_lines_list_list(self):
        self.assertEqual(normalize_extension_lines_list([1, 2, 3]), [1, 2, 3])

    def test_normalize_lines_list_dedup(self):
        self.assertEqual(normalize_extension_lines_list([1, 2, 2, 3]), [1, 2, 3])

    def test_normalize_lines_list_rejects_zero(self):
        with self.assertRaises(ValueError):
            normalize_extension_lines_list([0])

    def test_normalize_lines_list_rejects_negative(self):
        with self.assertRaises(ValueError):
            normalize_extension_lines_list([-1])

    def test_normalize_lines_list_rejects_non_int(self):
        with self.assertRaises(ValueError):
            normalize_extension_lines_list("abc")

    def test_validate_lines_list_no_lines_number(self):
        result = validate_extension_lines_list([1, 2], None, present=False)
        self.assertEqual(result, [1, 2])

    def test_validate_lines_list_present_but_no_number(self):
        with self.assertRaises(ValueError):
            validate_extension_lines_list([1], None, present=True)

    def test_validate_lines_list_below_min(self):
        with self.assertRaises(ValueError):
            validate_extension_lines_list([1], (2, 5), present=True)

    def test_validate_lines_list_above_max(self):
        with self.assertRaises(ValueError):
            validate_extension_lines_list([1, 2, 3], (1, 2), present=True)

    def test_validate_lines_list_unlimited_upper(self):
        result = validate_extension_lines_list([1, 2, 3, 4], (2, -1), present=True)
        self.assertEqual(result, [1, 2, 3, 4])

    def test_validate_lines_list_not_present_skips_validation(self):
        result = validate_extension_lines_list([1], (3, 5), present=False)
        self.assertEqual(result, [1])


    def test_normalize_lines_config_empty(self):
        result = normalize_extension_lines_config(None)
        self.assertEqual(result, {"number": 0, "lines_list": []})

    def test_normalize_lines_config_with_number(self):
        result = normalize_extension_lines_config({"number": (2, 4)})
        self.assertEqual(result, {"number": 2, "lines_list": []})

    def test_normalize_lines_config_with_lines_number_key(self):
        result = normalize_extension_lines_config({"lines_number": (3, 3)})
        self.assertEqual(result, {"number": 3, "lines_list": []})

    def test_normalize_lines_config_with_unlimited(self):
        result = normalize_extension_lines_config({"number": (2, -1)})
        self.assertEqual(result, {"number": -1, "lines_list": []})


    def test_normalize_plot_phases_default(self):
        self.assertEqual(
            normalize_plot_extension_phases(None),
            ("before_plot", "after_plot"),
        )

    def test_normalize_plot_phases_single(self):
        self.assertEqual(
            normalize_plot_extension_phases("before_plot"),
            ("before_plot",),
        )

    def test_normalize_plot_phases_invalid(self):
        with self.assertRaises(ValueError):
            normalize_plot_extension_phases("during_plot")


    def test_processing_extension_creation(self):
        ext = ProcessingExtension(
            type="my.process",
            name="My Process",
            handler=_noop_handler,
            description="A test",
        )
        self.assertEqual(ext.id, "my.process")
        self.assertEqual(ext.function_category, "processing")
        self.assertTrue(ext.listed)
        self.assertTrue(ext.closable)

    def test_processing_extension_hidden(self):
        ext = ProcessingExtension(
            type="h", name="Hidden", handler=_noop_handler, hidden=True
        )
        self.assertFalse(ext.listed)

    def test_processing_extension_lines_number_post_init(self):
        ext = ProcessingExtension(
            type="ln", name="LN", handler=_noop_handler, lines_number=(2, -1)
        )
        self.assertEqual(extension_lines_number(ext), (2, -1))

    def test_analysis_extension_creation(self):
        ext = AnalysisExtension(
            type="my.analyze",
            name="Analyze",
            handler=_noop_handler,
        )
        self.assertEqual(ext.function_category, "analysis")

    def test_plot_extension_creation(self):
        ext = PlotExtension(
            type="my.plot",
            name="Plot",
            handler=_noop_handler,
        )
        self.assertEqual(ext.function_category, "plot")
        self.assertEqual(ext.phases, ("before_plot", "after_plot"))

    def test_plot_extension_phases_post_init(self):
        ext = PlotExtension(
            type="p", name="P", handler=_noop_handler, phases=("after_plot",)
        )
        self.assertEqual(ext.phases, ("after_plot",))

    def test_digitize_extension_creation(self):
        ext = DigitizeExtension(
            type="my.digitize",
            name="Digitize",
            handler=_noop_handler,
        )
        self.assertEqual(ext.function_category, "digitize")

    def test_curve_style_extension_creation(self):
        ext = CurveStyleExtension(
            type="cs",
            name="CS",
            handler=lambda style, params: style,
        )
        self.assertEqual(ext.type, "cs")

    def test_plot_style_extension_creation(self):
        ext = PlotStyleExtension(
            type="ps",
            name="PS",
            handler=lambda style, params: style,
        )
        self.assertEqual(ext.type, "ps")

    def test_extension_config_field_to_dict(self):
        field = ExtensionConfigField(
            key="alpha",
            label="Alpha",
            description="Opacity",
            field_type="float",
            default=1.0,
            choices=(0.0, 0.5, 1.0),
            min_value=0.0,
            max_value=1.0,
            step=0.1,
            placeholder="0.5",
            extra={"unit": "opacity"},
        )
        d = field.to_dict()
        self.assertEqual(d["key"], "alpha")
        self.assertEqual(d["field_type"], "float")
        self.assertEqual(d["default"], 1.0)
        self.assertEqual(d["choices"], [0.0, 0.5, 1.0])
        self.assertEqual(d["extra"]["unit"], "opacity")


    def test_category_labels(self):
        self.assertIn("processing", _EXTENSION_CATEGORY_LABELS)
        self.assertIn("analysis", _EXTENSION_CATEGORY_LABELS)
        self.assertIn("plot", _EXTENSION_CATEGORY_LABELS)
        self.assertIn("digitize", _EXTENSION_CATEGORY_LABELS)

    def test_source_labels(self):
        for kind in ("base", "builtin", "external"):
            self.assertIn(kind, _EXTENSION_SOURCE_LABELS)
            self.assertIn(kind, _EXTENSION_ORIGIN_LABELS)

    def test_tool_tier_labels(self):
        self.assertIn("tool", _EXTENSION_TOOL_TIER_LABELS)
        self.assertIn("experimental", _EXTENSION_TOOL_TIER_LABELS)

    def test_source_kinds_frozenset(self):
        self.assertIn("builtin", _EXTENSION_SOURCE_KINDS)

    def test_non_extension_module_filenames(self):
        self.assertIn("extension_tools.py", _NON_EXTENSION_MODULE_FILENAMES)

    def test_source_hints(self):
        for category in ("processing", "analysis", "plot", "digitize"):
            self.assertIn(category, _EXTENSION_SOURCE_HINTS)


class TestExtensionDefinitionReexport(unittest.TestCase):
    """Verify re-export via extension_api still works."""

    def test_dataclasses_via_extension_api(self):
        from core.extension_api import (
            AnalysisExtension,
            CurveStyleExtension,
            DigitizeExtension,
            ExtensionConfigField,
            PlotExtension,
            PlotStyleExtension,
            ProcessingExtension,
        )
        self.assertIsNotNone(ProcessingExtension)
        self.assertIsNotNone(AnalysisExtension)
        self.assertIsNotNone(PlotExtension)
        self.assertIsNotNone(DigitizeExtension)
        self.assertIsNotNone(PlotStyleExtension)
        self.assertIsNotNone(CurveStyleExtension)
        self.assertIsNotNone(ExtensionConfigField)

    def test_normalize_functions_via_extension_api(self):
        from core.extension_api import (
            normalize_extension_field_type,
            normalize_extension_lines_list,
            normalize_extension_lines_number,
            normalize_extension_source_kind,
            normalize_extension_version,
        )
        self.assertTrue(callable(normalize_extension_version))
        self.assertTrue(callable(normalize_extension_field_type))
        self.assertTrue(callable(normalize_extension_lines_number))
        self.assertTrue(callable(normalize_extension_lines_list))
        self.assertTrue(callable(normalize_extension_source_kind))

    def test_label_dicts_via_extension_api(self):
        from core.extension_api import (
            _EXTENSION_CATEGORY_LABELS,
            _EXTENSION_SOURCE_LABELS,
        )
        self.assertIsInstance(_EXTENSION_CATEGORY_LABELS, dict)
        self.assertIsInstance(_EXTENSION_SOURCE_LABELS, dict)


if __name__ == "__main__":
    unittest.main()

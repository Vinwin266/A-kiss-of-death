"""Utility profiles: presets, overrides and descriptions."""

from __future__ import annotations

import unittest
from decimal import Decimal

from meterline.core.rounding import RoundingMode
from meterline.errors import PolicyError
from meterline.policy.conventions import (
    CreditValuation,
    NettingGranularity,
    ProrationBasis,
    TierBasis,
    TrueUpPolicy,
)
from meterline.policy.describe import (
    explain_convention,
    profile_highlights,
    profile_table,
)
from meterline.policy.presets import PRESETS, preset, preset_names
from meterline.policy.profile import UtilityProfile
from meterline.policy.resolve import ENUM_FIELDS, profile_from_dict, profile_overrides


class PresetTests(unittest.TestCase):
    def test_every_preset_is_named_after_itself(self) -> None:
        for name, profile in PRESETS.items():
            self.assertEqual(name, profile.name)

    def test_every_preset_has_a_description(self) -> None:
        for profile in PRESETS.values():
            self.assertTrue(profile.description)

    def test_presets_differ_from_each_other(self) -> None:
        rendered = {name: str(profile.as_dict()) for name, profile in PRESETS.items()}
        self.assertEqual(len(set(rendered.values())), len(PRESETS))

    def test_unknown_presets_list_the_known_ones(self) -> None:
        with self.assertRaises(PolicyError) as caught:
            preset("nonesuch")
        self.assertIn("model-rules", caught.exception.context["known"])

    def test_names_are_sorted(self) -> None:
        self.assertEqual(preset_names(), sorted(preset_names()))

    def test_the_cooperative_prorates_nothing(self) -> None:
        self.assertIs(
            preset("legacy-cooperative").proration, ProrationBasis.FULL_IF_ANY_DAY
        )

    def test_the_municipal_profile_refuses_to_guess(self) -> None:
        profile = preset("strict-municipal")
        self.assertIs(profile.true_up, TrueUpPolicy.CANCEL_REBILL)
        self.assertEqual(profile.gaps.value, "fail")


class ProfileTests(unittest.TestCase):
    def test_derived_ratios(self) -> None:
        profile = UtilityProfile(ratchet_percent="75", credit_percent_of_retail="80")
        self.assertEqual(profile.ratchet_fraction, Decimal("0.75"))
        self.assertEqual(profile.credit_fraction, Decimal("0.8"))

    def test_with_changes_returns_a_copy(self) -> None:
        original = UtilityProfile()
        changed = original.with_changes(tier_basis=TierBasis.DAILY)
        self.assertIs(original.tier_basis, TierBasis.CYCLE)
        self.assertIs(changed.tier_basis, TierBasis.DAILY)

    def test_unknown_fields_are_refused(self) -> None:
        with self.assertRaises(PolicyError):
            UtilityProfile().with_changes(nonsense=True)

    def test_an_impossible_true_up_month_is_refused(self) -> None:
        with self.assertRaises(PolicyError):
            UtilityProfile(true_up_month=13)

    def test_sub_cycle_netting_at_retail_is_refused(self) -> None:
        with self.assertRaises(PolicyError):
            UtilityProfile(
                netting=NettingGranularity.DAILY,
                credit_valuation=CreditValuation.RETAIL,
            )

    def test_sub_cycle_netting_is_allowed_at_avoided_cost(self) -> None:
        profile = UtilityProfile(
            netting=NettingGranularity.DAILY,
            credit_valuation=CreditValuation.AVOIDED_COST,
        )
        self.assertIs(profile.netting, NettingGranularity.DAILY)

    def test_the_dict_view_is_json_friendly(self) -> None:
        rendered = UtilityProfile().as_dict()
        self.assertIsInstance(rendered["rounding_mode"], str)
        self.assertIsInstance(rendered["day_types"], dict)

    def test_describe_covers_every_setting(self) -> None:
        described = UtilityProfile().describe()
        for field in UtilityProfile().field_names():
            if field in ("name", "description"):
                continue
            self.assertIn(field, described)


class ResolutionTests(unittest.TestCase):
    def test_a_base_preset_can_be_extended(self) -> None:
        profile = profile_from_dict({"base": "model-rules", "tier_basis": "daily"})
        self.assertIs(profile.tier_basis, TierBasis.DAILY)
        self.assertEqual(profile.name, "model-rules")

    def test_an_unknown_convention_value_lists_the_options(self) -> None:
        with self.assertRaises(PolicyError) as caught:
            profile_from_dict({"tier_basis": "hourly"})
        self.assertIn("cycle", caught.exception.context["options"])

    def test_unknown_fields_are_refused(self) -> None:
        with self.assertRaises(PolicyError):
            profile_overrides({"nonsense": 1})

    def test_day_types_decode_from_a_mapping(self) -> None:
        profile = profile_from_dict({"day_types": {"saturday_is_weekend": False}})
        self.assertFalse(profile.day_types.saturday_is_weekend)

    def test_unknown_day_type_settings_are_refused(self) -> None:
        with self.assertRaises(PolicyError):
            profile_from_dict({"day_types": {"tuesday_is_weekend": True}})

    def test_integers_are_coerced(self) -> None:
        profile = profile_from_dict({"money_places": 3})
        self.assertEqual(profile.money_places, 3)

    def test_every_enum_field_is_declared(self) -> None:
        for field in ENUM_FIELDS:
            self.assertIn(field, UtilityProfile().field_names())

    def test_a_rounding_mode_decodes(self) -> None:
        profile = profile_from_dict({"rounding_mode": "half_even"})
        self.assertIs(profile.rounding_mode, RoundingMode.HALF_EVEN)


class DescriptionTests(unittest.TestCase):
    def test_conventions_with_the_same_value_do_not_collide(self) -> None:
        self.assertNotEqual(
            explain_convention(ProrationBasis.NONE),
            explain_convention(TrueUpPolicy.NONE),
        )

    def test_an_undocumented_value_explains_nothing(self) -> None:
        self.assertEqual(explain_convention("something else"), "")

    def test_highlights_mention_the_big_movers(self) -> None:
        highlights = profile_highlights(preset("legacy-cooperative"))
        self.assertTrue(any("full month" in line for line in highlights))

    def test_the_table_has_a_row_for_every_setting(self) -> None:
        table = profile_table(UtilityProfile())
        expected = len(UtilityProfile().field_names()) - 2
        self.assertEqual(len(table.rows), expected)


if __name__ == "__main__":
    unittest.main()

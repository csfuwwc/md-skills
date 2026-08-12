import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import sync_writeback  # noqa: E402


parse_inventory_policy_args = getattr(
    sync_writeback, "parse_inventory_policy_args", None
)
missing_inventory_policy_ids = getattr(
    sync_writeback, "missing_inventory_policy_ids", None
)
variant_policy_updates = getattr(sync_writeback, "variant_policy_updates", None)


class InventoryPolicyFeatureAvailabilityTests(unittest.TestCase):
    def test_inventory_policy_confirmation_helpers_exist(self):
        self.assertTrue(
            all(
                callable(fn)
                for fn in (
                    parse_inventory_policy_args,
                    missing_inventory_policy_ids,
                    variant_policy_updates,
                )
            ),
            "inventory policy confirmation helpers are missing",
        )


@unittest.skipUnless(
    all(
        callable(fn)
        for fn in (
            parse_inventory_policy_args,
            missing_inventory_policy_ids,
            variant_policy_updates,
        )
    ),
    "inventory policy confirmation feature is not implemented yet",
)
class InventoryPolicyConfirmationTests(unittest.TestCase):
    def test_missing_choices_are_reported_without_a_default(self):
        choices = parse_inventory_policy_args([])

        self.assertEqual(choices, {})
        self.assertEqual(
            missing_inventory_policy_ids(
                ["gid://shopify/Product/1", "gid://shopify/Product/2"],
                choices,
            ),
            ["gid://shopify/Product/1", "gid://shopify/Product/2"],
        )

    def test_each_product_requires_an_explicit_continue_or_deny_choice(self):
        choices = parse_inventory_policy_args(
            [
                "gid://shopify/Product/1=CONTINUE",
                "gid://shopify/Product/2=deny",
            ]
        )

        self.assertEqual(
            choices,
            {
                "gid://shopify/Product/1": "CONTINUE",
                "gid://shopify/Product/2": "DENY",
            },
        )
        self.assertEqual(
            missing_inventory_policy_ids(
                ["gid://shopify/Product/1", "gid://shopify/Product/2"],
                choices,
            ),
            [],
        )

    def test_invalid_or_conflicting_choices_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "CONTINUE 或 DENY"):
            parse_inventory_policy_args(["gid://shopify/Product/1=AUTO"])

        with self.assertRaisesRegex(ValueError, "重复且冲突"):
            parse_inventory_policy_args(
                [
                    "gid://shopify/Product/1=CONTINUE",
                    "gid://shopify/Product/1=DENY",
                ]
            )

    def test_only_variants_that_differ_from_the_confirmed_choice_are_updated(self):
        variants = [
            {
                "id": "gid://shopify/ProductVariant/1",
                "title": "A",
                "inventoryPolicy": "DENY",
            },
            {
                "id": "gid://shopify/ProductVariant/2",
                "title": "B",
                "inventoryPolicy": "CONTINUE",
            },
        ]

        self.assertEqual(
            variant_policy_updates(variants, "CONTINUE"),
            [
                {
                    "id": "gid://shopify/ProductVariant/1",
                    "inventoryPolicy": "CONTINUE",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()

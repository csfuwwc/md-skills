import sys
import unittest
from copy import deepcopy
from decimal import Decimal
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

try:
    import regional_pricing
except ModuleNotFoundError:
    regional_pricing = None


REQUIRED_HELPERS = (
    "normalize_tier",
    "parse_money",
    "pricing_rows_for_tier",
    "parse_multiplier_overrides",
    "variant_multiplier",
    "validate_product_role",
    "base_price_updates",
    "expected_prices",
    "catalog_price_lists",
    "pricing_actions",
    "price_mismatches",
    "execute_pricing",
)


class RegionalPricingFeatureAvailabilityTests(unittest.TestCase):
    def test_regional_pricing_module_and_helpers_exist(self):
        self.assertIsNotNone(regional_pricing, "regional_pricing.py is missing")
        self.assertTrue(
            all(callable(getattr(regional_pricing, name, None)) for name in REQUIRED_HELPERS),
            "regional pricing helpers are missing",
        )


@unittest.skipUnless(
    regional_pricing is not None
    and all(callable(getattr(regional_pricing, name, None)) for name in REQUIRED_HELPERS),
    "regional pricing feature is not implemented yet",
)
class RegionalPricingTests(unittest.TestCase):
    def test_shopify_cli_accepts_both_raw_data_and_http_envelopes(self):
        self.assertEqual(
            regional_pricing._shopify_data({"product": {"id": "p1"}}),
            {"product": {"id": "p1"}},
        )
        self.assertEqual(
            regional_pricing._shopify_data({"data": {"product": {"id": "p1"}}}),
            {"product": {"id": "p1"}},
        )
        with self.assertRaisesRegex(RuntimeError, "GraphQL errors"):
            regional_pricing._shopify_data({"errors": [{"message": "denied"}]})

    def test_tier_is_explicit_and_restricted_to_p01_through_p07(self):
        self.assertEqual(regional_pricing.normalize_tier("p02"), "P02")
        for invalid in ("", "19.99", "P00", "P08", "P04/P05"):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "P01-P07"):
                    regional_pricing.normalize_tier(invalid)

    def test_pricing_table_values_are_parsed_from_the_selected_tier(self):
        payload = {
            "ok": True,
            "data": {
                "fields": ["市场键", "币种", "P02｜¥69档"],
                "data": [
                    ["US-USD", "USD", "$19.99"],
                    ["GB-GBP", "GBP", "£22.99"],
                    ["VN-VND", "VND", "329,000₫"],
                ],
                "has_more": False,
            },
        }

        rows = regional_pricing.pricing_rows_for_tier(
            payload,
            tier_field="P02｜¥69档",
        )

        self.assertEqual(
            rows,
            {
                "US-USD": {"currency": "USD", "unit_price": Decimal("19.99")},
                "GB-GBP": {"currency": "GBP", "unit_price": Decimal("22.99")},
                "VN-VND": {"currency": "VND", "unit_price": Decimal("329000")},
            },
        )
        self.assertEqual(regional_pricing.parse_money("Rp1,752,000"), Decimal("1752000"))

    def test_pricing_field_schema_must_be_complete_before_record_read(self):
        payload = {
            "ok": True,
            "data": {
                "fields": [
                    {"name": "市场键", "type": "text"},
                    {"name": "币种", "type": "text"},
                    {"name": "P02｜¥69档", "type": "text"},
                ],
                "total": 3,
            },
        }
        regional_pricing.validate_pricing_fields(payload, "P02｜¥69档")
        payload["data"]["total"] = 4
        with self.assertRaisesRegex(ValueError, "字段结构读取不完整"):
            regional_pricing.validate_pricing_fields(payload, "P02｜¥69档")

    def test_partial_or_duplicate_pricing_table_is_rejected(self):
        partial = {
            "ok": True,
            "data": {
                "fields": ["市场键", "币种", "P02｜¥69档"],
                "data": [["US-USD", "USD", "$19.99"]],
                "has_more": True,
            },
        }
        with self.assertRaisesRegex(ValueError, "未完整读取"):
            regional_pricing.pricing_rows_for_tier(partial, "P02｜¥69档")

        duplicate = {
            "ok": True,
            "data": {
                "fields": ["市场键", "币种", "P02｜¥69档"],
                "data": [
                    ["US-USD", "USD", "$19.99"],
                    ["US-USD", "USD", "$19.99"],
                ],
                "has_more": False,
            },
        }
        with self.assertRaisesRegex(ValueError, "重复市场键"):
            regional_pricing.pricing_rows_for_tier(duplicate, "P02｜¥69档")

    def test_variant_multiplier_uses_explicit_override_sku_or_box_count(self):
        overrides = regional_pricing.parse_multiplier_overrides(
            ["gid://shopify/ProductVariant/4=6"]
        )
        self.assertEqual(
            regional_pricing.variant_multiplier(
                {"id": "gid://shopify/ProductVariant/1", "title": "1 Pc", "sku": "ABC"},
                overrides,
            ),
            1,
        )
        self.assertEqual(
            regional_pricing.variant_multiplier(
                {"id": "gid://shopify/ProductVariant/2", "title": "1 Set", "sku": "ABC*8"},
                overrides,
            ),
            8,
        )
        self.assertEqual(
            regional_pricing.variant_multiplier(
                {
                    "id": "gid://shopify/ProductVariant/3",
                    "title": "Full Set (8 Boxes)",
                    "sku": "SET",
                },
                overrides,
            ),
            8,
        )
        self.assertEqual(
            regional_pricing.variant_multiplier(
                {"id": "gid://shopify/ProductVariant/4", "title": "1 Set", "sku": "SET"},
                overrides,
            ),
            6,
        )
        with self.assertRaisesRegex(ValueError, "无法确定"):
            regional_pricing.variant_multiplier(
                {"id": "gid://shopify/ProductVariant/5", "title": "1 Set", "sku": "SET"},
                overrides,
            )

    def test_target_must_be_draft_and_reference_must_be_active(self):
        regional_pricing.validate_product_role(
            {"id": "gid://shopify/Product/1", "status": "DRAFT"},
            "target",
        )
        regional_pricing.validate_product_role(
            {"id": "gid://shopify/Product/2", "status": "ACTIVE"},
            "reference",
        )
        with self.assertRaisesRegex(ValueError, "必须保持 DRAFT"):
            regional_pricing.validate_product_role(
                {"id": "gid://shopify/Product/1", "status": "ACTIVE"},
                "target",
            )
        with self.assertRaisesRegex(ValueError, "必须是 ACTIVE"):
            regional_pricing.validate_product_role(
                {"id": "gid://shopify/Product/2", "status": "DRAFT"},
                "reference",
            )

    def test_expected_prices_multiply_each_market_unit_price_by_pack_size(self):
        rows = {
            "US-USD": {"currency": "USD", "unit_price": Decimal("19.99")},
            "GB-GBP": {"currency": "GBP", "unit_price": Decimal("22.99")},
        }
        variants = [
            {"id": "v1", "title": "1 Pc"},
            {"id": "v2", "title": "1 Set"},
        ]

        plan = regional_pricing.expected_prices(rows, variants, {"v1": 1, "v2": 8})

        self.assertEqual(plan["US-USD"]["v1"], Decimal("19.99"))
        self.assertEqual(plan["US-USD"]["v2"], Decimal("159.92"))
        self.assertEqual(plan["GB-GBP"]["v2"], Decimal("183.92"))

    def test_base_price_plan_updates_only_differences_and_never_touches_status(self):
        product = {
            "id": "gid://shopify/Product/1",
            "status": "DRAFT",
            "variants": {
                "nodes": [
                    {"id": "v1", "price": "19.99", "compareAtPrice": None},
                    {"id": "v2", "price": "150", "compareAtPrice": None},
                ]
            },
        }

        updates = regional_pricing.base_price_updates(
            product,
            unit_price=Decimal("19.99"),
            multipliers={"v1": 1, "v2": 8},
        )

        self.assertEqual(updates, [{"id": "v2", "price": "159.92"}])
        self.assertNotIn("status", updates[0])

        product["variants"]["nodes"][0]["compareAtPrice"] = "29.99"
        with self.assertRaisesRegex(ValueError, "Compare-at"):
            regional_pricing.base_price_updates(
                product,
                unit_price=Decimal("19.99"),
                multipliers={"v1": 1, "v2": 8},
            )

    def test_catalog_mapping_uses_stable_ids_and_deduplicates_shared_catalogs(self):
        market_nodes = [
            {
                "name": "美国",
                "status": "ACTIVE",
                "catalogs": {
                    "nodes": [
                        {
                            "id": "catalog-us",
                            "title": "美国",
                            "status": "ACTIVE",
                            "priceList": {"id": "pl-us", "currency": "USD"},
                        },
                        {
                            "id": "catalog-global",
                            "title": "global",
                            "status": "ACTIVE",
                            "priceList": {"id": "pl-global", "currency": "USD"},
                        },
                    ]
                },
            },
            {
                "name": "加拿大",
                "status": "ACTIVE",
                "catalogs": {
                    "nodes": [
                        {
                            "id": "catalog-us",
                            "title": "美国",
                            "status": "ACTIVE",
                            "priceList": {"id": "pl-us", "currency": "USD"},
                        }
                    ]
                },
            },
            {
                "name": "英国",
                "status": "ACTIVE",
                "catalogs": {
                    "nodes": [
                        {
                            "id": "catalog-uk",
                            "title": "英国",
                            "status": "ACTIVE",
                            "priceList": {"id": "pl-uk", "currency": "GBP"},
                        }
                    ]
                },
            },
        ]
        config = {
            "US-USD": {
                "catalog_id": "catalog-us",
                "price_list_id": "pl-us",
                "catalog_title": "美国",
                "currency": "USD",
            },
            "GB-GBP": {
                "catalog_id": "catalog-uk",
                "price_list_id": "pl-uk",
                "catalog_title": "英国",
                "currency": "GBP",
            },
            "GLOBAL-USD": {
                "catalog_id": "catalog-global",
                "price_list_id": "pl-global",
                "catalog_title": "global",
                "currency": "USD",
            },
        }

        self.assertEqual(
            regional_pricing.catalog_price_lists(market_nodes, config),
            {
                "US-USD": {"catalog_id": "catalog-us", "price_list_id": "pl-us", "currency": "USD"},
                "GB-GBP": {"catalog_id": "catalog-uk", "price_list_id": "pl-uk", "currency": "GBP"},
                "GLOBAL-USD": {
                    "catalog_id": "catalog-global",
                    "price_list_id": "pl-global",
                    "currency": "USD",
                },
            },
        )

        market_nodes[0]["catalogs"]["nodes"].append(
            {
                "id": "catalog-new",
                "title": "New market",
                "status": "ACTIVE",
                "priceList": {"id": "pl-new", "currency": "CAD"},
            }
        )
        with self.assertRaisesRegex(ValueError, "未纳入区域定价配置"):
            regional_pricing.catalog_price_lists(market_nodes, config)

    def test_pricing_actions_preserve_base_inheritance_and_are_idempotent(self):
        expected = {
            "US-USD": {"v1": Decimal("19.99"), "v2": Decimal("159.92")},
            "GB-GBP": {"v1": Decimal("22.99"), "v2": Decimal("183.92")},
        }
        actual = {
            "US-USD": {
                "v1": {
                    "amount": Decimal("19.99"),
                    "currency": "USD",
                    "origin": "FIXED",
                    "compare_at": None,
                },
                "v2": {
                    "amount": Decimal("159.92"),
                    "currency": "USD",
                    "origin": "RELATIVE",
                    "compare_at": None,
                },
            },
            "GB-GBP": {
                "v1": {
                    "amount": Decimal("19.99"),
                    "currency": "USD",
                    "origin": "RELATIVE",
                    "compare_at": None,
                },
                "v2": {
                    "amount": Decimal("183.92"),
                    "currency": "GBP",
                    "origin": "FIXED",
                    "compare_at": None,
                },
            },
        }
        modes = {"US-USD": "BASE", "GB-GBP": "FIXED"}
        currencies = {"US-USD": "USD", "GB-GBP": "GBP"}

        actions = regional_pricing.pricing_actions(expected, actual, modes, currencies)

        self.assertEqual(actions["delete"], {"US-USD": ["v1"]})
        self.assertEqual(
            actions["add"],
            {
                "GB-GBP": [
                    {"variant_id": "v1", "amount": Decimal("22.99"), "currency": "GBP"}
                ]
            },
        )

        actual["US-USD"]["v1"]["origin"] = "RELATIVE"
        actual["GB-GBP"]["v1"] = {
            "amount": Decimal("22.99"),
            "currency": "GBP",
            "origin": "FIXED",
            "compare_at": None,
        }
        self.assertEqual(
            regional_pricing.pricing_actions(expected, actual, modes, currencies),
            {"add": {}, "delete": {}},
        )

    def test_missing_base_snapshot_blocks_before_fixed_price_writes(self):
        with self.assertRaisesRegex(ValueError, "BASE.*缺少"):
            regional_pricing.pricing_actions(
                {"US-USD": {"v1": Decimal("19.99")}},
                {"US-USD": {}},
                {"US-USD": "BASE"},
                {"US-USD": "USD"},
            )

    def test_existing_compare_at_price_blocks_regional_overwrite(self):
        expected = {"GB-GBP": {"v1": Decimal("22.99")}}
        actual = {
            "GB-GBP": {
                "v1": {
                    "amount": Decimal("25.99"),
                    "currency": "GBP",
                    "origin": "FIXED",
                    "compare_at": Decimal("29.99"),
                }
            }
        }
        with self.assertRaisesRegex(ValueError, "Compare-at"):
            regional_pricing.pricing_actions(
                expected,
                actual,
                {"GB-GBP": "FIXED"},
                {"GB-GBP": "GBP"},
            )

    def test_target_and_reference_must_both_match_the_table(self):
        expected = {
            "US-USD": {"v1": Decimal("19.99"), "v2": Decimal("159.92")},
            "GB-GBP": {"v1": Decimal("22.99"), "v2": Decimal("183.92")},
        }
        actual = {
            "US-USD": {"v1": Decimal("19.99"), "v2": Decimal("159.92")},
            "GB-GBP": {"v1": Decimal("22.99"), "v2": Decimal("180")},
        }
        reference = {
            "US-USD": {1: Decimal("19.99"), 8: Decimal("159.92")},
            "GB-GBP": {1: Decimal("22.99"), 8: Decimal("183.92")},
        }

        errors = regional_pricing.price_mismatches(
            expected,
            actual,
            reference,
            target_multipliers={"v1": 1, "v2": 8},
        )

        self.assertEqual(errors, ["GB-GBP/v2: target=180 expected=183.92"])

        reference["GB-GBP"][8] = Decimal("181")
        errors = regional_pricing.price_mismatches(
            expected,
            expected,
            reference,
            target_multipliers={"v1": 1, "v2": 8},
        )
        self.assertEqual(errors, ["GB-GBP/x8: reference=181 expected=183.92"])

    def test_origin_currency_and_compare_at_are_part_of_same_tier_verification(self):
        expected = {"US-USD": {"v1": Decimal("19.99")}}
        target = {
            "US-USD": {
                "v1": {
                    "amount": Decimal("19.99"),
                    "currency": "USD",
                    "origin": "FIXED",
                    "compare_at": None,
                }
            }
        }
        reference = {
            "US-USD": {
                1: {
                    "amount": Decimal("19.99"),
                    "currency": "USD",
                    "origin": "RELATIVE",
                    "compare_at": None,
                }
            }
        }

        errors = regional_pricing.price_mismatches(
            expected,
            target,
            reference,
            target_multipliers={"v1": 1},
            market_modes={"US-USD": "BASE"},
            market_currencies={"US-USD": "USD"},
        )

        self.assertEqual(errors, ["US-USD/v1: target origin=FIXED expected=RELATIVE"])


class FakePricingBackend:
    def __init__(self, table_payloads=None, reference_drift=False):
        self.table_payloads = list(table_payloads or [self._table_payload()])
        self.table_reads = 0
        self.mutations = []
        self.products = {
            "target": {
                "id": "target",
                "title": "Target",
                "status": "DRAFT",
                "variants": {
                    "nodes": [
                        {"id": "v1", "title": "1 Pc", "sku": "T", "price": "19.99", "compareAtPrice": None},
                        {"id": "v8", "title": "1 Set", "sku": "T*8", "price": "159.92", "compareAtPrice": None},
                    ]
                },
                "resourcePublicationsV2": {
                    "nodes": [
                        {"publication": {"id": "pub-us", "catalog": {"id": "cat-us"}}},
                        {"publication": {"id": "pub-gb", "catalog": {"id": "cat-gb"}}},
                        {"publication": {"id": "pub-global", "catalog": {"id": "cat-global"}}},
                    ],
                    "pageInfo": {"hasNextPage": False},
                },
            },
            "reference": {
                "id": "reference",
                "title": "Reference",
                "status": "ACTIVE",
                "variants": {
                    "nodes": [
                        {"id": "r1", "title": "1 Pc", "sku": "R", "price": "19.99", "compareAtPrice": None},
                        {"id": "r8", "title": "1 Set", "sku": "R*8", "price": "159.92", "compareAtPrice": None},
                    ]
                },
                "resourcePublicationsV2": {
                    "nodes": [
                        {"publication": {"id": "pub-us", "catalog": {"id": "cat-us"}}},
                        {"publication": {"id": "pub-gb", "catalog": {"id": "cat-gb"}}},
                        {"publication": {"id": "pub-global", "catalog": {"id": "cat-global"}}},
                    ],
                    "pageInfo": {"hasNextPage": False},
                },
            },
        }
        self.snapshots = {
            "target": {
                "US-USD": {
                    "v1": self._snapshot("19.99", "USD", "RELATIVE"),
                    "v8": self._snapshot("159.92", "USD", "RELATIVE"),
                },
                "GB-GBP": {
                    "v1": self._snapshot("19.99", "USD", "RELATIVE"),
                    "v8": self._snapshot("183.92", "GBP", "FIXED"),
                },
                "GLOBAL-USD": {
                    "v1": self._snapshot("19.99", "USD", "RELATIVE"),
                    "v8": self._snapshot("159.92", "USD", "RELATIVE"),
                },
            },
            "reference": {
                "US-USD": {
                    "r1": self._snapshot("19.99", "USD", "RELATIVE"),
                    "r8": self._snapshot("159.92", "USD", "RELATIVE"),
                },
                "GB-GBP": {
                    "r1": self._snapshot("22.99" if not reference_drift else "21.99", "GBP", "FIXED"),
                    "r8": self._snapshot("183.92", "GBP", "FIXED"),
                },
                "GLOBAL-USD": {
                    "r1": self._snapshot("19.99", "USD", "RELATIVE"),
                    "r8": self._snapshot("159.92", "USD", "RELATIVE"),
                },
            },
        }

    @staticmethod
    def _snapshot(amount, currency, origin):
        return {
            "amount": Decimal(amount),
            "currency": currency,
            "origin": origin,
            "compare_at": None,
        }

    @staticmethod
    def _table_payload(gb="£22.99"):
        return {
            "ok": True,
            "data": {
                "fields": ["市场键", "币种", "P02｜¥69档"],
                "data": [["US-USD", "USD", "$19.99"], ["GB-GBP", "GBP", gb]],
                "has_more": False,
            },
        }

    def read_pricing_table(self, source, tier_field):
        value = self.table_payloads[min(self.table_reads, len(self.table_payloads) - 1)]
        self.table_reads += 1
        return deepcopy(value)

    def get_product(self, product_id):
        return deepcopy(self.products[product_id])

    def get_market_nodes(self):
        return [
            {
                "name": "United States",
                "status": "ACTIVE",
                "catalogs": {
                    "nodes": [
                        {
                            "id": "cat-us",
                            "title": "美国",
                            "status": "ACTIVE",
                            "priceList": {"id": "pl-us", "currency": "USD"},
                        },
                        {
                            "id": "cat-global",
                            "title": "global",
                            "status": "ACTIVE",
                            "priceList": {"id": "pl-global", "currency": "USD"},
                        }
                    ]
                },
            },
            {
                "name": "United Kingdom",
                "status": "ACTIVE",
                "catalogs": {
                    "nodes": [
                        {
                            "id": "cat-gb",
                            "title": "英国",
                            "status": "ACTIVE",
                            "priceList": {"id": "pl-gb", "currency": "GBP"},
                        }
                    ]
                },
            },
        ]

    def get_price_snapshots(self, price_lists, product):
        return deepcopy(self.snapshots[product["id"]])

    def update_base_prices(self, product_id, updates):
        self.mutations.append(("base", deepcopy(updates)))
        for update in updates:
            for variant in self.products[product_id]["variants"]["nodes"]:
                if variant["id"] == update["id"]:
                    variant["price"] = update["price"]

    def delete_fixed_prices(self, price_list_id, variant_ids):
        self.mutations.append(("delete", price_list_id, list(variant_ids)))
        market_key = {
            "pl-us": "US-USD",
            "pl-gb": "GB-GBP",
            "pl-global": "GLOBAL-USD",
        }[price_list_id]
        product = self.products["target"]
        for variant_id in variant_ids:
            variant = next(v for v in product["variants"]["nodes"] if v["id"] == variant_id)
            self.snapshots["target"][market_key][variant_id] = self._snapshot(
                variant["price"], "USD", "RELATIVE"
            )

    def add_fixed_prices(self, price_list_id, prices):
        self.mutations.append(("add", price_list_id, deepcopy(prices)))
        market_key = {
            "pl-us": "US-USD",
            "pl-gb": "GB-GBP",
            "pl-global": "GLOBAL-USD",
        }[price_list_id]
        for item in prices:
            self.snapshots["target"][market_key][item["variantId"]] = self._snapshot(
                item["price"]["amount"], item["price"]["currencyCode"], "FIXED"
            )


@unittest.skipUnless(
    regional_pricing is not None and callable(getattr(regional_pricing, "execute_pricing", None)),
    "regional pricing orchestration is not implemented yet",
)
class RegionalPricingOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "pricing": {
                "source": {"tier_fields": {"P02": "P02｜¥69档"}},
                "market_catalogs": {
                    "US-USD": {
                        "catalog_id": "cat-us",
                        "price_list_id": "pl-us",
                        "catalog_title": "美国",
                        "currency": "USD",
                        "mode": "BASE",
                        "price_source_key": "US-USD",
                    },
                    "GLOBAL-USD": {
                        "catalog_id": "cat-global",
                        "price_list_id": "pl-global",
                        "catalog_title": "global",
                        "currency": "USD",
                        "mode": "BASE",
                        "price_source_key": "US-USD",
                    },
                    "GB-GBP": {
                        "catalog_id": "cat-gb",
                        "price_list_id": "pl-gb",
                        "catalog_title": "英国",
                        "currency": "GBP",
                        "mode": "FIXED",
                        "price_source_key": "GB-GBP",
                    },
                },
                "unsupported_market_keys": [],
                "reference_products": {"P02": "reference"},
            }
        }

    def test_reference_drift_blocks_even_in_dry_run(self):
        backend = FakePricingBackend(reference_drift=True)

        with self.assertRaisesRegex(ValueError, "REFERENCE_DRIFT"):
            regional_pricing.execute_pricing(
                self.config,
                product_id="target",
                tier="P02",
                apply=False,
                backend=backend,
                emit=lambda _line: None,
            )

        self.assertEqual(backend.mutations, [])

    @staticmethod
    def _make_target_sixteen_pack(backend):
        target = backend.products["target"]
        target["variants"]["nodes"][1] = {
            "id": "v16",
            "title": "1 Set",
            "sku": "T*16",
            "price": "319.84",
            "compareAtPrice": None,
        }
        for market_key, snapshots in backend.snapshots["target"].items():
            previous = snapshots.pop("v8")
            snapshots["v16"] = backend._snapshot(
                "319.84",
                "USD",
                "RELATIVE",
            )

    def test_packaging_mismatch_still_blocks_without_explicit_opt_in(self):
        backend = FakePricingBackend()
        self._make_target_sixteen_pack(backend)

        with self.assertRaisesRegex(ValueError, "包装倍数不一致"):
            regional_pricing.execute_pricing(
                self.config,
                product_id="target",
                tier="P02",
                apply=False,
                backend=backend,
                emit=lambda _line: None,
            )

        self.assertEqual(backend.mutations, [])

    def test_explicit_unit_price_mode_allows_reference_with_different_case_count(self):
        backend = FakePricingBackend()
        self._make_target_sixteen_pack(backend)

        report = regional_pricing.execute_pricing(
            self.config,
            product_id="target",
            tier="P02",
            apply=False,
            backend=backend,
            allow_reference_packaging_mismatch=True,
            emit=lambda _line: None,
        )

        self.assertEqual(report["planned_writes"], 2)
        self.assertEqual(backend.mutations, [])

    def test_apply_writes_only_the_diff_then_verifies_zero_mutations(self):
        backend = FakePricingBackend()

        report = regional_pricing.execute_pricing(
            self.config,
            product_id="target",
            tier="P02",
            apply=True,
            backend=backend,
            emit=lambda _line: None,
        )

        self.assertEqual(
            backend.mutations,
            [
                (
                    "add",
                    "pl-gb",
                    [
                        {
                            "variantId": "v1",
                            "price": {"amount": "22.99", "currencyCode": "GBP"},
                        }
                    ],
                )
            ],
        )
        self.assertEqual(report["writes"], 1)
        self.assertTrue(report["idempotent"])
        self.assertEqual(backend.products["target"]["status"], "DRAFT")

    def test_apply_rechecks_the_feishu_table_before_any_mutation(self):
        backend = FakePricingBackend(
            table_payloads=[
                FakePricingBackend._table_payload("£22.99"),
                FakePricingBackend._table_payload("£23.99"),
            ]
        )

        with self.assertRaisesRegex(ValueError, "写入前发生变化"):
            regional_pricing.execute_pricing(
                self.config,
                product_id="target",
                tier="P02",
                apply=True,
                backend=backend,
                emit=lambda _line: None,
            )

        self.assertEqual(backend.mutations, [])

    def test_global_fixed_price_is_detected_and_planned_for_inheritance(self):
        backend = FakePricingBackend()
        backend.snapshots["target"]["GLOBAL-USD"]["v1"]["origin"] = "FIXED"

        report = regional_pricing.execute_pricing(
            self.config,
            product_id="target",
            tier="P02",
            apply=False,
            backend=backend,
            emit=lambda _line: None,
        )

        self.assertEqual(report["planned_writes"], 2)
        self.assertEqual(backend.mutations, [])

    def test_relative_base_adjustment_drift_blocks_dry_run(self):
        backend = FakePricingBackend()
        backend.snapshots["target"]["GLOBAL-USD"]["v1"]["amount"] = Decimal("18.99")

        with self.assertRaisesRegex(ValueError, "BASE.*基础价"):
            regional_pricing.execute_pricing(
                self.config,
                product_id="target",
                tier="P02",
                apply=False,
                backend=backend,
                emit=lambda _line: None,
            )

        self.assertEqual(backend.mutations, [])

    def test_missing_catalog_membership_blocks_before_price_mutation(self):
        backend = FakePricingBackend()
        backend.products["target"]["resourcePublicationsV2"]["nodes"] = [
            node
            for node in backend.products["target"]["resourcePublicationsV2"]["nodes"]
            if node["publication"]["catalog"]["id"] != "cat-gb"
        ]

        with self.assertRaisesRegex(ValueError, "Catalog membership"):
            regional_pricing.execute_pricing(
                self.config,
                product_id="target",
                tier="P02",
                apply=False,
                backend=backend,
                emit=lambda _line: None,
            )

        self.assertEqual(backend.mutations, [])

    def test_base_price_concurrency_drift_blocks_and_preserves_newer_value(self):
        backend = FakePricingBackend()
        backend.products["target"]["variants"]["nodes"][1]["price"] = "150"
        backend.snapshots["target"]["US-USD"]["v8"]["amount"] = Decimal("150")
        backend.snapshots["target"]["GLOBAL-USD"]["v8"]["amount"] = Decimal("150")
        original_get_product = backend.get_product
        target_reads = 0

        def concurrent_get_product(product_id):
            nonlocal target_reads
            product = original_get_product(product_id)
            if product_id == "target":
                target_reads += 1
                if target_reads == 2:
                    product["variants"]["nodes"][1]["price"] = "151"
            return product

        backend.get_product = concurrent_get_product

        with self.assertRaisesRegex(ValueError, "写入前发生变化"):
            regional_pricing.execute_pricing(
                self.config,
                product_id="target",
                tier="P02",
                apply=True,
                backend=backend,
                emit=lambda _line: None,
            )

        self.assertEqual(backend.mutations, [])

    def test_mutation_that_changes_state_then_errors_is_compensated(self):
        backend = FakePricingBackend()
        original_add = backend.add_fixed_prices

        def mutate_then_fail(price_list_id, prices):
            original_add(price_list_id, prices)
            raise RuntimeError("timeout after server applied mutation")

        backend.add_fixed_prices = mutate_then_fail

        with self.assertRaisesRegex(RuntimeError, "已回滚"):
            regional_pricing.execute_pricing(
                self.config,
                product_id="target",
                tier="P02",
                apply=True,
                backend=backend,
                emit=lambda _line: None,
            )

        self.assertEqual(
            backend.snapshots["target"]["GB-GBP"]["v1"]["origin"],
            "RELATIVE",
        )

    def test_catalog_price_list_switch_during_apply_triggers_rollback(self):
        backend = FakePricingBackend()
        original_get_markets = backend.get_market_nodes
        market_reads = 0

        def changing_markets():
            nonlocal market_reads
            market_reads += 1
            nodes = original_get_markets()
            if market_reads >= 3:
                for market in nodes:
                    for catalog in market["catalogs"]["nodes"]:
                        if catalog["id"] == "cat-gb":
                            catalog["priceList"]["id"] = "pl-gb-new"
            return nodes

        backend.get_market_nodes = changing_markets

        with self.assertRaisesRegex(RuntimeError, "Catalog/PriceList.*写入期间"):
            regional_pricing.execute_pricing(
                self.config,
                product_id="target",
                tier="P02",
                apply=True,
                backend=backend,
                emit=lambda _line: None,
            )

        self.assertEqual(
            backend.snapshots["target"]["GB-GBP"]["v1"]["origin"],
            "RELATIVE",
        )

    def test_partial_failure_rolls_back_changes_already_applied(self):
        backend = FakePricingBackend()
        backend.products["target"]["variants"]["nodes"][1]["price"] = "150"
        backend.snapshots["target"]["US-USD"]["v8"]["amount"] = Decimal("150")
        backend.snapshots["target"]["GLOBAL-USD"]["v8"]["amount"] = Decimal("150")

        def fail_fixed_add(_price_list_id, _prices):
            raise RuntimeError("injected fixed-price failure")

        backend.add_fixed_prices = fail_fixed_add

        with self.assertRaisesRegex(RuntimeError, "已回滚"):
            regional_pricing.execute_pricing(
                self.config,
                product_id="target",
                tier="P02",
                apply=True,
                backend=backend,
                emit=lambda _line: None,
            )

        restored = backend.products["target"]["variants"]["nodes"][1]
        self.assertEqual(restored["price"], "150")
        self.assertEqual(backend.products["target"]["status"], "DRAFT")
        self.assertEqual(
            backend.mutations,
            [
                ("base", [{"id": "v8", "price": "159.92"}]),
                ("delete", "pl-gb", ["v1"]),
                ("base", [{"id": "v8", "price": "150"}]),
            ],
        )


if __name__ == "__main__":
    unittest.main()

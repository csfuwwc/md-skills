import sys
import unittest
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import _lib  # noqa: E402
import entities  # noqa: E402
import health  # noqa: E402
import qa  # noqa: E402
import sync_pull  # noqa: E402
import sync_writeback  # noqa: E402
import translate  # noqa: E402


def product_node():
    return {
        "id": "gid://shopify/Product/1",
        "handle": "moco-test",
        "onlineStoreUrl": "https://example.com/products/moco-test",
        "status": "ACTIVE",
        "vendor": "Funcinating",
        "productType": "Plush Blind Box",
        "tags": ["badge:new"],
        "category": {"fullName": "Toys > Stuffed Animals"},
        "title": "MOCO Test",
        "descriptionHtml": "<p>Test</p>",
        "seo": {"title": "MOCO Test", "description": "Test description"},
        "featuredImage": {"url": "https://cdn.example.com/moco.jpg"},
        "variants": {
            "edges": [
                {
                    "node": {
                        "id": "gid://shopify/ProductVariant/1",
                        "title": "Single",
                        "sku": "SKU-1",
                        "price": "19.99",
                        "inventoryQuantity": 100,
                        "inventoryPolicy": "DENY",
                    }
                }
            ]
        },
        "collections": {"edges": [{"node": {"handle": "moco"}}]},
        "metafields": {
            "edges": [
                {
                    "node": {
                        "namespace": "custom",
                        "key": "material",
                        "value": "Polyester fibre + ABS + PVC",
                    }
                }
            ]
        },
    }


class ProductMappingTests(unittest.TestCase):
    def test_product_mapping_includes_live_mirror_fields_and_normalized_content(self):
        mirror, content = entities.build_product(
            product_node(),
            {"collections": {"ip": ["moco"], "category": [], "scenario": []}},
        )

        self.assertEqual(mirror["Product Type"], "Plush Blind Box")
        self.assertEqual(mirror["Shopify分类"], "Toys > Stuffed Animals")
        self.assertEqual(content["Tags|标签"], ["badge:new"])
        self.assertEqual(
            content["custom.material 材质"], ["Polyester", "ABS", "PVC"]
        )

    def test_multi_select_text_keeps_boundaries(self):
        self.assertEqual(
            _lib.cell_text(["Polyester", "ABS", "PVC"]),
            "Polyester, ABS, PVC",
        )


class FeishuPaginationTests(unittest.TestCase):
    def test_bitable_list_reads_every_page(self):
        first = {
            "data": {
                "items": [{"record_id": "rec_1", "fields": {}}],
                "has_more": True,
                "page_token": "next-page",
            }
        }
        second = {
            "data": {
                "items": [{"record_id": "rec_2", "fields": {}}],
                "has_more": False,
            }
        }
        with mock.patch.object(_lib, "_lark", side_effect=[first, second]) as lark:
            rows = _lib.bitable_list(
                {"feishu": {"app_token": "app", "table_id": "tbl"}}
            )

        self.assertEqual([row["record_id"] for row in rows], ["rec_1", "rec_2"])
        self.assertIn("next-page", lark.call_args_list[1].args[0][-1])


class ShopifyCliErrorTests(unittest.TestCase):
    def test_graphql_errors_are_not_silently_dropped(self):
        def fake_run(command, **_kwargs):
            output = command[command.index("--output-file") + 1]
            Path(output).write_text(
                json.dumps({"data": {"product": None}, "errors": [{"message": "boom"}]}),
                encoding="utf-8",
            )
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch.object(_lib.subprocess, "run", side_effect=fake_run):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                _lib.shopify("query { shop { id } }", "shop.myshopify.com")

    def test_cli_nonzero_exit_is_reported(self):
        failed = SimpleNamespace(returncode=1, stdout="", stderr="network failed")
        with mock.patch.object(_lib.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(RuntimeError, "network failed"):
                _lib.shopify("query { shop { id } }", "shop.myshopify.com")


class LarkCliErrorTests(unittest.TestCase):
    def test_lark_cli_nonzero_exit_is_reported(self):
        failed = SimpleNamespace(returncode=1, stdout="", stderr='{"error":{"message":"keychain unavailable"}}')
        with mock.patch.object(_lib.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(RuntimeError, "keychain unavailable"):
                _lib._lark(["base", "+record-list"], None)


required_pull_helpers = (
    getattr(sync_pull, "product_query_term", None),
    getattr(sync_pull, "record_patch", None),
    getattr(sync_pull, "new_record_fields", None),
)


class PullFeatureAvailabilityTests(unittest.TestCase):
    def test_targeted_mirror_helpers_exist(self):
        self.assertTrue(
            all(callable(helper) for helper in required_pull_helpers),
            "targeted mirror-only pull helpers are missing",
        )


@unittest.skipUnless(
    all(callable(helper) for helper in required_pull_helpers),
    "targeted mirror-only pull is not implemented yet",
)
class PullPlanningTests(unittest.TestCase):
    def test_product_query_term_accepts_gid_and_rejects_other_entities(self):
        self.assertEqual(
            sync_pull.product_query_term(
                "product", "gid://shopify/Product/9618451235071", False, "draft"
            ),
            "id:9618451235071",
        )
        with self.assertRaisesRegex(ValueError, "只适用于 product"):
            sync_pull.product_query_term(
                "collection", "gid://shopify/Product/1", False, "draft"
            )

    def test_mirror_only_patch_ignores_content_and_writes_only_differences(self):
        patch = sync_pull.record_patch(
            mirror={"状态": "ACTIVE", "总库存": 200, "商品URL": "https://x"},
            content={"商品名称": "New title"},
            current={"状态": "DRAFT", "总库存": 0, "商品名称": "Old title"},
            field_types={"状态": 1, "总库存": 2, "商品URL": 15, "商品名称": 1},
            sync_date_field="最近Shopify同步日期",
            now_ms=123,
            mirror_only=True,
        )

        self.assertEqual(patch["状态"], "ACTIVE")
        self.assertEqual(patch["总库存"], 200)
        self.assertEqual(patch["商品URL"]["link"], "https://x")
        self.assertNotIn("商品名称", patch)
        self.assertEqual(patch["最近Shopify同步日期"], 123)

        self.assertEqual(
            sync_pull.record_patch(
                mirror={"状态": "ACTIVE"},
                content={},
                current={"状态": "ACTIVE"},
                field_types={"状态": 1},
                sync_date_field="最近Shopify同步日期",
                now_ms=456,
                mirror_only=True,
            ),
            {},
        )

    def test_new_product_starts_with_pending_operation_priority(self):
        fields = sync_pull.new_record_fields(
            mirror={"Shopify Product ID": "gid://shopify/Product/1"},
            content={},
            field_types={
                "Shopify Product ID": 1,
                "运营优先级": 3,
                "Shopify写回状态": 3,
                "FAQ JSON校验状态": 3,
                "Shopify写回时间": 5,
                "写回错误信息": 1,
            },
            workflow_status_field="内容审核状态",
            sync_date_field="最近Shopify同步日期",
            now_ms=123,
            mirror_only=True,
        )

        self.assertEqual(fields["运营优先级"], "待评估")
        self.assertEqual(fields["内容审核状态"], "待补素材")
        self.assertEqual(fields["Shopify写回状态"], "未写回")
        self.assertEqual(fields["FAQ JSON校验状态"], "待检查")
        self.assertNotIn("Shopify写回时间", fields)
        self.assertNotIn("写回错误信息", fields)

    def test_mirror_refresh_can_clear_a_stale_shopify_value(self):
        patch = sync_pull.record_patch(
            mirror={"商品URL": ""},
            content={},
            current={"商品URL": {"link": "https://old.example", "text": "old"}},
            field_types={"商品URL": 15},
            sync_date_field="最近Shopify同步日期",
            now_ms=789,
            mirror_only=True,
        )

        self.assertIsNone(patch["商品URL"])
        self.assertEqual(patch["最近Shopify同步日期"], 789)


required_writeback_helpers = (
    getattr(sync_writeback, "mutation_user_errors", None),
    getattr(sync_writeback, "product_readback_issues", None),
    getattr(sync_writeback, "writeback_result_fields", None),
)


class WritebackFeatureAvailabilityTests(unittest.TestCase):
    def test_writeback_verification_helpers_exist(self):
        self.assertTrue(
            all(callable(helper) for helper in required_writeback_helpers),
            "writeback verification helpers are missing",
        )


required_sellability_helpers = (
    getattr(sync_writeback, "shipping_profile_issues", None),
    getattr(sync_writeback, "storefront_sellability_issues", None),
    getattr(sync_writeback, "delivery_profile_variant_ids_to_associate", None),
    getattr(sync_writeback, "storefront_product_json_url", None),
    getattr(sync_writeback, "fetch_storefront_product_json", None),
)


class SellabilityFeatureAvailabilityTests(unittest.TestCase):
    def test_shipping_and_storefront_verification_helpers_exist(self):
        self.assertTrue(
            all(callable(helper) for helper in required_sellability_helpers),
            "shipping profile and storefront sellability verification are missing",
        )


@unittest.skipUnless(
    all(callable(helper) for helper in required_sellability_helpers),
    "sellability verification is not implemented yet",
)
class SellabilityVerificationTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "id": "gid://shopify/DeliveryProfile/1",
            "name": "范趣町配送",
            "profileItems": {
                "nodes": [{
                    "product": {"id": "gid://shopify/Product/1"},
                    "variants": {
                        "nodes": [
                            {"id": "gid://shopify/ProductVariant/1"},
                            {"id": "gid://shopify/ProductVariant/2"},
                        ],
                        "pageInfo": {"hasNextPage": False},
                    },
                }],
                "pageInfo": {"hasNextPage": False},
            },
            "profileLocationGroups": [{
                "locationGroup": {
                    "locations": {
                        "nodes": [{
                            "id": "gid://shopify/Location/1",
                            "name": "百橙云仓",
                            "isActive": True,
                            "fulfillsOnlineOrders": True,
                        }],
                        "pageInfo": {"hasNextPage": False},
                    }
                },
                "locationGroupZones": {
                    "nodes": [{
                        "zone": {
                            "name": "Singapore",
                            "countries": [{
                                "code": {"countryCode": "SG", "restOfWorld": False}
                            }],
                        },
                        "methodDefinitions": {
                            "nodes": [{"id": "method-1", "active": True}],
                            "pageInfo": {"hasNextPage": False},
                        },
                    }],
                    "pageInfo": {"hasNextPage": False},
                },
            }],
        }
        self.product = {
            "id": "gid://shopify/Product/1",
            "variants": {
                "nodes": [
                    self._variant("gid://shopify/ProductVariant/1", 10),
                    self._variant("gid://shopify/ProductVariant/2", 10),
                ],
                "pageInfo": {"hasNextPage": False},
            },
        }

    @staticmethod
    def _variant(variant_id, available):
        return {
            "id": variant_id,
            "sku": variant_id.rsplit("/", 1)[-1],
            "inventoryPolicy": "DENY",
            "sellableOnlineQuantity": available,
            "inventoryItem": {
                "tracked": True,
                "requiresShipping": True,
                "inventoryLevels": {
                    "nodes": [{
                        "location": {
                            "id": "gid://shopify/Location/1",
                            "name": "百橙云仓",
                            "isActive": True,
                            "fulfillsOnlineOrders": True,
                        },
                        "quantities": [{"name": "available", "quantity": available}],
                    }],
                    "pageInfo": {"hasNextPage": False},
                },
            },
        }

    def test_valid_profile_zone_inventory_and_methods_pass(self):
        self.assertEqual(
            sync_writeback.shipping_profile_issues(
                self.profile, self.product, ["SG"]
            ),
            [],
        )

    def test_delivery_profile_plan_only_associates_missing_variants(self):
        self.profile["profileItems"]["nodes"][0]["variants"]["nodes"].pop()

        self.assertEqual(
            sync_writeback.delivery_profile_variant_ids_to_associate(
                self.profile, self.product
            ),
            ["gid://shopify/ProductVariant/2"],
        )

    def test_storefront_json_url_uses_configured_market_path(self):
        self.assertEqual(
            sync_writeback.storefront_product_json_url(
                "www.funcinating.com", "en-sg", "moco test"
            ),
            "https://www.funcinating.com/en-sg/products/moco%20test.js",
        )

    def test_storefront_fetch_uses_curl_and_decodes_json(self):
        completed = SimpleNamespace(
            returncode=0,
            stdout='{"available":true,"variants":[]}',
            stderr="",
        )

        payload = sync_writeback.fetch_storefront_product_json(
            "https://example.com/products/a.js",
            runner=mock.Mock(return_value=completed),
        )

        self.assertTrue(payload["available"])

    def test_storefront_fetch_reports_http_failure(self):
        completed = SimpleNamespace(returncode=22, stdout="", stderr="HTTP 404")

        with self.assertRaisesRegex(RuntimeError, "HTTP 404"):
            sync_writeback.fetch_storefront_product_json(
                "https://example.com/products/a.js",
                runner=mock.Mock(return_value=completed),
            )

    def test_profile_without_country_zone_is_blocked(self):
        self.profile["profileLocationGroups"][0]["locationGroupZones"]["nodes"] = []

        issues = sync_writeback.shipping_profile_issues(
            self.profile, self.product, ["SG"]
        )

        self.assertTrue(any("SG" in issue and "运费" in issue for issue in issues))

    def test_profile_missing_one_variant_is_blocked(self):
        self.profile["profileItems"]["nodes"][0]["variants"]["nodes"].pop()

        issues = sync_writeback.shipping_profile_issues(
            self.profile, self.product, ["SG"]
        )

        self.assertTrue(any("ProductVariant/2" in issue for issue in issues))

    def test_deny_variant_requires_positive_inventory_at_eligible_location(self):
        self.product["variants"]["nodes"][0]["inventoryItem"]["inventoryLevels"]["nodes"][0]["quantities"][0]["quantity"] = 0

        issues = sync_writeback.shipping_profile_issues(
            self.profile, self.product, ["SG"]
        )

        self.assertTrue(any("ProductVariant/1" in issue and "库存" in issue for issue in issues))

    def test_deny_variant_requires_positive_sellable_online_quantity(self):
        self.product["variants"]["nodes"][0]["sellableOnlineQuantity"] = 0

        issues = sync_writeback.shipping_profile_issues(
            self.profile, self.product, ["SG"]
        )

        self.assertTrue(
            any("ProductVariant/1" in issue and "sellableOnlineQuantity" in issue for issue in issues)
        )

    def test_storefront_json_must_mark_every_variant_available(self):
        payload = {
            "available": False,
            "variants": [
                {"id": 1, "sku": "1", "available": True},
                {"id": 2, "sku": "2", "available": False},
            ],
        }

        issues = sync_writeback.storefront_sellability_issues(
            payload,
            ["gid://shopify/ProductVariant/1", "gid://shopify/ProductVariant/2"],
        )

        self.assertTrue(any("ProductVariant/2" in issue for issue in issues))

    def test_storefront_json_with_all_variants_available_passes(self):
        payload = {
            "available": True,
            "variants": [
                {"id": 1, "available": True},
                {"id": 2, "available": True},
            ],
        }

        self.assertEqual(
            sync_writeback.storefront_sellability_issues(
                payload,
                ["gid://shopify/ProductVariant/1", "gid://shopify/ProductVariant/2"],
            ),
            [],
        )


@unittest.skipUnless(
    all(callable(helper) for helper in required_writeback_helpers),
    "writeback verification is not implemented yet",
)
class WritebackVerificationTests(unittest.TestCase):
    def test_collection_handles_are_stably_deduplicated(self):
        self.assertEqual(
            sync_writeback.stable_unique(
                ["gismow", "bag-charms", "bag-charms", "plush"]
            ),
            ["gismow", "bag-charms", "plush"],
        )

    def test_collection_handles_are_normalized_to_lowercase(self):
        self.assertEqual(
            sync_writeback.normalize_collection_handles(
                ["GISMOW", "bag-charms", "Bag-Charms"]
            ),
            ["gismow", "bag-charms"],
        )

    def test_shopify_intertag_newlines_are_html_equivalent(self):
        desired = "<ul><li>One</li><li>Two</li></ul>"
        returned = "<ul>\n<li>One</li>\n<li>Two</li>\n</ul>"

        self.assertTrue(sync_writeback.shopify_html_equivalent(desired, returned))

    def test_online_store_publication_is_identified_by_shopify_app(self):
        publications = [
            {"id": "pos", "name": "POS", "app": {"id": "app-pos", "title": "POS"}},
            {
                "id": "online",
                "name": "在线商店",
                "app": {"id": "gid://shopify/App/580111", "title": "在线商店"},
            },
        ]

        self.assertEqual(
            sync_writeback.online_store_publication_id(publications), "online"
        )

    def test_any_shopify_user_error_blocks_success(self):
        self.assertEqual(
            sync_writeback.mutation_user_errors(
                {"userErrors": [{"field": ["title"], "message": "invalid"}]}
            ),
            ["title: invalid"],
        )

    def test_readback_requires_active_url_and_confirmed_inventory_policy(self):
        node = product_node()
        self.assertEqual(sync_writeback.product_readback_issues(node, "DENY"), [])

        node["onlineStoreUrl"] = None
        self.assertIn(
            "商品URL为空", sync_writeback.product_readback_issues(node, "DENY")
        )
        node["onlineStoreUrl"] = "https://example.com/products/moco-test"
        node["variants"]["edges"][0]["node"]["inventoryPolicy"] = "CONTINUE"
        self.assertTrue(
            any(
                "inventoryPolicy" in issue
                for issue in sync_writeback.product_readback_issues(node, "DENY")
            )
        )

    def test_draft_readback_does_not_require_online_url(self):
        node = product_node()
        node["status"] = "DRAFT"
        node["onlineStoreUrl"] = None

        self.assertEqual(
            sync_writeback.product_readback_issues(
                node,
                "DENY",
                expected_status="DRAFT",
                require_online_url=False,
            ),
            [],
        )

    def test_failure_result_never_marks_the_row_as_published(self):
        failure = sync_writeback.writeback_result_fields(False, "boom", 123)
        self.assertEqual(failure["Shopify写回状态"], "失败")
        self.assertEqual(failure["写回错误信息"], "boom")
        self.assertNotIn("内容审核状态", failure)

        success = sync_writeback.writeback_result_fields(True, "", 456)
        self.assertEqual(success["Shopify写回状态"], "成功")
        self.assertEqual(success["内容审核状态"], "已上线")

        prepared = sync_writeback.writeback_result_fields(
            True, "", 789, prepared_draft=True
        )
        self.assertEqual(prepared["Shopify写回状态"], "已写回")
        self.assertNotIn("内容审核状态", prepared)

    def test_verified_readback_always_refreshes_sync_timestamp(self):
        patch = sync_writeback.product_mirror_patch(
            product_node(),
            {"collections": {"ip": ["moco"], "category": [], "scenario": []}},
            {"状态": "ACTIVE"},
            {"状态": 1},
            "最近Shopify同步日期",
            999,
        )

        self.assertEqual(patch["最近Shopify同步日期"], 999)

    def test_description_guard_rejects_markdown_wrapped_image_sources(self):
        desired = '<p><img src="[https://cdn.example/a.jpg](https://cdn.example/a.jpg)"></p>'

        issues = sync_writeback.description_html_issues(
            desired,
            '<p><img src="https://cdn.example/a.jpg"></p>',
        )

        self.assertTrue(any("Markdown" in issue for issue in issues))

    def test_description_guard_rejects_image_count_regression(self):
        current = '<img src="a.jpg"><img src="b.jpg">'
        desired = '<p>Updated copy</p><img src="a.jpg">'

        issues = sync_writeback.description_html_issues(desired, current)

        self.assertTrue(any("2" in issue and "1" in issue for issue in issues))

    def test_description_guard_accepts_valid_html_without_image_loss(self):
        current = '<p>Old</p><img src="a.jpg"><img src="b.jpg">'
        desired = '<p>New</p><img src="a.jpg"><img src="b.jpg">'

        self.assertEqual(
            sync_writeback.description_html_issues(desired, current),
            [],
        )


class ProductQaTests(unittest.TestCase):
    def test_operation_priority_must_be_decided_before_publish(self):
        self.assertIn("运营优先级", qa.product_priority_issues({}))
        self.assertIn(
            "运营优先级", qa.product_priority_issues({"运营优先级": ["待评估"]})
        )
        self.assertEqual(
            qa.product_priority_issues({"运营优先级": ["P0/P1"]}), []
        )

    def test_faq_validation_requires_nonempty_question_and_answer_pairs(self):
        valid='[{"question":"What is it?","answer":"A blind box."}]'

        self.assertEqual(qa.faq_json_issues(valid), [])
        self.assertTrue(qa.faq_json_issues("not json"))
        self.assertTrue(qa.faq_json_issues('{}'))
        self.assertTrue(qa.faq_json_issues('[{"question":"","answer":"A"}]'))

    def test_faq_status_patch_is_explicit_and_idempotent(self):
        valid='[{"question":"What is it?","answer":"A blind box."}]'

        self.assertEqual(
            qa.faq_status_patch(
                {"custom.faq 常见问题": valid, "FAQ JSON校验状态": ["待检查"]}
            ),
            {"FAQ JSON校验状态": "通过"},
        )
        self.assertEqual(
            qa.faq_status_patch(
                {"custom.faq 常见问题": valid, "FAQ JSON校验状态": ["通过"]}
            ),
            {},
        )
        self.assertEqual(
            qa.faq_status_patch(
                {"custom.faq 常见问题": "bad", "FAQ JSON校验状态": ["通过"]}
            ),
            {"FAQ JSON校验状态": "格式错误"},
        )

    def test_product_prewrite_gate_requires_source_priority_and_valid_faq(self):
        fields={
            "运营优先级": ["待评估"],
            "资料来源|官方依据": "",
            "custom.faq 常见问题": "bad",
        }

        issues=sync_writeback.product_prewrite_issues(fields)

        self.assertIn("运营优先级", issues)
        self.assertIn("资料来源|官方依据", issues)
        self.assertTrue(any("FAQ" in issue for issue in issues))


class ProductWorkflowHealthTests(unittest.TestCase):
    def test_active_row_without_verified_writeback_is_reported_as_debt(self):
        issues=health.workflow_field_issues({
            "状态": "ACTIVE",
            "商品URL": "",
            "内容审核状态": ["已上线"],
            "Shopify写回状态": ["未写回"],
            "Shopify写回时间": None,
            "写回错误信息": "",
            "资料来源|官方依据": "",
            "custom.faq 常见问题": '[{"question":"Q","answer":"A"}]',
            "FAQ JSON校验状态": ["待检查"],
        })

        self.assertTrue(any("写回" in issue for issue in issues))
        self.assertTrue(any("商品URL" in issue for issue in issues))
        self.assertTrue(any("资料来源" in issue for issue in issues))
        self.assertTrue(any("FAQ" in issue for issue in issues))

    def test_verified_row_has_no_workflow_field_issues(self):
        self.assertEqual(health.workflow_field_issues({
            "状态": "ACTIVE",
            "商品URL": {"link": "https://example.com/products/a"},
            "内容审核状态": ["已上线"],
            "Shopify写回状态": ["成功"],
            "Shopify写回时间": 123,
            "写回错误信息": "",
            "资料来源|官方依据": "Official product sheet",
            "custom.faq 常见问题": '[{"question":"Q","answer":"A"}]',
            "FAQ JSON校验状态": ["通过"],
        }), [])


class TranslationDescriptionSafetyTests(unittest.TestCase):
    def test_product_translation_import_rejects_image_loss(self):
        data = [{
            "resourceId": "gid://shopify/Product/1",
            "contents": [{
                "key": "body_html",
                "en": '<img src="a.jpg"><img src="b.jpg">',
                "target": '<p>译文</p><img src="a.jpg">',
            }],
        }]

        issues = translate.translation_import_issues("product", data)

        self.assertTrue(any("2" in issue and "1" in issue for issue in issues))

    def test_product_translation_import_accepts_preserved_images(self):
        data = [{
            "resourceId": "gid://shopify/Product/1",
            "contents": [{
                "key": "body_html",
                "en": '<img src="a.jpg">',
                "target": '<p>译文</p><img src="a.jpg">',
            }],
        }]

        self.assertEqual(translate.translation_import_issues("product", data), [])


if __name__ == "__main__":
    unittest.main()

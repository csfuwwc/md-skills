#!/usr/bin/env python3
"""Configure a draft product's regional prices from the Feishu pricing matrix.

The matrix is the numeric source of truth.  A curated active product in the same
tier is a validation control, never a source of prices.  This script deliberately
does not publish products or add them to catalogs.
"""

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from pathlib import Path

from _lib import ensure_ready, feishu_profile, load_config


TIER_PATTERN = re.compile(r"^P0[1-7]$")


def normalize_tier(value):
    tier = (value or "").strip().upper()
    if not TIER_PATTERN.fullmatch(tier):
        raise ValueError("价格档位必须显式填写 P01-P07")
    return tier


def parse_money(value):
    text = str(value or "").strip().replace(",", "")
    number = re.sub(r"[^0-9.\-]", "", text)
    if not number or number in {"-", ".", "-."}:
        raise ValueError(f"无法解析价格: {value!r}")
    try:
        amount = Decimal(number)
    except InvalidOperation as exc:
        raise ValueError(f"无法解析价格: {value!r}") from exc
    if amount <= 0:
        raise ValueError(f"价格必须大于 0: {value!r}")
    return amount


def pricing_rows_for_tier(payload, tier_field):
    if not payload.get("ok"):
        raise ValueError(f"飞书价格表读取失败: {payload.get('error') or payload}")
    data = payload.get("data") or {}
    if data.get("has_more"):
        raise ValueError("飞书价格表未完整读取，停止定价")
    fields = data.get("fields") or []
    required = ["市场键", "币种", tier_field]
    missing = [name for name in required if name not in fields]
    if missing:
        raise ValueError(f"飞书价格表缺少字段: {', '.join(missing)}")
    indexes = {name: fields.index(name) for name in required}
    result = {}
    for row in data.get("data") or []:
        market_key = str(row[indexes["市场键"]] or "").strip()
        if not market_key:
            continue
        if market_key in result:
            raise ValueError(f"飞书价格表存在重复市场键: {market_key}")
        result[market_key] = {
            "currency": str(row[indexes["币种"]] or "").strip(),
            "unit_price": parse_money(row[indexes[tier_field]]),
        }
    if not result:
        raise ValueError("飞书价格表没有可用记录")
    return result


def validate_pricing_fields(payload, tier_field):
    if not payload.get("ok"):
        raise ValueError(f"飞书价格表字段读取失败: {payload.get('error') or payload}")
    data = payload.get("data") or {}
    fields = data.get("fields") or []
    total = data.get("total")
    if total is not None and int(total) > len(fields):
        raise ValueError("飞书价格表字段结构读取不完整")
    by_name = {}
    for field in fields:
        name = field.get("name")
        if name in by_name:
            raise ValueError(f"飞书价格表存在重名字段: {name}")
        by_name[name] = field
    required = ["市场键", "币种", tier_field]
    missing = [name for name in required if name not in by_name]
    if missing:
        raise ValueError(f"飞书价格表缺少字段: {', '.join(missing)}")
    for name in required:
        if by_name[name].get("type") not in {"text", "number"}:
            raise ValueError(f"飞书价格字段类型不支持: {name}={by_name[name].get('type')}")


def parse_multiplier_overrides(values):
    overrides = {}
    for raw in values or []:
        variant_id, sep, multiplier_text = raw.rpartition("=")
        variant_id = variant_id.strip()
        if not sep or not variant_id or not multiplier_text.strip().isdigit():
            raise ValueError("变体倍数格式必须是 VARIANT_ID=正整数")
        multiplier = int(multiplier_text)
        if multiplier <= 0:
            raise ValueError("变体倍数必须是正整数")
        if variant_id in overrides and overrides[variant_id] != multiplier:
            raise ValueError(f"{variant_id} 的变体倍数重复且冲突")
        overrides[variant_id] = multiplier
    return overrides


def variant_multiplier(variant, overrides=None):
    overrides = overrides or {}
    variant_id = variant.get("id") or ""
    if variant_id in overrides:
        return overrides[variant_id]
    sku = str(variant.get("sku") or "").strip()
    sku_match = re.search(r"\*(\d+)\s*$", sku)
    if sku_match:
        return int(sku_match.group(1))
    title = str(variant.get("title") or "").strip()
    title_match = re.search(r"(?:\(|\b)(\d+)\s*(?:boxes?|pcs?|pieces?|pza)(?:\)|\b)", title, re.I)
    if title_match:
        return int(title_match.group(1))
    normalized = re.sub(r"\s+", " ", title.lower())
    if normalized in {"1 pc", "1 pza", "single", "single box", "single blind box", "default title"}:
        return 1
    raise ValueError(
        f"无法确定变体倍数: {title or '(无标题)'} · {sku or '(无 SKU)'}；"
        "请传 --variant-multiplier VARIANT_ID=N"
    )


def validate_product_role(product, role):
    status = str(product.get("status") or "").upper()
    if role == "target" and status != "DRAFT":
        raise ValueError(f"目标商品必须保持 DRAFT，当前为 {status or 'UNKNOWN'}")
    if role == "reference" and status != "ACTIVE":
        raise ValueError(f"同档参考商品必须是 ACTIVE，当前为 {status or 'UNKNOWN'}")
    if role not in {"target", "reference"}:
        raise ValueError(f"未知商品角色: {role}")


def _decimal_text(amount):
    text = format(amount, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def base_price_updates(product, unit_price, multipliers):
    updates = []
    for variant in (product.get("variants") or {}).get("nodes") or []:
        variant_id = variant["id"]
        if variant.get("compareAtPrice") not in {None, ""}:
            raise ValueError(
                f"{variant_id} 存在 Compare-at price，区域定价脚本不会静默覆盖促销"
            )
        if variant_id not in multipliers:
            raise ValueError(f"变体缺少倍数: {variant_id}")
        wanted = unit_price * multipliers[variant_id]
        current = Decimal(str(variant.get("price") or "0"))
        if current != wanted:
            updates.append({"id": variant_id, "price": _decimal_text(wanted)})
    return updates


def expected_prices(pricing_rows, variants, multipliers):
    plan = {}
    for market_key, row in pricing_rows.items():
        unit_price = row["unit_price"]
        plan[market_key] = {}
        for variant in variants:
            variant_id = variant["id"]
            if variant_id not in multipliers:
                raise ValueError(f"变体缺少倍数: {variant_id}")
            plan[market_key][variant_id] = unit_price * multipliers[variant_id]
    return plan


def catalog_price_lists(market_nodes, catalog_config):
    active_catalogs = {}
    unique_catalogs = {}
    for market in market_nodes:
        if market.get("status") != "ACTIVE":
            continue
        for catalog in (market.get("catalogs") or {}).get("nodes") or []:
            if catalog.get("status") != "ACTIVE" or not catalog.get("id"):
                continue
            active_catalogs[catalog["id"]] = catalog
            price_list = catalog.get("priceList") or {}
            if not price_list.get("id"):
                continue
            unique_catalogs[catalog["id"]] = catalog
    configured_ids = {
        item.get("catalog_id") for item in catalog_config.values() if item.get("catalog_id")
    }
    if len(configured_ids) != len(catalog_config):
        raise ValueError("每个区域定价键必须绑定唯一的 catalog_id")
    unknown_ids = sorted(set(active_catalogs) - configured_ids)
    if unknown_ids:
        labels = [
            f"{active_catalogs[catalog_id].get('title')} ({catalog_id})"
            for catalog_id in unknown_ids
        ]
        raise ValueError("存在未纳入区域定价配置的 ACTIVE Catalog: " + ", ".join(labels))
    result = {}
    for market_key, wanted in catalog_config.items():
        catalog_id = wanted.get("catalog_id")
        price_list_id = wanted.get("price_list_id")
        if not catalog_id or not price_list_id:
            raise ValueError(f"{market_key} 必须固定 catalog_id 与 price_list_id")
        catalog = unique_catalogs.get(catalog_id)
        if not catalog:
            raise ValueError(f"{market_key} 配置的 ACTIVE Catalog 不存在: {catalog_id}")
        actual_price_list = catalog.get("priceList") or {}
        if catalog.get("title") != wanted.get("catalog_title"):
            raise ValueError(
                f"{market_key} Catalog 标题漂移: {catalog.get('title')} != {wanted.get('catalog_title')}"
            )
        if actual_price_list.get("id") != price_list_id:
            raise ValueError(
                f"{market_key} PriceList 漂移: {actual_price_list.get('id')} != {price_list_id}"
            )
        if actual_price_list.get("currency") != wanted.get("currency"):
            raise ValueError(
                f"{market_key} PriceList 币种漂移: "
                f"{actual_price_list.get('currency')} != {wanted.get('currency')}"
            )
        result[market_key] = {
            "catalog_id": catalog["id"],
            "price_list_id": actual_price_list["id"],
            "currency": actual_price_list["currency"],
        }
    return result


def pricing_actions(expected, actual, market_modes, market_currencies):
    actions = {"add": {}, "delete": {}}
    for market_key, variants in expected.items():
        mode = market_modes.get(market_key)
        currency = market_currencies.get(market_key)
        if mode not in {"BASE", "FIXED"}:
            raise ValueError(f"{market_key} 的定价模式必须是 BASE 或 FIXED")
        for variant_id, wanted in variants.items():
            snapshot = (actual.get(market_key) or {}).get(variant_id)
            if snapshot and snapshot.get("compare_at") is not None:
                raise ValueError(
                    f"{market_key}/{variant_id} 存在 Compare-at price，停止覆盖"
                )
            if mode == "BASE":
                if not snapshot:
                    raise ValueError(
                        f"BASE {market_key}/{variant_id} 缺少 PriceList 快照；"
                        "可能尚未加入该区域 Catalog，停止后续写入"
                    )
                if snapshot and snapshot.get("origin") == "FIXED":
                    actions["delete"].setdefault(market_key, []).append(variant_id)
                continue
            is_exact = bool(snapshot) and (
                snapshot.get("amount") == wanted
                and snapshot.get("currency") == currency
                and snapshot.get("origin") == "FIXED"
            )
            if not is_exact:
                actions["add"].setdefault(market_key, []).append(
                    {"variant_id": variant_id, "amount": wanted, "currency": currency}
                )
    return actions


def _amount(snapshot):
    return snapshot.get("amount") if isinstance(snapshot, dict) else snapshot


def price_mismatches(
    expected,
    actual,
    reference,
    target_multipliers,
    market_modes=None,
    market_currencies=None,
    check_reference=True,
):
    errors = []
    market_modes = market_modes or {}
    market_currencies = market_currencies or {}
    for market_key, variants in expected.items():
        for variant_id, wanted in variants.items():
            got = (actual.get(market_key) or {}).get(variant_id)
            got_amount = _amount(got)
            if got_amount != wanted:
                errors.append(f"{market_key}/{variant_id}: target={got_amount} expected={wanted}")
            elif isinstance(got, dict) and market_key in market_modes:
                expected_origin = "RELATIVE" if market_modes[market_key] == "BASE" else "FIXED"
                if got.get("currency") != market_currencies.get(market_key):
                    errors.append(
                        f"{market_key}/{variant_id}: target currency={got.get('currency')} "
                        f"expected={market_currencies.get(market_key)}"
                    )
                elif got.get("origin") != expected_origin:
                    errors.append(
                        f"{market_key}/{variant_id}: target origin={got.get('origin')} "
                        f"expected={expected_origin}"
                    )
                elif got.get("compare_at") is not None:
                    errors.append(
                        f"{market_key}/{variant_id}: target Compare-at={got.get('compare_at')} expected=None"
                    )
        if check_reference:
            expected_by_multiplier = {
                target_multipliers[variant_id]: wanted for variant_id, wanted in variants.items()
            }
            for multiplier, wanted in expected_by_multiplier.items():
                got = (reference.get(market_key) or {}).get(multiplier)
                got_amount = _amount(got)
                if got_amount != wanted:
                    errors.append(f"{market_key}/x{multiplier}: reference={got_amount} expected={wanted}")
                elif isinstance(got, dict) and market_key in market_modes:
                    expected_origin = "RELATIVE" if market_modes[market_key] == "BASE" else "FIXED"
                    if got.get("currency") != market_currencies.get(market_key):
                        errors.append(
                            f"{market_key}/x{multiplier}: reference currency={got.get('currency')} "
                            f"expected={market_currencies.get(market_key)}"
                        )
                    elif got.get("origin") != expected_origin:
                        errors.append(
                            f"{market_key}/x{multiplier}: reference origin={got.get('origin')} "
                            f"expected={expected_origin}"
                        )
                    elif got.get("compare_at") is not None:
                        errors.append(
                            f"{market_key}/x{multiplier}: reference Compare-at={got.get('compare_at')} expected=None"
                        )
    return errors


def product_multipliers(product, overrides=None):
    result = {}
    used = {}
    variants = (product.get("variants") or {}).get("nodes") or []
    if not variants:
        raise ValueError(f"商品没有可定价变体: {product.get('id')}")
    for variant in variants:
        multiplier = variant_multiplier(variant, overrides)
        if multiplier in used:
            raise ValueError(
                f"商品存在两个 x{multiplier} 变体，无法与同档参考品唯一对齐: "
                f"{used[multiplier]} / {variant.get('id')}"
            )
        result[variant["id"]] = multiplier
        used[multiplier] = variant["id"]
    return result


def snapshots_by_multiplier(snapshots, multipliers):
    converted = {}
    for market_key, variants in snapshots.items():
        converted[market_key] = {}
        for variant_id, snapshot in variants.items():
            if variant_id not in multipliers:
                continue
            multiplier = multipliers[variant_id]
            if multiplier in converted[market_key]:
                raise ValueError(f"{market_key} 的 x{multiplier} 参考价格不唯一")
            converted[market_key][multiplier] = snapshot
    return converted


def validate_catalog_membership(product, price_lists, role):
    publications = product.get("resourcePublicationsV2") or {}
    if (publications.get("pageInfo") or {}).get("hasNextPage"):
        raise ValueError(f"{role} Catalog membership 超过 100 条，读取不完整")
    present = {
        (((node.get("publication") or {}).get("catalog") or {}).get("id"))
        for node in publications.get("nodes") or []
    }
    missing = [
        market_key
        for market_key, mapping in price_lists.items()
        if mapping["catalog_id"] not in present
    ]
    if missing:
        raise ValueError(f"{role} Catalog membership 缺失: {', '.join(sorted(missing))}")


def validate_base_snapshots(product, snapshots, modes, currencies):
    base_amounts = {
        variant["id"]: Decimal(str(variant.get("price") or "0"))
        for variant in (product.get("variants") or {}).get("nodes") or []
    }
    for market_key, mode in modes.items():
        if mode != "BASE":
            continue
        for variant_id, base_amount in base_amounts.items():
            snapshot = (snapshots.get(market_key) or {}).get(variant_id)
            if not snapshot:
                raise ValueError(f"BASE {market_key}/{variant_id} 缺少 PriceList 快照")
            if snapshot.get("compare_at") is not None:
                raise ValueError(f"BASE {market_key}/{variant_id} 存在 Compare-at price")
            origin = snapshot.get("origin")
            if origin == "FIXED":
                continue  # pricing_actions 会删除该固定价并恢复继承。
            if origin != "RELATIVE":
                raise ValueError(
                    f"BASE {market_key}/{variant_id} origin={origin}，预期 RELATIVE 或待删除的 FIXED"
                )
            if (
                snapshot.get("currency") != currencies[market_key]
                or snapshot.get("amount") != base_amount
            ):
                raise ValueError(
                    f"BASE {market_key}/{variant_id} 未继承商品当前基础价: "
                    f"snapshot={snapshot.get('amount')} {snapshot.get('currency')}, "
                    f"base={base_amount} {currencies[market_key]}"
                )


def _product_pricing_state(product):
    return {
        "status": product.get("status"),
        "variants": [
            {
                "id": variant.get("id"),
                "title": variant.get("title"),
                "sku": variant.get("sku"),
                "price": str(variant.get("price")),
                "compareAtPrice": (
                    None
                    if variant.get("compareAtPrice") in {None, ""}
                    else str(variant.get("compareAtPrice"))
                ),
            }
            for variant in (product.get("variants") or {}).get("nodes") or []
        ],
    }


def _pricing_contract(config, tier, rows):
    pricing = config.get("pricing") or {}
    source = pricing.get("source") or {}
    tier_fields = source.get("tier_fields") or {}
    tier_field = tier_fields.get(tier)
    if not tier_field:
        raise ValueError(f"config.pricing.source.tier_fields 缺少 {tier}")
    catalogs = pricing.get("market_catalogs") or {}
    if not catalogs:
        raise ValueError("config.pricing.market_catalogs 未配置")
    unsupported = set(pricing.get("unsupported_market_keys") or [])
    price_sources = {
        market_key: item.get("price_source_key") or market_key
        for market_key, item in catalogs.items()
    }
    configured_sources = set(price_sources.values())
    table_keys = set(rows)
    missing = sorted((configured_sources | unsupported) - table_keys)
    unknown = sorted(table_keys - configured_sources - unsupported)
    if missing:
        raise ValueError(f"飞书价格表缺少配置市场: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"飞书价格表出现未配置市场: {', '.join(unknown)}")
    modes = {}
    currencies = {}
    for market_key, item in catalogs.items():
        mode = str(item.get("mode") or "").upper()
        currency = str(item.get("currency") or "").upper()
        if mode not in {"BASE", "FIXED"}:
            raise ValueError(f"{market_key} 的 mode 必须是 BASE 或 FIXED")
        if market_key.rsplit("-", 1)[-1] != currency:
            raise ValueError(f"{market_key} 与配置币种 {currency} 不一致")
        source_key = price_sources[market_key]
        if source_key not in rows:
            raise ValueError(f"{market_key} 的 price_source_key 不存在: {source_key}")
        if source_key.rsplit("-", 1)[-1] != currency:
            raise ValueError(f"{market_key} 与金额来源 {source_key} 的币种不一致")
        modes[market_key] = mode
        currencies[market_key] = currency
    base_keys = [key for key, mode in modes.items() if mode == "BASE"]
    if set(base_keys) != {"US-USD", "GLOBAL-USD"}:
        raise ValueError("US-USD 与 GLOBAL-USD 必须且只能配置为 BASE 继承价")
    if any(price_sources[key] != "US-USD" for key in base_keys):
        raise ValueError("US-USD 与 GLOBAL-USD 都必须复用飞书 US-USD 单价")
    return (
        pricing,
        source,
        tier_field,
        catalogs,
        modes,
        currencies,
        price_sources,
        sorted(unsupported),
    )


def _reference_errors(expected, reference_snapshots, target_multipliers, modes, currencies):
    # price_mismatches 同时检查 target/reference；用 expected 自身占位，只留下 reference 检查。
    return price_mismatches(
        expected,
        expected,
        reference_snapshots,
        target_multipliers,
        market_modes=modes,
        market_currencies=currencies,
    )


def _action_count(base_updates, actions):
    return (
        len(base_updates)
        + sum(len(values) for values in actions["delete"].values())
        + sum(len(values) for values in actions["add"].values())
    )


def _emit_plan(emit, tier, target, reference, base_updates, actions, unsupported, apply):
    emit(f"区域定价 {'APPLY' if apply else 'DRY-RUN'} · 档位 {tier}")
    emit(f"目标: {target.get('title')} ({target.get('id')}) · {target.get('status')}")
    emit(f"参考: {reference.get('title')} ({reference.get('id')}) · {reference.get('status')}")
    emit(f"基础 USD 待改变体: {len(base_updates)}")
    for market_key, variant_ids in sorted(actions["delete"].items()):
        emit(f"恢复继承 {market_key}: {len(variant_ids)} 个变体")
    for market_key, prices in sorted(actions["add"].items()):
        values = ", ".join(
            f"{item['variant_id'].rsplit('/', 1)[-1]}={_decimal_text(item['amount'])} {item['currency']}"
            for item in prices
        )
        emit(f"写固定价 {market_key}: {values}")
    if unsupported:
        emit(f"无对应 Catalog，跳过且不自动创建: {', '.join(unsupported)}")
    if _action_count(base_updates, actions) == 0:
        emit("计划为 0 次写入：目标商品已与飞书矩阵及标准配置一致")


def _rollback_journal(backend, journal):
    errors = []
    for entry in reversed(journal):
        try:
            if entry["kind"] == "base":
                backend.update_base_prices(entry["product_id"], entry["before"])
                continue
            restore_fixed = []
            restore_inherited = []
            for variant_id, snapshot in entry["before"].items():
                if snapshot and snapshot.get("origin") == "FIXED":
                    restore_fixed.append(
                        {
                            "variantId": variant_id,
                            "price": {
                                "amount": _decimal_text(snapshot["amount"]),
                                "currencyCode": snapshot["currency"],
                            },
                        }
                    )
                else:
                    restore_inherited.append(variant_id)
            if restore_fixed:
                backend.add_fixed_prices(entry["price_list_id"], restore_fixed)
            if restore_inherited:
                backend.delete_fixed_prices(entry["price_list_id"], restore_inherited)
        except Exception as exc:  # rollback 必须尽量继续恢复其他已写批次
            errors.append(f"{entry['kind']}: {exc}")
    if errors:
        raise RuntimeError("ROLLBACK_FAILED: " + " | ".join(errors))


def execute_pricing(
    config,
    product_id,
    tier,
    apply,
    backend,
    reference_product_id=None,
    override_values=None,
    allow_reference_packaging_mismatch=False,
    emit=print,
):
    tier = normalize_tier(tier)
    preliminary_pricing = config.get("pricing") or {}
    source = preliminary_pricing.get("source") or {}
    tier_field = (source.get("tier_fields") or {}).get(tier)
    if not tier_field:
        raise ValueError(f"config.pricing.source.tier_fields 缺少 {tier}")
    reference_product_id = reference_product_id or (
        preliminary_pricing.get("reference_products") or {}
    ).get(tier)
    if not reference_product_id:
        raise ValueError(
            f"{tier} 没有已登记的同档参考商品；请传 --reference-product-id，不能只凭价格猜档"
        )

    first_payload = backend.read_pricing_table(source, tier_field)
    rows = pricing_rows_for_tier(first_payload, tier_field)
    (
        pricing,
        source,
        tier_field,
        catalog_config,
        modes,
        currencies,
        price_sources,
        unsupported,
    ) = _pricing_contract(config, tier, rows)

    target = backend.get_product(product_id)
    reference = backend.get_product(reference_product_id)
    validate_product_role(target, "target")
    validate_product_role(reference, "reference")
    overrides = parse_multiplier_overrides(override_values)
    target_multipliers = product_multipliers(target, overrides)
    reference_multipliers = product_multipliers(reference, overrides)
    packaging_mismatch = (
        sorted(target_multipliers.values()) != sorted(reference_multipliers.values())
    )
    if packaging_mismatch and not allow_reference_packaging_mismatch:
        raise ValueError(
            "目标与同档参考商品的包装倍数不一致: "
            f"target={sorted(target_multipliers.values())}, "
            f"reference={sorted(reference_multipliers.values())}"
        )

    supported_rows = {
        market_key: rows[source_key] for market_key, source_key in price_sources.items()
    }
    target_variants = (target.get("variants") or {}).get("nodes") or []
    reference_variants = (reference.get("variants") or {}).get("nodes") or []
    expected = expected_prices(supported_rows, target_variants, target_multipliers)
    reference_expected = expected_prices(
        supported_rows, reference_variants, reference_multipliers
    )
    base_unit = rows["US-USD"]["unit_price"]
    base_updates = base_price_updates(target, base_unit, target_multipliers)
    reference_base_updates = base_price_updates(reference, base_unit, reference_multipliers)
    if reference_base_updates:
        raise ValueError(
            "REFERENCE_DRIFT: 同档参考商品基础 USD 价与飞书矩阵不一致: "
            + json.dumps(reference_base_updates, ensure_ascii=False)
        )

    price_lists = catalog_price_lists(backend.get_market_nodes(), catalog_config)
    validate_catalog_membership(target, price_lists, "目标商品")
    validate_catalog_membership(reference, price_lists, "同档参考商品")
    target_snapshot = backend.get_price_snapshots(price_lists, target)
    validate_base_snapshots(target, target_snapshot, modes, currencies)
    reference_raw = backend.get_price_snapshots(price_lists, reference)
    reference_snapshot = snapshots_by_multiplier(reference_raw, reference_multipliers)
    reference_errors = _reference_errors(
        reference_expected, reference_snapshot, reference_multipliers, modes, currencies
    )
    if reference_errors:
        raise ValueError("REFERENCE_DRIFT: " + " | ".join(reference_errors))
    actions = pricing_actions(expected, target_snapshot, modes, currencies)
    _emit_plan(
        emit,
        tier,
        target,
        reference,
        base_updates,
        actions,
        unsupported,
        apply,
    )
    planned_writes = _action_count(base_updates, actions)
    if not apply:
        return {
            "mode": "dry-run",
            "tier": tier,
            "writes": 0,
            "planned_writes": planned_writes,
            "idempotent": planned_writes == 0,
            "unsupported_market_keys": unsupported,
        }

    # 写前重读 SSOT、商品拓扑和价格状态。变化时停止，让操作者重新审阅新计划。
    second_rows = pricing_rows_for_tier(
        backend.read_pricing_table(source, tier_field), tier_field
    )
    if second_rows != rows:
        raise ValueError("飞书价格表在写入前发生变化；未执行任何 mutation，请重新 dry-run")
    current_target = backend.get_product(product_id)
    validate_product_role(current_target, "target")
    if _product_pricing_state(current_target) != _product_pricing_state(target):
        raise ValueError("目标商品基础价格或变体状态在写入前发生变化；未执行任何 mutation")
    current_multipliers = product_multipliers(current_target, overrides)
    if current_multipliers != target_multipliers:
        raise ValueError("目标商品变体拓扑在写入前发生变化；未执行任何 mutation")
    current_base_updates = base_price_updates(current_target, base_unit, current_multipliers)
    current_snapshot = backend.get_price_snapshots(price_lists, current_target)
    if current_snapshot != target_snapshot:
        raise ValueError("Shopify 区域价格在写入前发生变化；未执行任何 mutation")
    validate_base_snapshots(current_target, current_snapshot, modes, currencies)
    current_actions = pricing_actions(expected, current_snapshot, modes, currencies)
    if current_base_updates != base_updates or current_actions != actions:
        raise ValueError("Shopify 价格状态在写入前发生变化；未执行任何 mutation，请重新 dry-run")

    current_reference = backend.get_product(reference_product_id)
    validate_product_role(current_reference, "reference")
    validate_catalog_membership(current_target, price_lists, "目标商品")
    validate_catalog_membership(current_reference, price_lists, "同档参考商品")
    current_reference_multipliers = product_multipliers(current_reference, overrides)
    if current_reference_multipliers != reference_multipliers:
        raise ValueError("同档参考商品变体拓扑在写入前发生变化；未执行任何 mutation")
    if base_price_updates(current_reference, base_unit, current_reference_multipliers):
        raise ValueError("REFERENCE_DRIFT: 同档参考商品基础价在写入前发生变化")
    current_price_lists = catalog_price_lists(backend.get_market_nodes(), catalog_config)
    if current_price_lists != price_lists:
        raise ValueError("Shopify Catalog/PriceList 在写入前发生变化；未执行任何 mutation")
    current_reference_snapshot = snapshots_by_multiplier(
        backend.get_price_snapshots(current_price_lists, current_reference),
        current_reference_multipliers,
    )
    current_reference_errors = _reference_errors(
        reference_expected,
        current_reference_snapshot,
        reference_multipliers,
        modes,
        currencies,
    )
    if current_reference_errors:
        raise ValueError("REFERENCE_DRIFT: " + " | ".join(current_reference_errors))

    writes = 0
    journal = []
    try:
        if base_updates:
            current_variants = (current_target.get("variants") or {}).get("nodes") or []
            before_prices = {v["id"]: v["price"] for v in current_variants}
            journal.append(
                {
                    "kind": "base",
                    "product_id": product_id,
                    "before": [
                        {"id": update["id"], "price": before_prices[update["id"]]}
                        for update in base_updates
                    ],
                }
            )
            backend.update_base_prices(product_id, base_updates)
            writes += len(base_updates)
        for market_key, variant_ids in sorted(actions["delete"].items()):
            price_list_id = price_lists[market_key]["price_list_id"]
            journal.append(
                {
                    "kind": "fixed",
                    "price_list_id": price_list_id,
                    "before": {
                        variant_id: deepcopy(current_snapshot[market_key].get(variant_id))
                        for variant_id in variant_ids
                    },
                }
            )
            backend.delete_fixed_prices(price_list_id, variant_ids)
            writes += len(variant_ids)
        for market_key, items in sorted(actions["add"].items()):
            prices = [
                {
                    "variantId": item["variant_id"],
                    "price": {
                        "amount": _decimal_text(item["amount"]),
                        "currencyCode": item["currency"],
                    },
                }
                for item in items
            ]
            price_list_id = price_lists[market_key]["price_list_id"]
            journal.append(
                {
                    "kind": "fixed",
                    "price_list_id": price_list_id,
                    "before": {
                        item["variant_id"]: deepcopy(
                            current_snapshot[market_key].get(item["variant_id"])
                        )
                        for item in items
                    },
                }
            )
            backend.add_fixed_prices(price_list_id, prices)
            writes += len(prices)

        try:
            verified_price_lists = catalog_price_lists(
                backend.get_market_nodes(), catalog_config
            )
        except ValueError as mapping_exc:
            raise ValueError(
                f"Catalog/PriceList 在写入期间发生变化: {mapping_exc}"
            ) from mapping_exc
        if verified_price_lists != price_lists:
            raise ValueError("Catalog/PriceList 在写入期间发生变化")
        verified_target = backend.get_product(product_id)
        validate_product_role(verified_target, "target")
        validate_catalog_membership(verified_target, verified_price_lists, "目标商品")
        verified_multipliers = product_multipliers(verified_target, overrides)
        if verified_multipliers != target_multipliers:
            raise ValueError("写后回读发现目标商品变体拓扑变化")
        verified_snapshot = backend.get_price_snapshots(
            verified_price_lists, verified_target
        )
        verified_reference_product = backend.get_product(reference_product_id)
        validate_product_role(verified_reference_product, "reference")
        validate_catalog_membership(
            verified_reference_product, price_lists, "同档参考商品"
        )
        verified_reference_multipliers = product_multipliers(
            verified_reference_product, overrides
        )
        if verified_reference_multipliers != reference_multipliers:
            raise ValueError("写后回读发现参考商品变体拓扑变化")
        verified_reference = snapshots_by_multiplier(
            backend.get_price_snapshots(
                verified_price_lists, verified_reference_product
            ),
            verified_reference_multipliers,
        )
        mismatches = price_mismatches(
            expected,
            verified_snapshot,
            {},
            verified_multipliers,
            market_modes=modes,
            market_currencies=currencies,
            check_reference=False,
        )
        mismatches.extend(
            _reference_errors(
                reference_expected,
                verified_reference,
                verified_reference_multipliers,
                modes,
                currencies,
            )
        )
        if mismatches:
            raise ValueError("写后回读校验失败: " + " | ".join(mismatches))
        post_base = base_price_updates(verified_target, base_unit, verified_multipliers)
        post_actions = pricing_actions(expected, verified_snapshot, modes, currencies)
        idempotent = not post_base and _action_count([], post_actions) == 0
        if not idempotent:
            raise ValueError("写后再次生成计划仍有 mutation，幂等校验失败")
    except Exception as exc:
        if journal:
            try:
                _rollback_journal(backend, journal)
                rollback_target = backend.get_product(product_id)
                rollback_snapshot = backend.get_price_snapshots(price_lists, rollback_target)
                if (
                    _product_pricing_state(rollback_target)
                    != _product_pricing_state(current_target)
                    or rollback_snapshot != current_snapshot
                ):
                    raise RuntimeError("ROLLBACK_FAILED: 回读状态未恢复到写前快照")
            except Exception as rollback_exc:
                raise RuntimeError(f"区域价格写入失败: {exc}; {rollback_exc}") from exc
            raise RuntimeError(
                f"区域价格写入失败: {exc}; 已回滚本轮 {len(journal)} 个已成功批次"
            ) from exc
        raise
    emit(f"✅ 区域价格已验证；实际写入 {writes} 项，再跑计划为 0；商品仍为 DRAFT")
    return {
        "mode": "apply",
        "tier": tier,
        "writes": writes,
        "planned_writes": planned_writes,
        "idempotent": True,
        "unsupported_market_keys": unsupported,
    }


PRODUCT_QUERY = """
query RegionalPricingProduct($id: ID!) {
  product(id: $id) {
    id
    title
    status
    variants(first: 100) {
      nodes { id title sku price compareAtPrice }
      pageInfo { hasNextPage }
    }
    resourcePublicationsV2(first: 100, catalogType: MARKET, onlyPublished: false) {
      nodes { publication { id catalog { id } } isPublished }
      pageInfo { hasNextPage }
    }
  }
}
"""

MARKETS_QUERY = """
query RegionalPricingCatalogs {
  markets(first: 50) {
    nodes {
      name
      status
      catalogs(first: 20) {
        nodes { id title status priceList { id name currency } }
        pageInfo { hasNextPage }
      }
    }
    pageInfo { hasNextPage }
  }
}
"""

PRICE_LIST_QUERY = """
query RegionalPricingPriceList($id: ID!, $query: String!) {
  priceList(id: $id) {
    id
    name
    currency
    prices(first: 100, query: $query) {
      nodes {
        variant { id title sku }
        price { amount currencyCode }
        compareAtPrice { amount currencyCode }
        originType
      }
      pageInfo { hasNextPage }
    }
  }
}
"""

BASE_UPDATE_MUTATION = """
mutation RegionalPricingBase($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkUpdate(
    productId: $productId
    variants: $variants
    allowPartialUpdates: false
  ) {
    productVariants { id price compareAtPrice }
    userErrors { field message }
  }
}
"""

FIXED_ADD_MUTATION = """
mutation RegionalPricingFixedAdd($priceListId: ID!, $prices: [PriceListPriceInput!]!) {
  priceListFixedPricesAdd(priceListId: $priceListId, prices: $prices) {
    prices {
      variant { id }
      price { amount currencyCode }
      compareAtPrice { amount currencyCode }
      originType
    }
    userErrors { field code message }
  }
}
"""

FIXED_DELETE_MUTATION = """
mutation RegionalPricingFixedDelete($priceListId: ID!, $variantIds: [ID!]!) {
  priceListFixedPricesDelete(priceListId: $priceListId, variantIds: $variantIds) {
    deletedFixedPriceVariantIds
    userErrors { field code message }
  }
}
"""


def _json_from_output(output):
    decoder = json.JSONDecoder()
    for index, character in enumerate(output):
        if character not in "[{":
            continue
        try:
            value, _end = decoder.raw_decode(output[index:])
            return value
        except json.JSONDecodeError:
            continue
    raise RuntimeError("命令没有返回可解析的 JSON")


def _user_errors(payload, operation):
    if not isinstance(payload, dict):
        raise RuntimeError(f"{operation} 响应缺少 payload")
    errors = (payload or {}).get("userErrors") or []
    if errors:
        raise RuntimeError(f"{operation} 失败: " + json.dumps(errors, ensure_ascii=False))
    return payload


def _shopify_data(raw):
    if raw.get("errors"):
        raise RuntimeError("Shopify GraphQL errors: " + json.dumps(raw["errors"], ensure_ascii=False))
    data = raw.get("data", raw)
    if not isinstance(data, dict):
        raise RuntimeError("Shopify GraphQL 响应不是对象")
    return data


class CliBackend:
    def __init__(self, config):
        self.config = config
        self.store = config["shopify_store"]
        self.profile = feishu_profile(config)

    def _shopify(self, query, variables=None, allow_mutations=False):
        with tempfile.TemporaryDirectory(prefix="shopify-regional-pricing-") as directory:
            query_path = Path(directory) / "query.graphql"
            output_path = Path(directory) / "output.json"
            query_path.write_text(query, encoding="utf-8")
            command = [
                "shopify",
                "store",
                "execute",
                "-s",
                self.store,
                "-j",
                "--query-file",
                str(query_path),
                "--output-file",
                str(output_path),
            ]
            if allow_mutations:
                command.append("--allow-mutations")
            if variables is not None:
                variable_path = Path(directory) / "variables.json"
                variable_path.write_text(json.dumps(variables), encoding="utf-8")
                command.extend(["--variable-file", str(variable_path)])
            completed = subprocess.run(command, capture_output=True, text=True)
            if completed.returncode != 0:
                message = (completed.stderr or completed.stdout).strip()
                raise RuntimeError(f"Shopify CLI 失败(exit {completed.returncode}): {message}")
            if not output_path.exists():
                raise RuntimeError("Shopify CLI 未生成 JSON 输出")
            raw = json.loads(output_path.read_text(encoding="utf-8"))
            return _shopify_data(raw)

    def read_pricing_table(self, source, tier_field):
        field_command = [
            "lark-cli",
            "base",
            "+field-list",
            "--base-token",
            source["base_token"],
            "--table-id",
            source["table_id"],
            "--limit",
            "200",
            "--as",
            "user",
        ]
        if self.profile:
            field_command.extend(["--profile", self.profile])
        validate_pricing_fields(self._lark_json(field_command), tier_field)

        command = [
            "lark-cli",
            "base",
            "+record-list",
            "--base-token",
            source["base_token"],
            "--table-id",
            source["table_id"],
            "--limit",
            "200",
            "--format",
            "json",
            "--field-id",
            "市场键",
            "--field-id",
            "币种",
            "--field-id",
            tier_field,
            "--as",
            "user",
        ]
        if source.get("view_id"):
            command.extend(["--view-id", source["view_id"]])
        if self.profile:
            command.extend(["--profile", self.profile])
        return self._lark_json(command)

    @staticmethod
    def _lark_json(command):
        completed = subprocess.run(command, capture_output=True, text=True)
        output = completed.stdout + completed.stderr
        if completed.returncode != 0:
            raise RuntimeError(f"飞书价格表读取失败(exit {completed.returncode}): {output.strip()}")
        return _json_from_output(output)

    def get_product(self, product_id):
        data = self._shopify(PRODUCT_QUERY, {"id": product_id})
        product = data.get("product")
        if not product:
            raise ValueError(f"Shopify 找不到商品: {product_id}")
        if ((product.get("variants") or {}).get("pageInfo") or {}).get("hasNextPage"):
            raise ValueError("商品超过 100 个变体，区域定价脚本停止并转人工处理")
        if (
            ((product.get("resourcePublicationsV2") or {}).get("pageInfo") or {}).get(
                "hasNextPage"
            )
        ):
            raise ValueError("商品 Market Catalog membership 超过 100 条，读取不完整")
        return product

    def get_market_nodes(self):
        data = self._shopify(MARKETS_QUERY)
        markets = data.get("markets") or {}
        if (markets.get("pageInfo") or {}).get("hasNextPage"):
            raise ValueError("Markets 超过 50 个，目录读取不完整")
        for market in markets.get("nodes") or []:
            if (((market.get("catalogs") or {}).get("pageInfo") or {}).get("hasNextPage")):
                raise ValueError(f"Market {market.get('name')} 超过 20 个 Catalog")
        return markets.get("nodes") or []

    def get_price_snapshots(self, price_lists, product):
        product_numeric_id = str(product["id"]).rsplit("/", 1)[-1]
        result = {}
        for market_key, mapping in price_lists.items():
            data = self._shopify(
                PRICE_LIST_QUERY,
                {"id": mapping["price_list_id"], "query": f"product_id:{product_numeric_id}"},
            )
            price_list = data.get("priceList")
            if not price_list:
                raise ValueError(f"PriceList 不存在: {mapping['price_list_id']}")
            if price_list.get("currency") != mapping["currency"]:
                raise ValueError(
                    f"{market_key} PriceList 币种漂移: {price_list.get('currency')} != {mapping['currency']}"
                )
            prices = price_list.get("prices") or {}
            if (prices.get("pageInfo") or {}).get("hasNextPage"):
                raise ValueError(f"{market_key} 商品价格超过 100 个变体，读取不完整")
            result[market_key] = {}
            for node in prices.get("nodes") or []:
                variant = node.get("variant") or {}
                price = node.get("price") or {}
                if not variant.get("id") or price.get("amount") is None:
                    continue
                compare_at = node.get("compareAtPrice")
                result[market_key][variant["id"]] = {
                    "amount": Decimal(str(price["amount"])),
                    "currency": price.get("currencyCode"),
                    "origin": node.get("originType"),
                    "compare_at": (
                        Decimal(str(compare_at["amount"])) if compare_at else None
                    ),
                }
        return result

    def update_base_prices(self, product_id, updates):
        data = self._shopify(
            BASE_UPDATE_MUTATION,
            {"productId": product_id, "variants": updates},
            allow_mutations=True,
        )
        _user_errors(data.get("productVariantsBulkUpdate"), "productVariantsBulkUpdate")

    def delete_fixed_prices(self, price_list_id, variant_ids):
        data = self._shopify(
            FIXED_DELETE_MUTATION,
            {"priceListId": price_list_id, "variantIds": variant_ids},
            allow_mutations=True,
        )
        payload = _user_errors(
            data.get("priceListFixedPricesDelete"), "priceListFixedPricesDelete"
        )
        deleted = set(payload.get("deletedFixedPriceVariantIds") or [])
        if deleted != set(variant_ids):
            raise RuntimeError(
                "priceListFixedPricesDelete 回写数量不符: "
                f"wanted={variant_ids}, deleted={sorted(deleted)}"
            )

    def add_fixed_prices(self, price_list_id, prices):
        data = self._shopify(
            FIXED_ADD_MUTATION,
            {"priceListId": price_list_id, "prices": prices},
            allow_mutations=True,
        )
        payload = _user_errors(data.get("priceListFixedPricesAdd"), "priceListFixedPricesAdd")
        returned = payload.get("prices") or []
        if len(returned) != len(prices):
            raise RuntimeError(
                f"priceListFixedPricesAdd 回写数量不符: wanted={len(prices)}, got={len(returned)}"
            )


@contextmanager
def product_lock(store, product_id):
    safe_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{store}-{product_id}")
    path = Path(tempfile.gettempdir()) / f"shopify-regional-pricing-{safe_key}.lock"
    with path.open("w", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"同一商品已有区域定价任务在运行: {product_id}") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="按飞书价格矩阵配置草稿商品的区域价格，并用同档 Active 商品复核"
    )
    parser.add_argument("--product-id", required=True, help="gid://shopify/Product/...")
    parser.add_argument("--tier", required=True, help="显式价格档位 P01-P07")
    parser.add_argument("--reference-product-id", help="同档 Active 参考商品；默认读 config 映射")
    parser.add_argument(
        "--variant-multiplier",
        action="append",
        default=[],
        metavar="VARIANT_ID=N",
        help="标题/SKU 无法明确包装数量时显式指定，可重复",
    )
    parser.add_argument(
        "--allow-reference-packaging-mismatch",
        action="store_true",
        help="显式允许参考商品端盒数量不同；仍按飞书单盒价分别校验并计算",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="只读生成 mutation plan")
    mode.add_argument("--apply", action="store_true", help="执行差异写入并完整回读验证")
    parser.add_argument(
        "--skill-dir",
        default=str(Path(__file__).resolve().parents[1]),
        help="Shopify skill 根目录",
    )
    args = parser.parse_args(argv)
    config = load_config(args.skill_dir)
    ensure_ready(config)
    backend = CliBackend(config)
    try:
        with product_lock(config["shopify_store"], args.product_id):
            execute_pricing(
                config,
                product_id=args.product_id,
                tier=args.tier,
                apply=args.apply,
                backend=backend,
                reference_product_id=args.reference_product_id,
                override_values=args.variant_multiplier,
                allow_reference_packaging_mismatch=args.allow_reference_packaging_mismatch,
            )
        return 0
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

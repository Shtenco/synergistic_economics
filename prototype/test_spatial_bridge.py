import unittest
from decimal import Decimal

from spatial_bridge import (
    FinancialPostingRef, GeoPoint, PhysicalFlow, SourceEvidence,
    SpatialBridgeError, SpatialEconomicEvent, SpatialEventRegistry,
)


def source():
    return SourceEvidence(
        source_id="osm-eaeu-2026-11", source_name="Regional observation",
        source_version="2026-11", license="ODbL-1.0", evidence_type="observed",
        retrieved_at="2026-11-16T10:00:00Z", attribution_text="Source attribution",
    )


def flow():
    return PhysicalFlow("flow-001", "grain", Decimal("12.5"), "tonne", "cell-a", "cell-b", "2026-Q4")


def event(event_id="evt-001", key="key-001", physical=None, financial=None, location=None):
    return SpatialEconomicEvent(
        event_id=event_id, idempotency_key=key, event_type="shipment.dispatched",
        occurred_at="2026-11-16T12:00:00+05:00", region_id="KZ-39", cell_id="cell-a",
        source=source(), data_classification="aggregate", physical_flow=physical,
        financial_posting=financial, location=location,
    )


class SpatialBridgeTests(unittest.TestCase):
    def test_accepts_valid_physical_flow_event(self):
        item = event(physical=flow(), location=GeoPoint(63.6, 53.2))
        registry = SpatialEventRegistry()
        registry.append(item)
        self.assertEqual(len(registry), 1)
        self.assertEqual(registry.replay()[0].event_id, "evt-001")

    def test_rejects_duplicate_event_id_without_mutation(self):
        registry = SpatialEventRegistry()
        registry.append(event(physical=flow()))
        with self.assertRaises(SpatialBridgeError):
            registry.append(event(event_id="evt-001", key="new-key", physical=flow()))
        self.assertEqual(len(registry), 1)

    def test_rejects_duplicate_idempotency_key_without_mutation(self):
        registry = SpatialEventRegistry()
        registry.append(event(physical=flow()))
        with self.assertRaises(SpatialBridgeError):
            registry.append(event(event_id="evt-002", key="key-001", physical=flow()))
        self.assertEqual(len(registry), 1)

    def test_rejects_invalid_coordinates(self):
        with self.assertRaises(SpatialBridgeError):
            GeoPoint(181, 50)
        with self.assertRaises(SpatialBridgeError):
            GeoPoint(70, float("nan"))

    def test_rejects_invalid_crs(self):
        with self.assertRaises(SpatialBridgeError):
            GeoPoint(70, 50, crs="EPSG:3857")

    def test_rejects_negative_or_non_finite_physical_quantity(self):
        with self.assertRaises(SpatialBridgeError):
            PhysicalFlow("f1", "grain", Decimal("-1"), "tonne", "a", "b")
        with self.assertRaises(SpatialBridgeError):
            PhysicalFlow("f2", "grain", Decimal("NaN"), "tonne", "a", "b")

    def test_requires_at_least_one_flow_or_posting(self):
        with self.assertRaises(SpatialBridgeError):
            event(physical=None, financial=None)

    def test_financial_posting_is_a_separate_reference(self):
        posting = FinancialPostingRef("J-100", "expense:transport", "cash:cell-a", Decimal("250.00"), "sdu", "settled")
        item = event(physical=flow(), financial=posting)
        payload = item.to_dict()
        self.assertEqual(payload["physicalFlow"]["quantity"], "12.5")
        self.assertEqual(payload["physicalFlow"]["unit"], "tonne")
        self.assertEqual(payload["financialPosting"]["amount"], "250.00")
        self.assertEqual(payload["financialPosting"]["currency"], "SDU")
        self.assertNotIn("amount", payload["physicalFlow"])
        self.assertNotIn("quantity", payload["financialPosting"])

    def test_rejects_identical_debit_and_credit_accounts(self):
        with self.assertRaises(SpatialBridgeError):
            FinancialPostingRef("J-101", "cash:a", "cash:a", Decimal("1"), "USD")

    def test_rejects_non_positive_financial_amount(self):
        with self.assertRaises(SpatialBridgeError):
            FinancialPostingRef("J-102", "expense:a", "cash:a", Decimal("0"), "USD")

    def test_source_evidence_requires_version_license_and_timezone(self):
        with self.assertRaises(SpatialBridgeError):
            SourceEvidence("s", "name", "", "ODbL", "observed", "2026-11-16T10:00:00Z")
        with self.assertRaises(SpatialBridgeError):
            SourceEvidence("s", "name", "v1", "ODbL", "observed", "2026-11-16T10:00:00")

    def test_rejects_invalid_confidence(self):
        with self.assertRaises(SpatialBridgeError):
            SourceEvidence("s", "n", "v1", "L", "observed", "2026-11-16T10:00:00Z", confidence=1.1)

    def test_related_event_ids_must_be_unique(self):
        with self.assertRaises(SpatialBridgeError):
            SpatialEconomicEvent(
                event_id="e", idempotency_key="k", event_type="shipment.dispatched",
                occurred_at="2026-11-16T10:00:00Z", region_id="r", cell_id="c",
                source=source(), data_classification="aggregate", physical_flow=flow(),
                related_event_ids=("x", "x"),
            )


if __name__ == "__main__":
    unittest.main()

"""Tests for versioned financial metadata and explicit opening stocks."""
import unittest

from sfc_projection_kernel import SFCIdentity
from sfc_source_contracts import (
    EffectiveDatedSectorRegistry,
    InstrumentTerms,
    InstrumentTermsRegistry,
    OpeningPosition,
    OpeningStockSnapshot,
    SFCSourceContractError,
    SectorMembership,
)


def terms(start=1, end=None, maturity="2028-12-31"):
    return InstrumentTerms(
        instrument_id="LOAN-1",
        instrument_class="LOAN",
        denomination="LCU:0.01",
        currency="LCU",
        valuation_basis="NOMINAL",
        maturity=maturity,
        rate_type="FIXED",
        rate_reference="NONE",
        rate_spread="0",
        reset_frequency="NONE",
        day_count_convention="ACT/365F",
        payment_frequency="MONTHLY",
        principal_repayment="AMORTIZING",
        effective_from_period=start,
        effective_to_period=end,
        nonnegative_gross_position=True,
    )


def sectors():
    return EffectiveDatedSectorRegistry(
        version="sectors-v1",
        allowed_sector_codes=frozenset({"H", "NFC", "CB", "CBank", "GOV", "ROW"}),
        memberships=(
            SectorMembership("household-1", "H", 1, None),
            SectorMembership("bank-1", "CB", 1, None),
            SectorMembership("firm-1", "NFC", 1, 2),
            SectorMembership("firm-1", "H", 3, None),
        ),
    )


def identity(*, holder="household-1", holder_sector="H", issuer="bank-1",
             issuer_sector="CB", maturity="2028-12-31"):
    return SFCIdentity(
        instrument_id="LOAN-1",
        instrument_class="LOAN",
        holder_entity_id=holder,
        holder_sector=holder_sector,
        issuer_entity_id=issuer,
        issuer_sector=issuer_sector,
        currency="LCU",
        maturity=maturity,
        denomination="LCU:0.01",
        valuation_basis="NOMINAL",
    )


class SFCSourceContractTests(unittest.TestCase):
    def test_instrument_terms_are_complete_and_explicit(self):
        with self.assertRaises(TypeError):
            InstrumentTerms(instrument_id="LOAN-1")

    def test_instrument_registry_resolves_period_specific_terms(self):
        registry = InstrumentTermsRegistry("terms-v1", (terms(1, 2), terms(3, None, "2029-12-31")))
        self.assertEqual(registry.resolve("LOAN-1", 2).maturity, "2028-12-31")
        self.assertEqual(registry.resolve("LOAN-1", 3).maturity, "2029-12-31")
        with self.assertRaises(SFCSourceContractError):
            registry.resolve("LOAN-1", 4 + 10**6)

    def test_instrument_terms_reject_overlapping_effective_periods(self):
        with self.assertRaises(SFCSourceContractError):
            InstrumentTermsRegistry("terms-v1", (terms(1, 4), terms(4, None)))

    def test_sector_registry_preserves_effective_dated_reclassification(self):
        registry = sectors()
        self.assertEqual(registry.resolve("firm-1", 2), "NFC")
        self.assertEqual(registry.resolve("firm-1", 3), "H")
        changed = EffectiveDatedSectorRegistry(
            version="sectors-v2",
            allowed_sector_codes=registry.allowed_sector_codes,
            memberships=registry.memberships,
        )
        self.assertNotEqual(registry.digest, changed.digest)

    def test_sector_registry_rejects_overlapping_or_unknown_membership(self):
        with self.assertRaises(SFCSourceContractError):
            EffectiveDatedSectorRegistry(
                "bad", frozenset({"H", "CB"}),
                (SectorMembership("x", "H", 1, 3), SectorMembership("x", "CB", 3, None)),
            )
        with self.assertRaises(SFCSourceContractError):
            EffectiveDatedSectorRegistry(
                "bad", frozenset({"H"}),
                (SectorMembership("x", "NFC", 1, None),),
            )

    def test_opening_snapshot_requires_every_declared_position_even_when_zero(self):
        ident = identity()
        registry = InstrumentTermsRegistry("terms-v1", (terms(),))
        sector_registry = sectors()
        with self.assertRaises(SFCSourceContractError):
            OpeningStockSnapshot(
                "open-v1", 2, registry.version, registry.digest,
                sector_registry.version, sector_registry.digest,
                (ident,), (),
            )
        snapshot = OpeningStockSnapshot(
            "open-v1", 2, registry.version, registry.digest,
            sector_registry.version, sector_registry.digest,
            (ident,), (OpeningPosition(ident, "0.00", "ZERO-CERT-1", "BANK-STATEMENT-1"),),
        )
        snapshot.validate_against(registry, sector_registry)
        self.assertEqual(snapshot.as_projection_openings()[(ident, 2)], "0")

    def test_opening_snapshot_pins_registry_versions_and_digests(self):
        ident = identity()
        registry = InstrumentTermsRegistry("terms-v1", (terms(),))
        sector_registry = sectors()
        snapshot = OpeningStockSnapshot(
            "open-v1", 2, registry.version, registry.digest,
            sector_registry.version, sector_registry.digest,
            (ident,), (OpeningPosition(ident, "25.00", "BANK-CERT-1", "BANK-STATEMENT-1"),),
        )
        altered = InstrumentTermsRegistry("terms-v2", (terms(maturity="2030-12-31"),))
        with self.assertRaises(SFCSourceContractError):
            snapshot.validate_against(altered, sector_registry)

    def test_opening_identity_must_match_instrument_and_sector_registries(self):
        registry = InstrumentTermsRegistry("terms-v1", (terms(),))
        sector_registry = sectors()
        bad_identity = identity(holder_sector="NFC")
        snapshot = OpeningStockSnapshot(
            "open-v1", 2, registry.version, registry.digest,
            sector_registry.version, sector_registry.digest,
            (bad_identity,),
            (OpeningPosition(bad_identity, "10", "CERT", "SOURCE"),),
        )
        with self.assertRaises(SFCSourceContractError):
            snapshot.validate_against(registry, sector_registry)

    def test_nonnegative_instrument_terms_reject_negative_opening_stock(self):
        ident = identity()
        registry = InstrumentTermsRegistry("terms-v1", (terms(),))
        sector_registry = sectors()
        snapshot = OpeningStockSnapshot(
            "open-v1", 2, registry.version, registry.digest,
            sector_registry.version, sector_registry.digest,
            (ident,), (OpeningPosition(ident, "-1", "CERT", "SOURCE"),),
        )
        with self.assertRaises(SFCSourceContractError):
            snapshot.validate_against(registry, sector_registry)

    def test_opening_balance_rejects_float_nan_and_implicit_evidence(self):
        ident = identity()
        with self.assertRaises(SFCSourceContractError):
            OpeningPosition(ident, 0.0, "CERT", "SOURCE")
        with self.assertRaises(SFCSourceContractError):
            OpeningPosition(ident, "NaN", "CERT", "SOURCE")
        with self.assertRaises(SFCSourceContractError):
            OpeningPosition(ident, "0", "", "SOURCE")


if __name__ == "__main__":
    unittest.main(verbosity=2)

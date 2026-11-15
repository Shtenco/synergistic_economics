import unittest

from institutional_sectors import (
    ALLOWED_SECTOR_CODES,
    SECTOR_CENTRAL_BANK,
    SECTOR_COMMERCIAL_BANKS,
    SECTOR_GOVERNMENT,
    SECTOR_HOUSEHOLDS,
    SECTOR_NONFINANCIAL_CORPORATIONS,
    SECTOR_REST_OF_WORLD,
)


class InstitutionalSectorCodeTests(unittest.TestCase):
    def test_codes_match_the_canonical_six_sector_sfc_documents(self):
        self.assertEqual(SECTOR_HOUSEHOLDS, "H")
        self.assertEqual(SECTOR_NONFINANCIAL_CORPORATIONS, "NFC")
        self.assertEqual(SECTOR_COMMERCIAL_BANKS, "CB")
        self.assertEqual(SECTOR_CENTRAL_BANK, "CBank")
        self.assertEqual(SECTOR_GOVERNMENT, "GOV")
        self.assertEqual(SECTOR_REST_OF_WORLD, "ROW")

    def test_allowed_codes_are_exactly_the_six_canonical_sectors(self):
        self.assertEqual(
            ALLOWED_SECTOR_CODES,
            frozenset({"H", "NFC", "CB", "CBank", "GOV", "ROW"}),
        )

    def test_commercial_bank_and_central_bank_codes_are_not_interchangeable(self):
        self.assertNotEqual(SECTOR_COMMERCIAL_BANKS, SECTOR_CENTRAL_BANK)
        self.assertNotEqual(
            {"commercial_bank": SECTOR_COMMERCIAL_BANKS,
             "central_bank": SECTOR_CENTRAL_BANK}["commercial_bank"],
            {"commercial_bank": SECTOR_COMMERCIAL_BANKS,
             "central_bank": SECTOR_CENTRAL_BANK}["central_bank"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

import unittest

from care_service_queue import CareQueueError, CareServiceQueue


class CareServiceQueueTests(unittest.TestCase):
    def test_fifo_serves_oldest_lots_first(self):
        queue = CareServiceQueue(capacity=5.0, max_age_periods=4, retention=1.0)
        queue.advance_and_add(1.0, period=1)
        queue.advance_and_add(2.0, period=2)
        served = queue.serve_fifo(1.5)
        self.assertAlmostEqual(served, 1.5)
        self.assertAlmostEqual(queue.total_quantity, 1.5)
        distribution = queue.age_distribution()
        self.assertAlmostEqual(distribution.get(0, 0.0), 1.5)
        self.assertNotIn(1, distribution)

    def test_lots_expire_after_their_last_service_opportunity(self):
        queue = CareServiceQueue(capacity=3.0, max_age_periods=2, retention=1.0)
        queue.advance_and_add(1.0, period=1)
        first = queue.advance_and_add(0.0, period=2)
        self.assertAlmostEqual(first["expired"], 0.0)
        self.assertAlmostEqual(queue.total_quantity, 1.0)
        second = queue.advance_and_add(0.0, period=3)
        self.assertAlmostEqual(second["expired"], 1.0)
        self.assertAlmostEqual(queue.total_quantity, 0.0)

    def test_retention_attrition_and_capacity_overflow_are_explicit(self):
        capped = CareServiceQueue(capacity=1.0, max_age_periods=3, retention=1.0)
        first = capped.advance_and_add(2.0, period=1)
        self.assertAlmostEqual(first["accepted_new"], 1.0)
        self.assertAlmostEqual(first["overflow"], 1.0)
        self.assertAlmostEqual(first["attrited"], 0.0)
        self.assertAlmostEqual(capped.overflow_quantity, 1.0)

        decaying = CareServiceQueue(capacity=3.0, max_age_periods=3, retention=0.5)
        admission = decaying.advance_and_add(1.0, period=1)
        self.assertAlmostEqual(admission["accepted_new"], 0.5)
        self.assertAlmostEqual(admission["attrited"], 0.5)
        next_period = decaying.advance_and_add(0.0, period=2)
        self.assertAlmostEqual(next_period["attrited"], 0.25)
        self.assertAlmostEqual(decaying.total_quantity, 0.25)
        self.assertAlmostEqual(decaying.attrited_quantity, 0.75)

    def test_zero_retention_is_a_true_no_queue_control(self):
        queue = CareServiceQueue(capacity=2.0, max_age_periods=3, retention=0.0)
        result = queue.advance_and_add(1.5, period=1)
        self.assertAlmostEqual(result["accepted_new"], 0.0)
        self.assertAlmostEqual(result["attrited"], 1.5)
        self.assertAlmostEqual(queue.total_quantity, 0.0)

    def test_invalid_queue_parameters_and_service_are_rejected(self):
        with self.assertRaises(CareQueueError):
            CareServiceQueue(capacity=-1)
        with self.assertRaises(CareQueueError):
            CareServiceQueue(capacity=1, max_age_periods=0)
        with self.assertRaises(CareQueueError):
            CareServiceQueue(capacity=1, retention=1.1)
        queue = CareServiceQueue(capacity=1)
        with self.assertRaises(CareQueueError):
            queue.serve_fifo(-1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

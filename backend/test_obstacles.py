import unittest
from obstacles import describe_obstacles

class ObstacleTests(unittest.TestCase):
    def test_observed_chair_is_described_without_walking_instruction(self):
        text = describe_obstacles([{'kind':'chair','position':'center'}])
        self.assertIn('chair', text)
        self.assertIn('center', text)
        self.assertIn('Clearance is unverified', text)
        self.assertNotIn('keep walking', text)
        self.assertNotIn('turn right', text)

    def test_model_cannot_inject_a_movement_command_as_an_object(self):
        self.assertIsNone(describe_obstacles([{'kind':'turn right and walk','position':'center'}]))
        self.assertIsNone(describe_obstacles([{'kind':'chair','position':'take one step down'}]))
        self.assertIsNone(describe_obstacles([]))

if __name__ == '__main__': unittest.main()

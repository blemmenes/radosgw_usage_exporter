import unittest
from radosgw_usage_exporter import get_bucket_namespace

class TestGetBucketNamespace(unittest.TestCase):
    def test_namespace_extraction_from_data(self):
        # Test case based on provided Prometheus metrics data

        # First metric: namespace should be "alpha-beta"
        bucket_name_1 = "foo-bar-baz-qux-12345678-1234-5678-1234-567812345678"
        bucket_owner_1 = "obc-alpha-beta-foo-bar-baz-qux-abcdef12-3456-7890-abcd-ef1234567890"
        expected_namespace_1 = "alpha-beta"
        self.assertEqual(get_bucket_namespace(bucket_name_1, bucket_owner_1, "bucket-"), expected_namespace_1)

        # Second metric: namespace should be "gamma-delta"
        bucket_name_2 = "lorem-ipsum-dolor-sit-98765432-4321-8765-4321-876543218765"
        bucket_owner_2 = "obc-gamma-delta-bucket-lorem-ipsum-dolor-sit-1234abcd-5678-efgh-1234-abcd5678efgh"
        expected_namespace_2 = "gamma-delta"
        self.assertEqual(get_bucket_namespace(bucket_name_2, bucket_owner_2, "bucket-"), expected_namespace_2)

        # Third metric: fuzzy match to extract namespace "omega-theta"
        bucket_name_3 = "theta-omega-phi-psi"
        bucket_owner_3 = "obc-omega-theta-phi-psi-abcdefab-cdef-abcd-efab-cdefabcdefab"
        expected_namespace_3 = "omega-theta"
        self.assertEqual(get_bucket_namespace(bucket_name_3, bucket_owner_3, "bucket-"), expected_namespace_3)

if __name__ == '__main__':
    unittest.main()


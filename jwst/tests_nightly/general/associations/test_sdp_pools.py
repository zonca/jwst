"""Test using SDP-generated pools
"""
from collections import Counter
from pathlib import Path
import pytest
import re

from jwst.associations.lib.diff import (
    compare_asn_files,
)
from jwst.tests.base_classes import BaseJWSTTest

from jwst.associations.main import Main as asn_generate

# Main test args
TEST_ARGS = ['--dry-run', '--no-merge']

# Decompose pool name to retrieve proposal and version id.
pool_regex = re.compile(r'(?P<proposal>jw.+?)_(?P<versionid>.+)_pool')


# #############################################################
# Setup a base class and instantiate it in order to provide the
# file lists for the test parametrization.
# #############################################################
class AssociationBase(BaseJWSTTest):
    input_loc = 'associations'
    test_dir = 'sdp'
    ref_loc = [test_dir, 'truth']

    _pool_paths = None
    _truth_paths = None

    @property
    def pool_paths(self):
        if self._pool_paths is None:
            self._pool_paths = self.data_glob(self.test_dir, 'pools', glob='*.csv')
        return self._pool_paths

    @property
    def truth_paths(self):
        if self._truth_paths is None:
            self._truth_paths = self.data_glob(*self.ref_loc, glob='*.json')
        return self._truth_paths

asn_base = AssociationBase()
try:
    POOL_PATHS = asn_base.pool_paths
except Exception:
    POOL_PATHS = ['test will be skipped']


# #####
# Tests
# #####
class TestSDPPools(AssociationBase):
    @pytest.mark.parametrize(
        'pool_path',
        POOL_PATHS
    )
    def test_against_standard(self, pool_path):
        """Compare a generated association against a standard

        Success is when no other AssertionError occurs.
        """

        # Parse pool name
        pool = Path(pool_path).stem
        proposal, version_id = pool_regex.match(pool).group('proposal', 'versionid')

        # Create the associations
        generated_path = Path('generate')
        generated_path.mkdir()
        asn_generate([
            '--no-merge',
            '-p', str(generated_path),
            '--version-id', version_id,
            self.get_data(pool_path)
        ])

        # Retrieve the truth files
        asn_regex = re.compile(
            r'.+{proposal}.+{version_id}(_[^_]+?_[^_]+?_asn\.json)$'.format(
                proposal=proposal, version_id=version_id
            ),
            flags=re.IGNORECASE
        )
        truth_paths = [
            self.get_data(truth_path)
            for truth_path in asn_base.truth_paths
            if asn_regex.match(truth_path)
        ]

        # Compare the association sets.
        try:
            compare_asn_files(generated_path.glob('*.json'), truth_paths)
        except AssertionError as error:
            if 'Associations do not share a common set of products' in str(error):
                pytest.xfail('Issue #3039')
            else:
                raise

    @pytest.mark.parametrize(
        'pool_path',
        POOL_PATHS
    )
    def test_dup_product_names(self, pool_path):
        """Check for duplicate product names for a pool"""

        results = asn_generate([
            '--dry-run',
            '--no-merge',
            self.get_data(pool_path)
        ])
        asns = results.associations

        product_names = Counter(
            product['name']
            for asn in asns
            for product in asn['products']
        )

        multiples = [
            product_name
            for product_name, count in product_names.items()
            if count > 1
        ]

        assert not len(multiples), 'Multiple product names: {}'.format(multiples)

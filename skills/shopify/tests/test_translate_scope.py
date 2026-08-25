import os
import sys
import unittest


SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import translate  # noqa: E402


class TranslationScopeTests(unittest.TestCase):
    def test_resource_scope_matches_only_the_requested_product(self):
        wanted = "gid://shopify/Product/9638177177855"

        self.assertTrue(translate.resource_selected(wanted, wanted))
        self.assertFalse(
            translate.resource_selected("gid://shopify/Product/1", wanted)
        )
        self.assertTrue(translate.resource_selected("gid://shopify/Product/1", None))


if __name__ == "__main__":
    unittest.main()

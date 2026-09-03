"""Tests du marketing social.

Aucun appel reseau n'est effectue : les chemins « non configure » echouent
avant toute requete HTTP, et le chemin nominal est intercepte a la frontiere
`_publish_on`. Un test qui contacterait Mastodon serait non deterministe.
"""
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestSenodooSocial(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Account = cls.env['senodoo.social.account']
        cls.Post = cls.env['senodoo.social.post']
        cls.mastodon = cls.Account.create({
            'name': "Mastodon Senodoo", 'platform': 'mastodon',
            'base_url': "https://mastodon.example", 'access_token': "jeton-test",
        })
        cls.linkedin = cls.Account.create({'name': "LinkedIn", 'platform': 'linkedin'})

    def test_01_configuration_is_reported_precisely(self):
        self.assertTrue(self.mastodon.is_configured)
        self.assertFalse(self.linkedin.publishing_supported)
        self.assertIn("LinkedIn", self.linkedin._missing_configuration())

        sans_jeton = self.Account.create({
            'name': "Sans jeton", 'platform': 'mastodon',
            'base_url': "https://mastodon.example",
        })
        self.assertFalse(sans_jeton.is_configured)
        self.assertIn("jeton", sans_jeton._missing_configuration())

    def test_02_character_limit_blocks_before_sending(self):
        post = self.Post.create({
            'message': "x" * 300, 'account_ids': [(6, 0, [self.mastodon.id])],
        })
        self.assertFalse(post.over_limit_warning, "300 < 500 : Mastodon accepte")
        post.account_ids = [(6, 0, [self.Account.create(
            {'name': "X", 'platform': 'x'}).id])]
        self.assertIn("280", post.over_limit_warning)
        with self.assertRaises(UserError):
            post.action_publish_now()

    def test_03_unconfigured_account_fails_loudly(self):
        """Jamais de faux succes : un compte non configure marque un echec."""
        post = self.Post.create({
            'message': "Bonjour", 'account_ids': [(6, 0, [self.linkedin.id])],
        })
        post.action_publish_now()
        self.assertEqual(post.state, 'failed')
        self.assertEqual(post.failed_count, 1)
        self.assertEqual(post.posted_count, 0)
        self.assertIn("LinkedIn", post.error_message)
        self.assertEqual(post.line_ids.state, 'failed')
        self.assertFalse(post.line_ids.published_url)

    def test_04_one_network_failing_does_not_block_the_others(self):
        post = self.Post.create({
            'message': "Annonce",
            'account_ids': [(6, 0, [self.mastodon.id, self.linkedin.id])],
        })
        real = type(post)._publish_on

        def _selective(self_post, account):
            if account.platform == 'mastodon':
                return "https://mastodon.example/@senodoo/1"
            return real(self_post, account)

        with patch.object(type(post), '_publish_on', _selective):
            post.action_publish_now()

        self.assertEqual(post.posted_count, 1, "Mastodon devait partir")
        self.assertEqual(post.failed_count, 1, "LinkedIn devait echouer")
        self.assertEqual(post.state, 'failed', "l'etat global reflete l'echec partiel")
        posted = post.line_ids.filtered(lambda line: line.state == 'posted')
        self.assertEqual(posted.published_url, "https://mastodon.example/@senodoo/1")

    def test_05_publishing_twice_does_not_duplicate(self):
        post = self.Post.create({
            'message': "Une seule fois", 'account_ids': [(6, 0, [self.mastodon.id])],
        })
        with patch.object(type(post), '_publish_on', return_value="https://url/1") as mocked:
            post.action_publish_now()
            post.action_publish_now()
        self.assertEqual(mocked.call_count, 1, "une ligne deja publiee ne repart pas")
        self.assertEqual(post.state, 'posted')

    def test_06_schedule_requires_a_date(self):
        post = self.Post.create({
            'message': "Plus tard", 'account_ids': [(6, 0, [self.mastodon.id])],
        })
        with self.assertRaises(UserError):
            post.action_schedule()
        post.scheduled_date = "2020-01-01 08:00:00"
        post.action_schedule()
        self.assertEqual(post.state, 'scheduled')

    def test_07_cron_picks_due_posts_only(self):
        due = self.Post.create({
            'message': "Due", 'account_ids': [(6, 0, [self.mastodon.id])],
            'scheduled_date': "2020-01-01 08:00:00", 'state': 'scheduled',
        })
        later = self.Post.create({
            'message': "Plus tard", 'account_ids': [(6, 0, [self.mastodon.id])],
            'scheduled_date': "2999-01-01 08:00:00", 'state': 'scheduled',
        })
        published = []
        with patch.object(type(due), '_publish_on',
                          side_effect=lambda a: published.append(a) or "https://url/1"):
            self.Post._cron_publish_scheduled()
        self.assertEqual(due.state, 'posted')
        self.assertEqual(later.state, 'scheduled', "une publication future ne doit pas partir")

    def test_08_empty_target_is_refused(self):
        post = self.Post.create({
            'message': "Sans cible", 'account_ids': [(6, 0, [self.mastodon.id])],
        })
        post.account_ids = [(5, 0, 0)]
        with self.assertRaises(UserError):
            post.action_publish_now()

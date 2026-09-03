"""Tests de la base de connaissances."""
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, new_test_user


class TestSenodooKnowledge(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Article = cls.env['senodoo.knowledge.article']
        cls.alice = new_test_user(cls.env, login='k_alice', groups='base.group_user')
        cls.bob = new_test_user(cls.env, login='k_bob', groups='base.group_user')

    def test_01_hierarchy_and_path(self):
        root = self.Article.create({'name': "Manuel"})
        child = self.Article.create({'name': "Congés", 'parent_id': root.id})
        leaf = self.Article.create({'name': "Poser un congé", 'parent_id': child.id})
        self.assertEqual(leaf.full_path, "Manuel / Congés / Poser un congé")
        self.assertEqual(root.child_count, 1)
        self.assertEqual(leaf.parent_id.parent_id, root)

    def test_02_recursion_is_rejected(self):
        root = self.Article.create({'name': "A"})
        child = self.Article.create({'name': "B", 'parent_id': root.id})
        # Odoo detecte la boucle dans _parent_store avant ma contrainte et
        # leve UserError ; ma contrainte leve ValidationError, qui en herite.
        # assertRaises d'Odoo n'accepte pas de tuple (common.py:520 appelle
        # issubclass sur l'argument), donc on vise la classe parente.
        with self.assertRaises(UserError):
            root.parent_id = child
            # L'affectation n'ecrit qu'en cache : sans flush, la contrainte
            # se declencherait apres le bloc et l'exception s'echapperait.
            root.flush_recordset()

    def test_03_favorite_is_per_user(self):
        article = self.Article.create({'name': "Partagé"})
        article.with_user(self.alice).action_toggle_favorite()
        self.assertTrue(article.with_user(self.alice).is_favorite)
        self.assertFalse(article.with_user(self.bob).is_favorite,
                         "un favori ne doit pas fuiter d'un utilisateur a l'autre")
        found = self.Article.with_user(self.alice).search([('is_favorite', '=', True)])
        self.assertIn(article, found, "le filtre « mes favoris » doit retrouver l'article")

    def test_04_private_article_is_hidden_server_side(self):
        """Le partage est une regle d'enregistrement, pas un masquage d'interface."""
        private = self.Article.with_user(self.alice).create({
            'name': "Notes privées", 'internal_permission': 'none',
        })
        self.assertNotIn(private, self.Article.with_user(self.bob).search([]))
        with self.assertRaises(AccessError):
            private.with_user(self.bob).read(['name'])

    def test_05_read_only_article_cannot_be_edited(self):
        article = self.Article.with_user(self.alice).create({
            'name': "Procédure", 'internal_permission': 'read',
        })
        self.assertEqual(article.with_user(self.bob).name, "Procédure")
        with self.assertRaises(AccessError):
            article.with_user(self.bob).write({'name': "Détourné"})

    def test_06_search_covers_the_body(self):
        self.Article.create({'name': "Sans rapport", 'body': "<p>procédure de remboursement</p>"})
        found = self.Article.search(['|', ('name', 'ilike', 'remboursement'),
                                     ('body', 'ilike', 'remboursement')])
        self.assertEqual(len(found), 1, "la recherche doit porter sur le contenu")

    def test_07_archive_takes_the_whole_subtree(self):
        root = self.Article.create({'name': "Racine"})
        child = self.Article.create({'name': "Enfant", 'parent_id': root.id})
        root.action_archive_tree()
        self.assertFalse(root.active)
        self.assertFalse(child.active, "aucun sous-article ne doit rester orphelin visible")

    def test_08_child_creation_opens_the_child(self):
        root = self.Article.create({'name': "Racine"})
        action = root.action_create_child()
        child = self.Article.browse(action['res_id'])
        self.assertEqual(child.parent_id, root)
        self.assertEqual(action['view_mode'], 'form')

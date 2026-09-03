"""Tests de la gestion documentaire."""
import base64

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase, new_test_user

# En-tete PDF reel : `ir.attachment` deduit le type MIME du CONTENU, pas
# de l'extension. Un test avec du texte nomme « .pdf » testerait le
# contraire de ce qui se passe en production.
PDF = base64.b64encode(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n")
TEXTE = base64.b64encode(b"contrat de prestation, 12 pages")


class TestSenodooDocuments(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Folder = cls.env['senodoo.document.folder']
        cls.Document = cls.env['senodoo.document']
        cls.public = cls.Folder.create({'name': "Public"})
        cls.rh_group = cls.env['res.groups'].create({'name': "RH Senodoo"})
        cls.private = cls.Folder.create({
            'name': "RH", 'group_ids': [(6, 0, [cls.rh_group.id])],
        })
        cls.alice = new_test_user(cls.env, login='d_alice',
                                  groups='senodoo_documents.group_documents_user')
        cls.bob = new_test_user(cls.env, login='d_bob',
                                groups='senodoo_documents.group_documents_user')

    def test_01_file_metadata_is_computed(self):
        doc = self.Document.create({
            'name': "Contrat", 'folder_id': self.public.id,
            'datas': PDF, 'file_name': "contrat.pdf",
        })
        self.assertEqual(doc.extension, 'pdf')
        self.assertGreater(doc.file_size, 0, "la taille doit venir de l'attachement")
        self.assertEqual(doc.mimetype, 'application/pdf')
        self.assertIn("o", doc.file_size_human)

    def test_01b_mimetype_comes_from_content_not_from_the_name(self):
        """Renommer un fichier ne doit pas changer le type declare.

        C'est une propriete de securite : un executable renomme en « .pdf »
        ne doit pas etre annonce comme un PDF.
        """
        doc = self.Document.create({
            'name': "Faux PDF", 'folder_id': self.public.id,
            'datas': TEXTE, 'file_name': "deguise.pdf",
        })
        self.assertEqual(doc.extension, 'pdf', "l'extension reste celle du nom")
        self.assertEqual(doc.mimetype, 'text/plain',
                         "le type MIME doit venir du contenu reel")

    def test_02_storage_uses_ir_attachment(self):
        """Le binaire suit le filestore, pas un stockage parallele."""
        doc = self.Document.create({
            'name': "Facture", 'folder_id': self.public.id,
            'datas': PDF, 'file_name': "facture.pdf",
        })
        attachment = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'senodoo.document'),
            ('res_id', '=', doc.id),
            ('res_field', '=', 'datas'),
        ])
        self.assertEqual(len(attachment), 1)
        self.assertEqual(attachment.datas, PDF)

    def test_03_url_document_requires_an_address(self):
        with self.assertRaises(ValidationError):
            self.Document.create({
                'name': "Lien", 'folder_id': self.public.id, 'type': 'url',
            })
        doc = self.Document.create({
            'name': "Lien", 'folder_id': self.public.id, 'type': 'url',
            'url': "https://exemple.test/rapport.pdf",
        })
        self.assertEqual(doc.extension, 'pdf')
        self.assertEqual(doc.action_open_url()['url'], "https://exemple.test/rapport.pdf")

    def test_04_restricted_folder_is_enforced_server_side(self):
        secret = self.Document.create({
            'name': "Salaires", 'folder_id': self.private.id,
            'datas': PDF, 'file_name': "salaires.xlsx",
            'owner_id': self.env.user.id,
        })
        self.assertNotIn(secret, self.Document.with_user(self.alice).search([]))
        with self.assertRaises(AccessError):
            secret.with_user(self.alice).read(['name'])

        self.alice.group_ids = [(4, self.rh_group.id)]
        self.alice.invalidate_recordset()
        self.assertIn(secret, self.Document.with_user(self.alice).search([]),
                      "un membre du groupe doit y acceder")

    def test_05_owner_keeps_access_to_own_document(self):
        mine = self.Document.with_user(self.bob).create({
            'name': "Ma note", 'folder_id': self.private.id,
            'type': 'url', 'url': "https://exemple.test/note",
        })
        self.assertIn(mine, self.Document.with_user(self.bob).search([]),
                      "le proprietaire garde acces meme hors du groupe")

    def test_06_folder_hierarchy_and_recursion(self):
        parent = self.Folder.create({'name': "Comptabilité"})
        child = self.Folder.create({'name': "2026", 'parent_id': parent.id})
        self.assertEqual(child.full_path, "Comptabilité / 2026")
        with self.assertRaises(UserError):
            parent.parent_id = child
            parent.flush_recordset()

    def test_07_opening_a_folder_includes_subfolders(self):
        parent = self.Folder.create({'name': "Ventes"})
        child = self.Folder.create({'name': "Devis", 'parent_id': parent.id})
        doc = self.Document.create({
            'name': "Devis 42", 'folder_id': child.id,
            'type': 'url', 'url': "https://exemple.test/d42",
        })
        action = parent.action_open_documents()
        self.assertEqual(action['domain'], [('folder_id', 'child_of', parent.id)])
        self.assertIn(doc, self.Document.search(action['domain']))

    def test_08_archiving_a_folder_takes_its_documents(self):
        parent = self.Folder.create({'name': "Obsolète"})
        child = self.Folder.create({'name': "2019", 'parent_id': parent.id})
        doc = self.Document.create({
            'name': "Vieux contrat", 'folder_id': child.id,
            'type': 'url', 'url': "https://exemple.test/vieux",
        })
        parent.action_archive_tree()
        for record in (parent, child, doc):
            record.invalidate_recordset()
            self.assertFalse(record.active, f"{record._name} devait etre archive")

    def test_09_tag_in_use_cannot_be_deleted(self):
        tag = self.env['senodoo.document.tag'].create({'name': "Confidentiel"})
        self.Document.create({
            'name': "Note", 'folder_id': self.public.id, 'tag_ids': [(6, 0, [tag.id])],
            'type': 'url', 'url': "https://exemple.test/n",
        })
        with self.assertRaises(UserError):
            tag.unlink()

    def test_10_folder_counts_its_documents(self):
        folder = self.Folder.create({'name': "Compteur"})
        self.assertEqual(folder.document_count, 0)
        for index in range(3):
            self.Document.create({
                'name': f"Doc {index}", 'folder_id': folder.id,
                'type': 'url', 'url': f"https://exemple.test/{index}",
            })
        folder.invalidate_recordset()
        self.assertEqual(folder.document_count, 3)

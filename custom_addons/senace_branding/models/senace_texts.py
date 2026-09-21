"""Reprend les textes de marque qui vivent en base et non dans un template.

Pourquoi du Python et pas des vues heritees :

* les modeles de courriel, les astuces du resume periodique et les libelles de
  champs sont des ENREGISTREMENTS, pas des vues : rien a heriter ;
* leurs champs sont traduisibles, donc stockes en jsonb, une valeur par
  langue. Une ecriture faite dans la langue courante ne touche que celle-la,
  et « Odoo » resterait dans l'autre. Chaque ecriture est donc rejouee pour
  toutes les langues actives ;
* plusieurs cibles appartiennent a des modules que SEN ACE n'installe pas
  forcement (`sale`, `account`, `calendar`). Les declarer en dependance les
  installerait : on verifie leur presence a l'execution a la place.

Tout est rejoue a chaque mise a jour du module, ce qui est voulu : une mise a
jour d'`account` ou de `calendar` reecrirait ses propres donnees.
"""
import logging
import re

from odoo import api, models

_logger = logging.getLogger(__name__)

MARQUE = "SEN ACE"

# Invitation envoyee a chaque nouvel utilisateur. Le corps d'origine est une
# publicite pour l'editeur (« Never heard of Odoo? It's an all-in-one business
# software loved by 12+ million users », lien vers le tour produit). On le
# remplace entierement plutot que par touches : il n'en resterait rien de
# coherent. Les `t-out` et le bouton d'acceptation sont conserves tels quels.
INVITATION_OBJET = (
    "{{ object.create_uid.name }} vous invite à rejoindre "
    "{{ object.company_id.name }}"
)
INVITATION_CORPS = """<t>
Bonjour <t t-out="object.name or ''">Marc Demo</t>,<br/><br/>
<t t-out="object.create_uid.name or ''">L'équipe</t>, de <t t-out="object.company_id.name or ''">SEN ACE</t>, vous invite à rejoindre son espace de travail.
<div style="margin: 16px 0px 16px 0px;">
    <a t-att-href="object.partner_id._get_signup_url()" t-attf-style="background-color: {{object.company_id.email_secondary_color or '#0a4da3'}}; padding: 8px 16px 8px 16px; text-decoration: none; color: {{object.company_id.email_primary_color or '#FFFFFF'}}; border-radius: 5px; font-size:13px;">
        Accepter l'invitation
    </a>
</div>
<b>  Ce lien reste valable <t t-out="(object.env['ir.config_parameter'].sudo().get_int('auth_signup.signup.validity.hours') or 144)//24"/> jours </b> <br/>
<t t-set="website_url" t-value="object.get_base_url()"/>
Votre adresse d'accès est : <b><a t-att-href="website_url" t-out="website_url or ''">https://senace.sn</a></b><br/>
Votre identifiant de connexion est : <b><a t-attf-href="/web/login?login={{ object.email }}" target="_blank" t-out="object.email or ''">prenom.nom@example.com</a></b><br/><br/>
Bonne découverte !<br/>
--<br/>L'équipe <t t-out="object.company_id.name or ''">SEN ACE</t>
</t>"""

# Reecritures integrales : (xmlid, {champ: valeur}). La meme valeur est posee
# dans toutes les langues -- SEN ACE ne travaille qu'en francais, et cela
# garantit qu'aucune traduction ne reintroduise la marque par la bande.
REECRITURES = [
    ('auth_signup.set_password_email', {
        'subject': INVITATION_OBJET,
        'body_html': INVITATION_CORPS,
    }),
    ('auth_totp_mail.mail_template_totp_invite', {
        'subject': "Activez la double authentification sur votre compte "
                   "{{ object.company_id.name }}",
    }),
]

# Retouches ciblees : (xmlid, champ, [(motif, remplacement)]). Les motifs sont
# des expressions regulieres appliquees a CHAQUE langue, donc ancres sur le mot
# « Odoo » lui-meme, qui ne se traduit pas.
RETOUCHES = [
    # Le lien de visioconference interne, nomme « Odoo Discuss » dans les
    # quatre courriels d'agenda.
    ('calendar.calendar_template_meeting_changedate', 'body_html',
     [(r'Odoo\s+Discuss\w*', "Discussion")]),
    ('calendar.calendar_template_meeting_update', 'body_html',
     [(r'Odoo\s+Discuss\w*', "Discussion")]),
    ('calendar.calendar_template_meeting_invitation', 'body_html',
     [(r'Odoo\s+Discuss\w*', "Discussion")]),
    ('calendar.calendar_template_meeting_reminder', 'body_html',
     [(r'Odoo\s+Discuss\w*', "Discussion")]),
    # Le logo de l'editeur, en en-tete des notifications comptables.
    ('account.mail_template_invoice_subscriber', 'body_html',
     [(r'alt="Odoo"', 'alt="%s"' % MARQUE),
      (r'/web/static/img/logo_inverse_white_206px\.png',
       '/senace_branding/static/src/img/logo.png')]),
    ('account.mail_template_einvoice_notification', 'body_html',
     [(r'alt="Odoo"', 'alt="%s"' % MARQUE),
      (r'/web/static/img/logo_inverse_white_206px\.png',
       '/senace_branding/static/src/img/logo.png')]),
    # Signature de l'editeur en pied d'une alerte de credits.
    ('crm_iap_mine.lead_generation_no_credits', 'body_html',
     [(r'Odoo S\.A\.', MARQUE)]),
]

# Resume periodique envoye par courriel : son objet (« Your Odoo Periodic
# Digest ») et ses astuces. Les enregistrements sont cherches par leur contenu
# plutot qu'enumeres par identifiant : les modules en ajoutent au fil des
# versions, et une liste figee en manquerait a la prochaine montee.
ASTUCES = [
    ('digest.digest', ['name']),
    ('digest.tip', ['name', 'tip_description']),
]

# Libelles de champs visibles dans l'interface.
LIBELLES = [
    ('ir.module.module', 'to_buy', "Module sous licence éditeur"),
    ('payment.provider', 'module_to_buy', "Module sous licence éditeur"),
    ('res.users', 'odoobot_state', "État de l'assistant"),
    ('res.users', 'odoobot_failed', "Échec de l'assistant"),
]


class SenaceTexts(models.AbstractModel):
    _name = 'senace.texts'
    _description = "Textes de marque stockes en base"

    # ------------------------------------------------------------------
    # Outils
    # ------------------------------------------------------------------
    @api.model
    def _langues(self):
        return self.env['res.lang'].sudo().search([]).mapped('code') or ['en_US']

    @api.model
    def _poser(self, enregistrement, champ, valeur):
        """Ecrit la meme valeur dans toutes les langues actives."""
        for langue in self._langues():
            enregistrement.with_context(lang=langue).sudo().write({champ: valeur})

    @api.model
    def _retoucher(self, enregistrement, champ, motifs):
        """Applique des expressions regulieres langue par langue."""
        touche = False
        for langue in self._langues():
            cible = enregistrement.with_context(lang=langue).sudo()
            valeur = cible[champ]
            if not valeur:
                continue
            nouveau = valeur
            for motif, remplacement in motifs:
                nouveau = re.sub(motif, remplacement, nouveau)
            if nouveau != valeur:
                cible.write({champ: nouveau})
                touche = True
        return touche

    # ------------------------------------------------------------------
    # Entree unique, appelee depuis data/branding_data.xml
    # ------------------------------------------------------------------
    @api.model
    def apply_texts(self):
        self._appliquer_courriels()
        self._appliquer_astuces()
        self._appliquer_libelles()
        self._appliquer_modules()
        self._appliquer_aides()
        return True

    @api.model
    def _appliquer_aides(self):
        """Info-bulles des champs et textes d'ecran vide des actions.

        Le second se voit plus qu'on ne croit : c'est le paragraphe affiche
        au milieu d'une liste encore vide (« Odoo vous aide a suivre toutes
        les activites liees a vos contacts »), donc la premiere chose que lit
        un utilisateur qui ouvre une application neuve.

        La table de substitution est celle de `senace.views` : meme marque,
        memes tournures, un seul endroit a maintenir.
        """
        substituer = self.env['senace.views']._substituer
        cibles = [('ir.model.fields', 'help'), ('ir.actions.act_window', 'help')]
        for modele, champ in cibles:
            enrs = self.env[modele].sudo().search([(champ, 'ilike', 'odoo')])
            touches = 0
            for enr in enrs:
                for langue in self._langues():
                    cible = enr.with_context(lang=langue)
                    valeur = cible[champ]
                    if not valeur or 'odoo' not in valeur.lower():
                        continue
                    nouveau = substituer(valeur)
                    if nouveau != valeur:
                        cible.write({champ: nouveau})
                        touches += 1
            if touches:
                _logger.info("senace: %s aides corrigees sur %s", touches, modele)

    @api.model
    def _appliquer_courriels(self):
        for xmlid, valeurs in REECRITURES:
            modele = self.env.ref(xmlid, raise_if_not_found=False)
            if not modele:
                continue
            for champ, valeur in valeurs.items():
                self._poser(modele, champ, valeur)
            _logger.info("senace: courriel %s reecrit", xmlid)

        for xmlid, champ, motifs in RETOUCHES:
            modele = self.env.ref(xmlid, raise_if_not_found=False)
            if modele and self._retoucher(modele, champ, motifs):
                _logger.info("senace: courriel %s retouche", xmlid)

    @api.model
    def _appliquer_astuces(self):
        """Le resume periodique cite l'editeur et son robot par leur nom."""
        motifs = [(r'\bOdooBot\b', "l'assistant"), (r'\bOdoo\b', MARQUE)]
        for modele, champs in ASTUCES:
            if modele not in self.env:
                continue
            champs = [c for c in champs if c in self.env[modele]._fields]
            if not champs:
                continue
            domaine = ['|'] * (len(champs) - 1)
            domaine += [(c, 'ilike', 'odoo') for c in champs]
            for enr in self.env[modele].sudo().search(domaine):
                for champ in champs:
                    self._retoucher(enr, champ, motifs)

    @api.model
    def _appliquer_libelles(self):
        """Renomme les libelles de champs qui citent l'editeur.

        On ecrit sur ir.model.fields plutot que de redefinir le champ dans un
        modele herite : `to_buy` et `odoobot_state` appartiennent a des modules
        du coeur, et une redefinition imposerait d'en dependre.
        """
        Champs = self.env['ir.model.fields'].sudo()
        for modele, nom, libelle in LIBELLES:
            champ = Champs.search([('model', '=', modele), ('name', '=', nom)], limit=1)
            if champ:
                self._poser(champ, 'field_description', libelle)

    @api.model
    def _appliquer_modules(self):
        """Nom et resume des modules tels qu'ils s'affichent dans Applications."""
        motifs = [(r'\bOdooBot\b', "Assistant %s" % MARQUE), (r'\bOdoo\b', MARQUE)]
        modules = self.env['ir.module.module'].sudo().search([
            '|', ('shortdesc', 'ilike', 'odoo'), ('summary', 'ilike', 'odoo'),
        ])
        for module in modules:
            for champ in ('shortdesc', 'summary'):
                self._retoucher(module, champ, motifs)
        if modules:
            _logger.info("senace: %s fiches de module retouchees", len(modules))

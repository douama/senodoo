"""Reprend les textes de marque qui restent dans des vues du coeur.

Pourquoi une ecriture directe plutot qu'une heritance de vue, alors que c'est
la bonne pratique et ce que fait le reste du module :

* les chaines visees sont des morceaux de TEXTE au milieu d'un paragraphe, ou
  des valeurs d'attribut. L'heritance QWeb sait remplacer un noeud entier ou
  un attribut, pas une phrase dans un noeud : il faudrait recopier des blocs
  entiers de vues du coeur, qui divergeraient a la premiere montee de version ;
* elles appartiennent a une quinzaine de modules (`sale`, `account`,
  `calendar`, `payment`, `iap`, `product`...) que SEN ACE n'installe pas
  forcement. Les declarer en dependance les installerait.

La contrepartie est assumee : une mise a jour du module proprietaire
reecrirait sa vue. Le bloc est donc rejoue a chaque mise a jour de
senace_branding, et l'entrypoint met a jour les modules maison a chaque
deploiement.

Trois garde-fous :
  1. on ne touche qu'aux vues qui contiennent reellement le motif ;
  2. chaque arch est reparse apres substitution ; une vue qui ne serait plus
     du XML valide est laissee intacte et signalee ;
  3. l'ecriture est rejouee pour chaque langue active, car `arch_db` est
     traduisible -- une correction faite en anglais laisserait la marque dans
     la version francaise.
"""
import logging
import re

from lxml import etree

from odoo import api, models

_logger = logging.getLogger(__name__)

MARQUE = "SEN ACE"
BOT = "%s Bot" % MARQUE
SITE = "https://senace.sn"

# Libelles a reprendre : celui de l'editeur, et celui que ce module posait
# avant que le robot ne s'appelle « SEN ACE Bot ».
RECHERCHES = ('odoo', 'Assistant SEN ACE')

# (motif, remplacement). L'ordre compte : les formulations precises passent
# avant les generiques. Les espaces sont souples (\s+) parce que ces chaines
# sont reparties sur plusieurs lignes dans les vues d'origine.
REMPLACEMENTS = [
    # --- Accroches commerciales de l'editeur -------------------------------
    # Un simple « Odoo » -> « SEN ACE » produirait une affirmation fausse
    # (« 50 000 entreprises utilisent SEN ACE ») : ces phrases sont reecrites.
    (r'50,000\+\s*companies\s+run\s+Odoo\s+to\s+grow\s+their\s+businesses\.',
     "Faites grandir votre activité avec %s." % MARQUE),
    (r'50,000\+\s*companies\s+run\s+Odoo\.?', "Faites grandir votre activité."),
    (r'50,000\+\s*companies\s+trust\s+Odoo\.?', "Ils nous font confiance."),
    (r'Never\s+heard\s+of\s+Odoo\?', "Vous ne nous connaissez pas encore ?"),

    # --- Noms de produits de l'editeur -------------------------------------
    (r'\bOdoo\s+Studio\b', "l'éditeur de vues"),
    (r'\bOdoo\s+Mobile\b', "l'application mobile"),
    (r'\bOdoo\s+In-App\s+Purchase\b', "Achats intégrés"),
    (r'\bOdoo\s+Enterprise\s+Subscription\b', "Abonnement"),
    (r'\bOdoo\s+Enterprise\b', "édition Entreprise"),
    (r'\bOdoo\s+Discuss\w*', "Discussion"),
    (r'\bOdoo\s+meeting\b', "Réunion"),
    (r'\bOdoo\s+Tour\b', "visite guidée"),
    (r'\bOdoo\s+Logo\b', "Logo %s" % MARQUE),
    (r'\bOdoo\s+Apps\b', "Applications"),
    (r'\bOdoo\s+S\.A\.', MARQUE),
    (r'\bOdooBot\b', BOT),
    # Transition : une version anterieure de ce module posait « Assistant
    # SEN ACE ». Les bases deja deployees le portent, et plus aucune regle
    # ancree sur OdooBot ne les rattraperait.
    (r'Assistant\s+SEN\s+ACE\b', BOT),

    # --- Politique de cookies : « session_id (Odoo) » et ses cinq voisines.
    # La parenthese nommait l'editeur ; le nom technique du cookie reste exact.
    (r'\s*\(Odoo\)', ''),

    # --- Exemples et libelles ----------------------------------------------
    # Adresse d'exemple dans l'aide du champ « domaine de messagerie ». Un
    # remplacement par la marque donnerait « SEN ACE@example.com », qui n'est
    # pas une adresse.
    (r'\bodoo@example\.com\b', "contact@example.com"),
    (r'Bank\s+of\s+odoo', "Banque"),
    (r'Speedscope\s+for\s+odoo', "Speedscope"),
    (r'Invoice\s+generated\s+by\s+Odoo', "Facture générée par %s" % MARQUE),
    (r'e\.g\.\s*https://www\.odoo\.com', "ex. %s" % SITE),
    # Logo de l'editeur incruste au centre du QR code des factures.
    (r'/account/static/src/img/Odoo_logo_O\.svg',
     '/senace_branding/static/src/img/icon-192.png'),

    # --- Liens vers le site de l'editeur -----------------------------------
    # Y compris la documentation : la cible devient le site SEN ACE plutot
    # qu'une page de l'editeur. Contrepartie assumee, signalee au passage :
    # les quelques liens « en savoir plus » du portail et des reglages
    # n'ouvrent plus la documentation d'origine.
    (r'https?://(www\.)?odoo\.com[^\s"\'<>)]*', SITE),
    # Depot public de l'editeur, cite par l'assistant d'export des traductions.
    (r'https?://github\.com/odoo/[^\s"\'<>)]*', SITE),
    # Domaine cite sans schema, dans une phrase : « un serveur de messagerie
    # pret a l'emploi (@mycompany.odoo.com) ». La regle ci-dessus, ancree sur
    # http, ne l'attrape pas, et la garde des identifiants non plus.
    (r'@?(?:[\w-]+\.)*odoo\.com\b', "senace.sn"),

    # --- Reste : mentions isolees dans des phrases d'aide ------------------
    # Passe en dernier, une fois les formulations ci-dessus consommees.
    (r'\bOdoo\b', MARQUE),
    (r'\bodoo\b(?![_.\-/])', MARQUE),
]

COMPILES = [(re.compile(motif), remplacement) for motif, remplacement in REMPLACEMENTS]

# Attributs qu'un humain lit. Tout le reste est laisse tel quel : `t-if`,
# `t-value` et consorts portent du Python, `class` et `id` des identifiants.
ATTRIBUTS = (
    'title', 'alt', 'placeholder', 'help', 'string', 'label', 'confirm',
    'aria-label', 'data-original-title',
    'href', 't-att-href', 't-attf-href', 'src',
    # `documentation` alimente le petit « ? » a cote d'un reglage. Une valeur
    # absolue pointe sur le site de l'editeur ; une valeur relative
    # (/applications/...) est prefixee a l'affichage par l'URL de sa
    # documentation, qu'aucune reecriture d'arch ne peut atteindre.
    'documentation',
)

# Elements dont le contenu est du code, jamais du texte affiche. Les epargner
# n'est pas un detail : `web.layout` declare `var odoo = {` dans un <script>,
# et le renommer casserait le client web entier. Le XML resterait pourtant
# valide, donc aucune validation ne rattraperait la panne.
CODE = {'script', 'style'}

# Vues a ne pas toucher : leur « odoo » est technique, le reecrire casserait
# quelque chose.
#   default_less / default_scss : exemple de code affiche dans l'editeur de
#     site, qui cite la variable SCSS $o-brand-odoo definie par le coeur ;
#   view_speedscope_index : outil de profilage, reserve aux developpeurs.
EPARGNEES = {
    'website.default_less',
    'website.default_scss',
}


class SenaceViews(models.AbstractModel):
    _name = 'senace.views'
    _description = "Textes de marque restant dans les vues du coeur"

    @api.model
    def _langues(self):
        return self.env['res.lang'].sudo().search([]).mapped('code') or ['en_US']

    @api.model
    def _substituer(self, texte):
        for motif, remplacement in COMPILES:
            texte = motif.sub(remplacement, texte)
        return texte

    @api.model
    def _nettoyer(self, arch):
        """Transforme l'arbre plutot que la chaine.

        Une substitution sur le texte brut atteindrait aussi le contenu des
        <script> et les expressions Python des attributs QWeb. On ne touche
        donc qu'aux noeuds de texte affiches et a une liste blanche
        d'attributs lisibles.

        Renvoie None si rien n'a change, pour eviter une ecriture inutile.
        """
        arbre = etree.fromstring(arch)
        touche = False

        # Noeuds dont le contenu est du code : on les saute, eux et leur
        # descendance, mais pas leur `tail`, qui est du texte du parent.
        interdits = set()
        for noeud in arbre.iter():
            if isinstance(noeud.tag, str) and noeud.tag.lower() in CODE:
                interdits.update(id(d) for d in noeud.iter())

        for noeud in arbre.iter():
            if not isinstance(noeud.tag, str):
                continue  # commentaire ou instruction de traitement
            if id(noeud) not in interdits and noeud.text:
                nouveau = self._substituer(noeud.text)
                if nouveau != noeud.text:
                    noeud.text, touche = nouveau, True
            if noeud.tail:
                nouveau = self._substituer(noeud.tail)
                if nouveau != noeud.tail:
                    noeud.tail, touche = nouveau, True
            if id(noeud) in interdits:
                continue
            for attr in ATTRIBUTS:
                valeur = noeud.get(attr)
                if not valeur:
                    continue
                nouveau = self._substituer(valeur)
                if nouveau != valeur:
                    noeud.set(attr, nouveau)
                    touche = True

        if not touche:
            return None
        return etree.tostring(arbre, encoding='unicode')

    @api.model
    def _vues_heritees_maison(self):
        """Vues du coeur qu'une de nos propres vues surcharge deja.

        Elles sont laissees telles quelles pour deux raisons. La sortie rendue
        est deja propre, puisque nos heritances la reecrivent. Et surtout,
        leurs xpath sont ancres sur le contenu d'origine : reecrire l'arch
        sous leurs pieds ferait echouer l'heritage au demarrage suivant, et
        Odoo refuserait alors de charger le registre.
        """
        notres = self.env['ir.ui.view'].sudo().search([
            ('inherit_id', '!=', False),
        ]).filtered(lambda v: (v.xml_id or '').startswith(
            ('senace_branding.', 'senace_website_landing.', 'senodoo_website_landing.')))
        return set(notres.mapped('inherit_id').ids)

    @api.model
    def apply_views(self):
        """Parcourt les vues actives qui citent l'editeur et les corrige."""
        epargnees = {
            self.env.ref(x).id
            for x in EPARGNEES
            if self.env.ref(x, raise_if_not_found=False)
        }
        epargnees |= self._vues_heritees_maison()
        Vues = self.env['ir.ui.view'].sudo()
        # `with_context(active_test=False)` volontairement absent : une vue
        # desactivee n'est pas rendue, donc rien n'en sort.
        # On cherche aussi « Assistant SEN ACE » : une version anterieure de ce
        # module posait ce libelle pour le robot, et les bases deja deployees
        # le portent. Ancre sur le seul mot « odoo », la reprise le manquerait.
        cibles = Vues.search([
            ('active', '=', True),
            '|', ('arch_db', 'ilike', 'odoo'),
            ('arch_db', 'ilike', 'Assistant SEN ACE'),
        ])

        corrigees = invalides = 0
        for vue in cibles:
            if vue.id in epargnees:
                continue
            xmlid = vue.xml_id or ''
            if xmlid.startswith('senace_branding.'):
                continue
            for langue in self._langues():
                cible = vue.with_context(lang=langue, active_test=False)
                arch = cible.arch_db
                if not arch:
                    continue
                minuscules = arch.lower()
                if not any(m.lower() in minuscules for m in RECHERCHES):
                    continue
                try:
                    nouveau = self._nettoyer(arch)
                except etree.XMLSyntaxError as exc:
                    _logger.warning("senace: vue %s illisible, ignoree : %s",
                                    xmlid or vue.id, exc)
                    invalides += 1
                    continue
                if not nouveau:
                    continue
                try:
                    cible.write({'arch_db': nouveau})
                    corrigees += 1
                except Exception as exc:  # noqa: BLE001
                    _logger.warning("senace: vue %s non ecrite : %s",
                                    xmlid or vue.id, exc)
                    invalides += 1

        _logger.info("senace: %s arch de vues corriges, %s ecartes",
                     corrigees, invalides)
        return True

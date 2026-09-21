/**
 * Retire la marque Odoo des deux endroits du client web qui la portent en
 * JavaScript et qu'aucune heritance de vue ne peut atteindre.
 */
import { registry } from "@web/core/registry";
import { titleService } from "@web/core/browser/title_service";

const BRAND = "SEN ACE";

// ---------------------------------------------------------------------------
// 1. Titre de l'onglet
//
// `title_service` retombe sur la chaine « Odoo » des que titleParts est vide :
// a l'amorcage, entre deux actions, et sur l'ecran de deconnexion. La valeur
// est enfermee dans la closure du service, donc inatteignable par un patch de
// prototype. On reenveloppe le service et on repasse derriere lui apres chaque
// ecriture, ce qui evite de recopier son implementation -- qui changerait a la
// prochaine montee de version d'Odoo.
// ---------------------------------------------------------------------------
registry.category("services").add(
    "title",
    {
        ...titleService,
        start(env) {
            const service = titleService.start(env);
            const rebrand = () => {
                if (document.title.includes("Odoo")) {
                    document.title = document.title.replaceAll("Odoo", BRAND);
                }
            };
            rebrand();
            return {
                get current() {
                    return document.title;
                },
                getParts: service.getParts,
                setCounters(counters) {
                    service.setCounters(counters);
                    rebrand();
                },
                setParts(parts) {
                    service.setParts(parts);
                    rebrand();
                },
            };
        },
    },
    { force: true }
);

// ---------------------------------------------------------------------------
// 2. Menu utilisateur (avatar, en haut a droite)
//
//   « My Odoo.com Account » ouvre accounts.odoo.com ;
//   « Help » pointe sur session.support_url, soit odoo.com/buy.
//
// Les deux entrees n'ont aucun sens sur une instance autoheberge : elles sont
// retirees du registre plutot que masquees en CSS, sinon la palette de
// commandes (CTRL+K) continuerait de les proposer.
// ---------------------------------------------------------------------------
const userMenu = registry.category("user_menuitems");
userMenu.remove("odoo_account");
userMenu.remove("support");

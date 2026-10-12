import { registerWebsitePreviewTour } from "@website/js/tours/tour_utils";

const MODAL = ".modal:not(.o_inactive_modal)";

function openEditMenu() {
    return [
        {
            content: "Ouvrir le menu Site",
            trigger: 'button[data-menu-xmlid="website.menu_site"]',
            run: "click",
        },
        {
            content: "Ouvrir « Modifier le menu »",
            trigger: 'a[data-menu-xmlid="website.menu_edit_menu"]',
            run: "click",
        },
        {
            trigger: ".oe_menu_editor",
        },
    ];
}

function saveMenu() {
    return [
        {
            content: "Enregistrer le menu",
            trigger: `${MODAL} .modal-footer .btn-primary`,
            run: "click",
        },
        {
            trigger: "body:not(:has(.oe_menu_editor))",
        },
    ];
}

registerWebsitePreviewTour("senace_menu_parent", { url: "/" }, () => [
    {
        trigger: ":iframe #wrapwrap",
    },
    ...openEditMenu(),
    // Creation : la sous-page est rangee sous son parent depuis la fenetre.
    {
        content: "Ajouter un élément de menu",
        trigger: `${MODAL} .modal-body a:eq(0)`,
        run: "click",
    },
    {
        content: "Saisir le libellé",
        trigger: `${MODAL} .o_menu_dialog_form input`,
        run: "edit Sous-page test",
    },
    {
        content: "Saisir l'URL",
        trigger: `${MODAL} #url_input`,
        run: "edit /#sous-page-test",
    },
    {
        content: "Choisir le menu parent",
        trigger: `${MODAL} #o_senace_menu_parent`,
        run: "selectByLabel Parent test",
    },
    {
        content: "Valider l'élément",
        trigger: `${MODAL} .modal-footer .btn-primary`,
        run: "click",
    },
    {
        content: "L'élément est rangé sous son parent dans l'éditeur",
        trigger:
            ".oe_menu_editor > li:has(> .input-group .js_menu_label:contains(Parent test)) > ul .js_menu_label:contains(Sous-page test)",
    },
    ...saveMenu(),
    {
        content: "Le parent devient une liste déroulante sur le site",
        trigger: ":iframe header a.dropdown-toggle:contains(Parent test)",
    },
    // Modification : la sous-page revient au premier niveau.
    ...openEditMenu(),
    {
        content: "Modifier la sous-page",
        trigger: ".oe_menu_editor li:has(> .input-group .js_menu_label:contains(Sous-page test)) .js_edit_menu",
        run: "click",
    },
    {
        content: "Le parent actuel est présélectionné",
        trigger: `${MODAL} #o_senace_menu_parent:has(option:selected:contains(Parent test))`,
    },
    {
        content: "Remettre au premier niveau",
        trigger: `${MODAL} #o_senace_menu_parent`,
        run: "select root",
    },
    {
        content: "Valider l'élément",
        trigger: `${MODAL} .modal-footer .btn-primary`,
        run: "click",
    },
    {
        content: "La sous-page est revenue au premier niveau",
        trigger: ".oe_menu_editor > li > .input-group .js_menu_label:contains(Sous-page test)",
    },
    ...saveMenu(),
    {
        trigger: ":iframe #wrapwrap",
    },
]);

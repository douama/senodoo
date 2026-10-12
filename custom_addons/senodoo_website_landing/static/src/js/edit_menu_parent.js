// Sous-pages dans le menu principal.
//
// Odoo sait afficher un sous-menu, mais ne permet de le creer qu'en faisant
// glisser une ligne vers la droite dans « Modifier le menu », geste que rien
// ne signale. On ajoute a la fenetre d'un element de menu un choix explicite
// « Sous-menu de », a la creation comme a la modification. Le glisser-deposer
// natif reste disponible, et les regles du coeur sont reprises : un seul
// niveau de sous-menu, jamais sous un mega menu.
import { reactive } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { EditMenuDialog, MenuDialog } from "@website/components/dialog/edit_menu";

patch(MenuDialog, {
    props: {
        ...MenuDialog.props,
        parentChoices: { type: Array, optional: true },
        parentChoice: { type: Object, optional: true },
    },
});

patch(MenuDialog.prototype, {
    onParentChange(ev) {
        const index = ev.target.value;
        this.props.parentChoice.parentId = index === "root" ? false : this.props.parentChoices[index].id;
    },
});

patch(EditMenuDialog.prototype, {
    setup() {
        super.setup();
        // addMenu et editMenu du coeur ouvrent MenuDialog avec des props
        // figees : on les complete au passage plutot que de recopier ces deux
        // methodes, qui peuvent evoluer avec Odoo.
        const dialogs = this.dialogs;
        this.dialogs = {
            ...dialogs,
            add: (Dialog, props, options) =>
                dialogs.add(Dialog, Dialog === MenuDialog ? this._withParentChoice(props) : props, options),
        };
    },

    addMenu(isMegaMenu) {
        this._menuInDialog = null;
        return super.addMenu(isMegaMenu);
    },

    editMenu(id) {
        this._menuInDialog = this.map.get(id);
        return super.editMenu(id);
    },

    _withParentChoice(props) {
        const menu = this._menuInDialog;
        // Un mega menu reste au premier niveau, et un menu qui a deja des
        // sous-menus ne peut pas descendre : il n'y a qu'un niveau.
        if (props.isMegaMenu || menu?.children.length) {
            return props;
        }
        const rootId = this.state.rootMenu.fields.id;
        const parentChoices = this.state.rootMenu.children
            .filter((candidate) => candidate !== menu && !candidate.fields.is_mega_menu)
            .map((candidate) => ({ id: candidate.fields.id, name: candidate.fields.name }));
        const currentParentId = menu?.fields.parent_id;
        const parentChoice = reactive({
            parentId: currentParentId && currentParentId !== rootId ? currentParentId : false,
        });
        return {
            ...props,
            parentChoices,
            parentChoice,
            save: (...args) => {
                props.save(...args);
                // Un nouvel element est ajoute par le coeur en fin de premier niveau.
                const saved = menu || this.state.rootMenu.children.at(-1);
                this._moveMenuUnder(saved, parentChoice.parentId);
            },
        };
    },

    _moveMenuUnder(menu, parentId) {
        const rootId = this.state.rootMenu.fields.id;
        const newParentId = parentId || rootId;
        const oldParentId = menu.fields.parent_id || rootId;
        if (newParentId === oldParentId) {
            return;
        }
        const oldParent = this.map.get(oldParentId);
        oldParent.children = oldParent.children.filter((child) => child.fields.id !== menu.fields.id);
        this.map.get(newParentId).children.push(menu);
        menu.fields.parent_id = newParentId;
    },
});

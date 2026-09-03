"""Tests du moteur de marketing automatise.

Aucun courriel n'est reellement envoye : `_execute` est intercepte a la
frontiere et renvoie une `mailing.trace` fabriquee, ce qui permet de piloter
precisement ouverture, clic et reponse pour eprouver les declencheurs.
"""
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestSenodooMarketingAutomation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Campaign = cls.env['senodoo.marketing.campaign']
        cls.Activity = cls.env['senodoo.marketing.activity']
        cls.Trace = cls.env['senodoo.marketing.trace']
        cls.MailingTrace = cls.env['mailing.trace']

        cls.tag = cls.env['res.partner.category'].create({'name': "Cible test"})
        cls.partners = cls.env['res.partner'].create([
            {'name': "Client A", 'email': "a@exemple.test", 'category_id': [(6, 0, [cls.tag.id])]},
            {'name': "Client B", 'email': "b@exemple.test", 'category_id': [(6, 0, [cls.tag.id])]},
        ])
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.mailing = cls.env['mailing.mailing'].create({
            'subject': "Bonjour",
            'body_html': "<p>Bonjour</p>",
            'mailing_model_id': cls.partner_model.id,
        })
        cls.campaign = cls.Campaign.create({
            'name': "Réactivation",
            'model_id': cls.partner_model.id,
            'domain': f"[('category_id', 'in', [{cls.tag.id}])]",
        })
        cls.first = cls.Activity.create({
            'campaign_id': cls.campaign.id, 'name': "Premier courriel",
            'activity_type': 'email', 'mailing_id': cls.mailing.id,
            'trigger_type': 'begin',
        })

    def _fake_mailing_trace(self, partner, **values):
        return self.MailingTrace.create({
            'mass_mailing_id': self.mailing.id,
            'model': 'res.partner', 'res_id': partner.id, **values,
        })

    def _run_with_fake_send(self, traces_by_partner=None):
        """Traite les traces dues sans envoyer de courriel reel."""
        traces_by_partner = traces_by_partner or {}

        def _execute(trace_self, record):
            return traces_by_partner.get(record.id, self.MailingTrace.browse())

        with patch.object(type(self.Trace), '_execute', _execute):
            return self.Trace._process_due()

    # -- cycle de vie ----------------------------------------------------
    def test_01_campaign_without_activity_cannot_start(self):
        empty = self.Campaign.create({
            'name': "Vide", 'model_id': self.partner_model.id, 'domain': "[]",
        })
        with self.assertRaises(UserError):
            empty.action_start()

    def test_02_invalid_domain_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.Campaign.create({
                'name': "Cassée", 'model_id': self.partner_model.id,
                'domain': "[('champ_inexistant', '=', 1)]",
            })

    def test_03_start_enrolls_targets_and_schedules_begin(self):
        self.campaign.action_start()
        self.assertEqual(self.campaign.participant_count, 2)
        traces = self.Trace.search([('campaign_id', '=', self.campaign.id)])
        self.assertEqual(len(traces), 2, "une trace de depart par participant")
        self.assertTrue(all(t.state == 'scheduled' for t in traces))

    def test_04_sync_only_adds_new_records(self):
        self.campaign.action_start()
        self.assertEqual(self.campaign.participant_count, 2)
        self.campaign.action_sync_participants()
        self.assertEqual(self.campaign.participant_count, 2, "aucun doublon")

        nouveau = self.env['res.partner'].create({
            'name': "Client C", 'email': "c@exemple.test",
            'category_id': [(6, 0, [self.tag.id])],
        })
        self.campaign.action_sync_participants()
        self.campaign.invalidate_recordset()
        self.assertEqual(self.campaign.participant_count, 3)
        self.assertIn(nouveau.id, self.campaign.participant_ids.mapped('res_id'))

    # -- enchainement ----------------------------------------------------
    def test_05_processing_schedules_children(self):
        suite = self.Activity.create({
            'campaign_id': self.campaign.id, 'name': "Relance",
            'activity_type': 'email', 'mailing_id': self.mailing.id,
            'trigger_type': 'activity', 'parent_id': self.first.id,
            'interval_number': 3, 'interval_type': 'days',
        })
        self.campaign.action_start()
        self._run_with_fake_send()

        parents = self.Trace.search([('activity_id', '=', self.first.id)])
        self.assertTrue(all(t.state == 'processed' for t in parents))
        enfants = self.Trace.search([('activity_id', '=', suite.id)])
        self.assertEqual(len(enfants), 2, "une relance planifiee par participant")
        self.assertTrue(all(t.state == 'scheduled' for t in enfants))
        self.assertGreater(enfants[0].schedule_date, fields.Datetime.now())

    def test_06_nothing_runs_twice(self):
        self.campaign.action_start()
        self._run_with_fake_send()
        traite = self.Trace.search_count([('state', '=', 'processed')])
        self._run_with_fake_send()
        self.assertEqual(self.Trace.search_count([('state', '=', 'processed')]), traite,
                         "une trace deja traitee ne doit pas repartir")

    # -- declencheurs comportementaux -------------------------------------
    def _prepare_behaviour(self, trigger):
        child = self.Activity.create({
            'campaign_id': self.campaign.id, 'name': f"Suite {trigger}",
            'activity_type': 'email', 'mailing_id': self.mailing.id,
            'trigger_type': trigger, 'parent_id': self.first.id,
        })
        self.campaign.action_start()
        ouvreur, silencieux = self.partners
        self._run_with_fake_send({
            ouvreur.id: self._fake_mailing_trace(
                ouvreur, trace_status='open', open_datetime=fields.Datetime.now()),
            silencieux.id: self._fake_mailing_trace(silencieux, trace_status='sent'),
        })
        self._run_with_fake_send()
        return child, ouvreur, silencieux

    def _state_for(self, activity, partner):
        trace = self.Trace.search([
            ('activity_id', '=', activity.id),
            ('participant_id.res_id', '=', partner.id),
        ], limit=1)
        return trace.state, trace.state_msg

    def test_07_mail_open_only_follows_openers(self):
        child, ouvreur, silencieux = self._prepare_behaviour('mail_open')
        self.assertEqual(self._state_for(child, ouvreur)[0], 'processed')
        etat, motif = self._state_for(child, silencieux)
        self.assertEqual(etat, 'canceled')
        self.assertIn("pas ete ouvert", motif, "le motif doit etre lisible")

    def test_08_mail_not_open_is_the_exact_mirror(self):
        child, ouvreur, silencieux = self._prepare_behaviour('mail_not_open')
        self.assertEqual(self._state_for(child, silencieux)[0], 'processed')
        self.assertEqual(self._state_for(child, ouvreur)[0], 'canceled')

    def test_09_a_click_implies_an_open(self):
        """Le pixel de suivi peut ne pas charger : un clic prouve la lecture."""
        child = self.Activity.create({
            'campaign_id': self.campaign.id, 'name': "Après ouverture",
            'activity_type': 'email', 'mailing_id': self.mailing.id,
            'trigger_type': 'mail_open', 'parent_id': self.first.id,
        })
        self.campaign.action_start()
        cliqueur = self.partners[0]
        self._run_with_fake_send({
            cliqueur.id: self._fake_mailing_trace(
                cliqueur, trace_status='sent',
                links_click_datetime=fields.Datetime.now()),
        })
        self._run_with_fake_send()
        self.assertEqual(self._state_for(child, cliqueur)[0], 'processed')

    def test_10_missing_parent_mail_cancels_with_a_reason(self):
        child = self.Activity.create({
            'campaign_id': self.campaign.id, 'name': "Suite",
            'activity_type': 'email', 'mailing_id': self.mailing.id,
            'trigger_type': 'mail_open', 'parent_id': self.first.id,
        })
        self.campaign.action_start()
        self._run_with_fake_send()   # aucune mailing.trace produite
        self._run_with_fake_send()
        etat, motif = self._state_for(child, self.partners[0])
        self.assertEqual(etat, 'canceled')
        self.assertIn("n'a pas ete envoye", motif)

    # -- robustesse -------------------------------------------------------
    def test_11_deleted_record_is_rejected_not_crashing(self):
        self.campaign.action_start()
        self.partners[0].unlink()
        self._run_with_fake_send()
        rejete = self.Trace.search([('state', '=', 'rejected')])
        self.assertEqual(len(rejete), 1)
        self.assertIn("n'existe plus", rejete.state_msg)
        self.assertEqual(self.Trace.search_count([('state', '=', 'processed')]), 1,
                         "l'autre participant doit avoir ete traite")

    def test_12_failure_on_one_does_not_stop_the_others(self):
        self.campaign.action_start()
        cible = self.partners[0]

        panne = "serveur SMTP injoignable"

        def _boom(trace_self, record):
            if record.id == cible.id:
                raise ValueError(panne)
            return self.MailingTrace.browse()

        with patch.object(type(self.Trace), '_execute', _boom):
            self.Trace._process_due()
        self.assertEqual(self.Trace.search_count([('state', '=', 'rejected')]), 1)
        self.assertEqual(self.Trace.search_count([('state', '=', 'processed')]), 1)

    def test_13_stopping_cancels_only_what_has_not_left(self):
        self.campaign.action_start()
        self._run_with_fake_send()
        suite = self.Activity.create({
            'campaign_id': self.campaign.id, 'name': "Relance",
            'activity_type': 'email', 'mailing_id': self.mailing.id,
            'trigger_type': 'activity', 'parent_id': self.first.id,
            'interval_number': 5, 'interval_type': 'days',
        })
        self.campaign.participant_ids[0].trace_ids  # force le prefetch
        self.Trace.create({
            'participant_id': self.campaign.participant_ids[0].id,
            'activity_id': suite.id,
            'schedule_date': fields.Datetime.add(fields.Datetime.now(), days=5),
        })
        self.campaign.action_stop()
        self.assertEqual(self.Trace.search_count(
            [('campaign_id', '=', self.campaign.id), ('state', '=', 'scheduled')]), 0)
        self.assertGreater(self.Trace.search_count(
            [('campaign_id', '=', self.campaign.id), ('state', '=', 'processed')]), 0,
            "un envoi deja parti ne peut pas etre annule")

    def test_14_participant_completes_when_nothing_remains(self):
        self.campaign.action_start()
        self._run_with_fake_send()
        self.campaign.participant_ids._refresh_completion()
        self.assertTrue(all(p.state == 'completed' for p in self.campaign.participant_ids))

    # -- garde-fous de configuration --------------------------------------
    def test_15_activity_constraints(self):
        with self.assertRaises(ValidationError):
            self.Activity.create({
                'campaign_id': self.campaign.id, 'name': "Début avec parent",
                'activity_type': 'email', 'mailing_id': self.mailing.id,
                'trigger_type': 'begin', 'parent_id': self.first.id,
            })
        action = self.Activity.create({
            'campaign_id': self.campaign.id, 'name': "Action",
            'activity_type': 'action',
            'server_action_id': self.env['ir.actions.server'].create({
                'name': "Rien", 'model_id': self.partner_model.id,
                'state': 'code', 'code': "pass",
            }).id,
            'trigger_type': 'activity', 'parent_id': self.first.id,
        })
        with self.assertRaises(ValidationError):
            self.Activity.create({
                'campaign_id': self.campaign.id, 'name': "Réaction impossible",
                'activity_type': 'email', 'mailing_id': self.mailing.id,
                'trigger_type': 'mail_open', 'parent_id': action.id,
            })

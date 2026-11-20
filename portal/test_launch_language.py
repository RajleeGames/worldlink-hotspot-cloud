from pathlib import Path
import re
from types import SimpleNamespace

from django.conf import settings
from django.template import Context, Template
from django.test import SimpleTestCase

from portal.words import EN, SW, words_for
from cloud.templatetags.translations import SW as STAFF_SW
from networks.forms import OmadaOnboardingForm


class LaunchTranslationTests(SimpleTestCase):
    def test_checkout_and_payment_status_have_both_languages(self):
        keys = {
            'guest_wifi', 'pay_mobile', 'mobile_title', 'mobile_phone',
            'send_push', 'pin_warning', 'payment_confirmed',
            'payment_verified_pending', 'provider_uncertain', 'keep_reference',
        }
        for key in keys:
            with self.subTest(key=key):
                self.assertTrue(EN.get(key))
                self.assertTrue(SW.get(key))
                self.assertNotEqual(EN[key], SW[key])
                self.assertEqual(words_for('sw')[key], SW[key])

    def test_staff_switch_translates_approval_without_translating_ids(self):
        template = Template('{% load translations %}{% t "Approve site mapping" %} | {{ ap_mac }}')
        content = {'ap_mac': 'B8-FB-B3-79-B5-60'}
        sw = template.render(Context({**content, 'request': SimpleNamespace(session={'ui_lang': 'sw'})}))
        en = template.render(Context({**content, 'request': SimpleNamespace(session={'ui_lang': 'en'})}))
        self.assertIn('Idhinisha uhusishaji wa eneo', sw)
        self.assertIn('Approve site mapping', en)
        self.assertIn(content['ap_mac'], sw)

        public = template.render(Context({**content, 'request': SimpleNamespace(session={'ui_lang': 'en'}),
                                          'public_portal': True, 'lang': 'sw'}))
        self.assertIn('Idhinisha uhusishaji wa eneo', public)

    def test_mobile_input_zoom_rule_preserves_pinch_zoom(self):
        css = (Path(settings.BASE_DIR) / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')
        self.assertIn('font-size:16px!important', css)
        self.assertIn(':where(.app-body,.guest-body)', css)
        self.assertNotIn('user-scalable=no', css)
        self.assertNotIn('maximum-scale=1', css)

    def test_every_literal_staff_translation_has_swahili_text(self):
        # Protect against adding an untranslated {% t 'literal' %} in future PRs.
        pattern = re.compile(r'\{%\s*t\s+([\x27\x22])(.+?)\1\s*%\}')
        missing = []
        for page in (Path(settings.BASE_DIR) / 'templates').rglob('*.html'):
            missing += [(page.name, phrase) for _, phrase in pattern.findall(page.read_text(encoding='utf-8'))
                        if phrase not in STAFF_SW]
        self.assertEqual(missing, [])

    def test_omada_connection_options_follow_owner_language(self):
        en = str(OmadaOnboardingForm(ui_lang='en')['connection_mode'])
        sw = str(OmadaOnboardingForm(ui_lang='sw')['connection_mode'])
        self.assertIn('Connect to WorldLink central Omada (recommended)', en)
        self.assertIn('Unganisha na Omada kuu ya WorldLink', sw)
        self.assertNotIn('Unganisha na Omada kuu ya WorldLink', en)

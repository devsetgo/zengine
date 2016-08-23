# -*-  coding: utf-8 -*-
"""
"""

# Copyright (C) 2016 ZetaOps Inc.
#
# This file is licensed under the GNU General Public License v3
# (GPLv3).  See LICENSE.txt for details.

import pytest
from zengine.lib.test_utils import BaseTestCase
from zengine.models import User


_MSG_TR = 'Bu çevirilebilir bir mesajdır.'
_MSG_EN = 'This is a translateable message.'
_MSG_UNTRANSLATED = 'This message has not been translated.'


class TestCase(BaseTestCase):
    def test_translation(self):
        test_user = User.objects.get(username='super_user')
        # We'll connect with the 'tr' language code to get the translated message
        self.prepare_client('/i18n/', user=test_user)
        resp = self.client.post(lang_code='tr')
        assert resp.json['message'] == _MSG_TR
        # This message was not translated yet, so this message only should fall back to default message
        assert resp.json['untranslated'] == _MSG_UNTRANSLATED

    def test_default(self):
        test_user = User.objects.get(username='super_user')
        # First, let's make the engine switch to a language other than the default
        self.prepare_client('/i18n/', user=test_user)
        resp = self.client.post(lang_code='tr')
        assert resp.json['message'] == _MSG_TR
        # Next, we'll connect without a language code to get the default language
        self.prepare_client('/i18n/', user=test_user)
        resp = self.client.post()
        # Since no language code was given, the engine should switch back to default language
        assert resp.json['message'] == _MSG_EN
        assert resp.json['untranslated'] == _MSG_UNTRANSLATED

    def test_default_with_code(self):
        test_user = User.objects.get(username='super_user')
        # First, let's make the engine switch to a language other than the default
        self.prepare_client('/i18n/', user=test_user)
        resp = self.client.post(lang_code='tr')
        assert resp.json['message'] == _MSG_TR
        # Next, we'll connect specifically with the default language code
        self.prepare_client('/i18n/', user=test_user)
        resp = self.client.post()
        # The engine should have switched to the default language
        assert resp.json['message'] == _MSG_EN
        assert resp.json['untranslated'] == _MSG_UNTRANSLATED

    def test_fallback(self):
        test_user = User.objects.get(username='super_user')
        # We'll connect witha language code that we don't have the translations for
        self.prepare_client('/i18n/', user=test_user)
        resp = self.client.post(lang_code='klingon')
        # The engine should fall back to the default language since the translations are missing
        assert resp.json['message'] == _MSG_EN
        assert resp.json['untranslated'] == _MSG_UNTRANSLATED

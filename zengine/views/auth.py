# -*-  coding: utf-8 -*-
"""Authentication views"""

# Copyright (C) 2015 ZetaOps Inc.
#
# This file is licensed under the GNU General Public License v3
# (GPLv3).  See LICENSE.txt for details.
import falcon

from pyoko import fields
from zengine.forms.json_form import JsonForm
from zengine.views.base import SimpleView


class LoginForm(JsonForm):
    username = fields.String("Username")
    password = fields.String("Password", type="password")


def logout(current):
    current.session.delete()


def dashboard(current):
    current.output["msg"] = "Success"


class Login(SimpleView):
    def do_view(self):
        try:
            auth_result = self.current.auth.authenticate(
                self.current.input['username'],
                self.current.input['password'])
            self.current.task_data['login_successful'] = auth_result
        except:
            self.current.log.exception("Wrong username or another error occurred")
            self.current.task_data['login_successful'] = False
        if not self.current.task_data['login_successful']:
            self.current.response.status = falcon.HTTP_403

    def show_view(self):
        self.current.output['forms'] = LoginForm(current=self.current).serialize()




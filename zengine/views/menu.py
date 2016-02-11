# -*-  coding: utf-8 -*-
"""
This module holds Menu class that builds user
menus according to :attr:`zengine.settings.OBJECT_MENU`
and :attr:`zengine.settings.QUICK_MENUS`

"""

# Copyright (C) 2015 ZetaOps Inc.
#
# This file is licensed under the GNU General Public License v3
# (GPLv3).  See LICENSE.txt for details.
from collections import defaultdict

from pyoko.lib.utils import get_object_from_path
from pyoko.lib.utils import lazy_property
from pyoko.model import model_registry
from zengine.auth.permissions import _get_workflows
from zengine.views.base import BaseView
from zengine.config import settings


class Menu(BaseView):
    """
    Menu view class
    """
    def __init__(self, current):
        super(Menu, self).__init__(current)
        self.output['quick_menu'] = []
        self.output['other'] = []
        if settings.ENABLE_SIMPLE_CRUD_MENU:
            result = self.simple_crud()
        else:
            result = self.get_crud_menus()
        for k, v in self._get_workflow_menus().items():
            result[k].extend(v)
        self.output.update(result)

    def simple_crud(self):
        """
        Prepares menu entries for auto-generated model CRUD views.
        This is simple version of :attr:`get_crud_menus()` without
        Category support and permission control.
        Just for development purposes.

        Returns:
            Dict of list of dicts (``{'':[{}],}``). Menu entries.

        """
        results = defaultdict(list)
        for mdl in model_registry.get_base_models():
            results['other'].append({"text": mdl.Meta.verbose_name_plural,
                                     "wf": 'crud',
                                     "model": mdl.__name__,
                                     "kategori": settings.DEFAULT_OBJECT_CATEGORY_NAME})
        return results

    def get_crud_menus(self):
        """
        Generates menu entries according to
        :attr:`zengine.settings.OBJECT_MENU` and permissions
        of current user.

        Returns:
            Dict of list of dicts (``{'':[{}],}``). Menu entries.
        """
        results = defaultdict(list)
        for object_type in settings.OBJECT_MENU:
            for model_data in settings.OBJECT_MENU[object_type]:
                if self.current.has_permission(model_data['name']):
                    self._add_crud(model_data, object_type, results)
        return results

    def _add_crud(self, model_data, object_type, results):
        """
        Creates a menu entry for given model data.
        Updates results in place.

        Args:
            model_data: Model data.
            object_type: Relation name.
            results: Results dict.
        """
        model = model_registry.get_model(model_data['name'])
        field_name = model_data.get('field')
        verbose_name = model_data.get('verbose_name', model.Meta.verbose_name_plural)
        category = model_data.get('category', settings.DEFAULT_OBJECT_CATEGORY_NAME)
        wf_dict = {"text": verbose_name,
                   "wf": model_data.get('wf', "crud"),
                   "model": model_data['name'],
                   "kategori": category}
        if field_name:
            wf_dict['param'] = field_name
        results[object_type].append(wf_dict)
        self._add_to_quick_menu(wf_dict['model'], wf_dict)

    def _add_to_quick_menu(self, key, wf):
        """
        Appends menu entries to dashboard quickmenu according
        to :attr:`zengine.settings.QUICK_MENU`

        Args:
            key: workflow name
            wf: workflow menu entry
        """
        if key in settings.QUICK_MENU:
            self.output['quick_menu'].append(wf)

    def _get_workflow_menus(self):
        """
        Creates menu entries for custom workflows.

        Returns:
            Dict of list of dicts (``{'':[{}],}``). Menu entries.
        """
        results = defaultdict(list)
        for wf in _get_workflows():
            if self.current.has_permission(wf.spec.name):
                self._add_wf(wf, results)
        return results

    def _add_wf(self, wf, results):
        """
        Creates a menu entry for given model data.
        Updates results in place.

        Args:
            wf: Workflow data
            results: Results dict.
        """
        category = wf.spec.wf_properties.get("menu_category", settings.DEFAULT_WF_CATEGORY_NAME)
        object_of_wf = wf.spec.wf_properties.get('object', 'other')
        if category != 'hidden':
            wf_dict = {
                "text": wf.spec.wf_name,
                "wf": wf.spec.name,
                "kategori": category,
                "param": "id"}
            results[object_of_wf].append(wf_dict)
            self._add_to_quick_menu(wf_dict['wf'], wf_dict)

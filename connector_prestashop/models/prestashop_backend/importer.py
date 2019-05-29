# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from odoo import _
from odoo.addons.component.core import Component
from odoo.addons.connector.components.mapper import mapping
from odoo.addons.connector_prestashop.components.importer import PrestashopImporter


class MetadataBatchImporter(Component):
    """ Import the records directly, without delaying the jobs.

    Import the PrestShop Websites, Shop Groups and Shops

    They are imported directly because this is a rare and fast operation,
    and we don't really bother if it blocks the UI during this time.
    (that's also a mean to rapidly check the connectivity with PrestaShop).

    """

    _name = 'prestashop.metadata.batch.importer'
    _inherit = 'prestashop.direct.batch.importer'
    _apply_on = [
        'prestashop.shop.group',
        'prestashop.shop',
    ]

class ShopGroupImporter(PrestashopImporter):
    _model_name = 'prestashop.shop.group'


class ShopGroupBatchImporter(DirectBatchImporter):
    _model_name = 'prestashop.shop.group'

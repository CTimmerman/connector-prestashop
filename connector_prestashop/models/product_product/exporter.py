# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from odoo.addons.component.core import Component


class CombinationInventoryExporter(Component):
    _name = 'prestashop.product.combination.inventory.exporter'
    _inherit = 'prestashop.product.template.inventory.exporter'
    _apply_on = 'prestashop.product.combination'

    _usage = 'inventory.exporter'

    def get_filter(self, product):
        return {
            'filter[id_product]': product.main_template_id.prestashop_id,
            'filter[id_product_attribute]': product.prestashop_id,
        }

    def get_quantity_vals(self, product):
        res = {
            'quantity': int(product.quantity),
            'out_of_stock': int(product.main_template_id.out_of_stock),
        }

        if not int(product.quantity):
            if int(product.potential_qty):
                res['delivery_out_stock'] = product.main_template_id.delivery_out_stock or ''
            elif not int(product.potential_qty):
                res['delivery_out_stock'] = product.main_template_id.delivery_no_stock or ''

        return res

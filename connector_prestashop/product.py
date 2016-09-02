# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import datetime
import mimetypes
import html2text

from openerp import models

from openerp.addons.connector.queue.job import job
from openerp.addons.connector.event import on_record_write
from openerp.addons.connector.unit.synchronizer import Exporter
from .unit.import_synchronizer import DelayedBatchImport
from .unit.import_synchronizer import PrestashopImportSynchronizer
from .unit.import_synchronizer import import_record
from openerp.addons.connector.unit.mapper import (mapping,
                                                  ImportMapper)
from prestapyt import PrestaShopWebServiceError

from .unit.backend_adapter import GenericAdapter

from .connector import get_environment
from .backend import prestashop

from prestapyt import PrestaShopWebServiceDict

try:
    from xml.etree import cElementTree as ElementTree
except ImportError, e:
    from xml.etree import ElementTree


@prestashop
class ProductCategoryMapper(ImportMapper):
    _model_name = 'prestashop.product.category'

    direct = [
        ('position', 'sequence'),
        ('description', 'description'),
        ('link_rewrite', 'link_rewrite'),
        ('meta_description', 'meta_description'),
        ('meta_keywords', 'meta_keywords'),
        ('meta_title', 'meta_title'),
        ('id_shop_default', 'default_shop_id'),
        ('active', 'active'),
        ('position', 'position')
    ]

    @mapping
    def name(self, record):
        if record['name'] is None:
            return {'name': ''}
        return {'name': record['name']}

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}

    @mapping
    def parent_id(self, record):
        if record['id_parent'] == '0':
            return {}
        return {
            'parent_id':
                self.binder_for('prestashop.product.category').to_openerp(
                    record['id_parent'], unwrap=True)}

    @mapping
    def data_add(self, record):
        if record['date_add'] == '0000-00-00 00:00:00':
            return {'date_add': datetime.datetime.now()}
        return {'date_add': record['date_add']}

    @mapping
    def data_upd(self, record):
        if record['date_upd'] == '0000-00-00 00:00:00':
            return {'date_upd': datetime.datetime.now()}
        return {'date_upd': record['date_upd']}


# Product image connector parts
@prestashop
class ProductImageMapper(ImportMapper):
    _model_name = 'prestashop.product.image'

    direct = [
        # ('content', 'file_db_store'),
    ]

    @mapping
    def owner_id(self, record):
        return {
            'owner_id': self.binder_for(
                'prestashop.product.template').to_openerp(
                record['id_product'], unwrap=True)
        }

    @mapping
    def name(self, record):
        product = self.binder_for('prestashop.product.template').to_openerp(
            record['id_product'], unwrap=True, browse=True)
        return {'name': '%s_%s' % (product.name, record['id_image'])}

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}

    @mapping
    def extension(self, record):
        return {'extension': mimetypes.guess_extension(record['type'])}

    @mapping
    def image_url(self, record):
        url = self.backend_record.location.encode()
        url += '/img/p/' + '/'.join(list(record['id_image']))
        extension = ''
        if record['type'] == 'image/jpeg':
            extension = '.jpg'
        url += '/' + record['id_image'] + extension
        return {'url': url}
        # return {'storage': 'db'}

    @mapping
    def filename(self, record):
        return {'filename': '%s.jpg' % record['id_image']}

    @mapping
    def storage(self, record):
        return {'storage': 'url'}
        # return {'storage': 'db'}

    @mapping
    def owner_model(self, record):
        return {'owner_model': 'product.template'}


@prestashop
class TemplateMapper(ImportMapper):
    _model_name = 'prestashop.product.template'

    direct = [
        ('description', 'description_html'),
        ('description_short', 'description_short_html'),
        ('weight', 'weight'),
        ('wholesale_price', 'standard_price'),
        ('id_shop_default', 'default_shop_id'),
        ('link_rewrite', 'link_rewrite'),
        ('reference', 'reference'),
        ('available_for_order', 'available_for_order'),
        ('on_sale', 'on_sale'),
    ]

    def get_sale_price(self, record, tax):
        price_adapter = self.unit_for(
            GenericAdapter, 'prestashop.product.combination')
        combination = price_adapter.read(
            record['id_default_combination']['value'])
        impact_price = float(combination['price'])
        price = float(record['price'])
        if tax:
            tax = tax[:1]
            return (price / (1 + tax.amount) - impact_price) * (1 + tax.amount)
        price = float(record['price']) - impact_price
        return price

    @mapping
    def list_price(self, record):
        price = 0.0
        tax = self._get_tax_ids(record)
        associations = record.get('associations', {})
        combinations = associations.get('combinations', {}).get(
            'combinations', [])
        if not isinstance(combinations, list):
            combinations = [combinations]
        if combinations:
            price = self.get_sale_price(record, tax)
        else:
            if record['price'] != '':
                price = float(record['price'])
        return {'list_price': price}

    @mapping
    def name(self, record):
        if record['name']:
            return {'name': record['name']}
        return {'name': 'noname'}

    @mapping
    def date_add(self, record):
        if record['date_add'] == '0000-00-00 00:00:00':
            return {'date_add': datetime.datetime.now()}
        return {'date_add': record['date_add']}

    @mapping
    def date_upd(self, record):
        if record['date_upd'] == '0000-00-00 00:00:00':
            return {'date_upd': datetime.datetime.now()}
        return {'date_upd': record['date_upd']}

    def has_combinations(self, record):
        combinations = record.get('associations', {}).get(
            'combinations', {}).get('combinations', [])
        return len(combinations) != 0

    def _template_code_exists(self, code):
        model = self.session.env['product.template']
        template_ids = model.search([
            ('default_code', '=', code),
            ('company_id', '=', self.backend_record.company_id.id),
        ], limit=1)
        return len(template_ids) > 0

    @mapping
    def default_code(self, record):
        if self.has_combinations(record):
            return {}
        code = record.get('reference')
        if not code:
            code = "backend_%d_product_%s" % (
                self.backend_record.id, record['id']
            )
        if not self._template_code_exists(code):
            return {'default_code': code}
        i = 1
        current_code = '%s_%d' % (code, i)
        while self._template_code_exists(current_code):
            i += 1
            current_code = '%s_%d' % (code, i)
        return {'default_code': current_code}

    def clear_html_field(self, content):
        html = html2text.HTML2Text()
        html.ignore_images = True
        html.ignore_links = True
        return html.handle(content)

    @mapping
    def description(self, record):
        return {
            'description': self.clear_html_field(
                record.get('description_short', '')),
        }

    @mapping
    def active(self, record):
        return {'always_available': bool(int(record['active']))}

    @mapping
    def sale_ok(self, record):
        # if this product has combinations, we do not want to sell this
        # product, but its combinations (so sale_ok = False in that case).
        return {'sale_ok': True}

    @mapping
    def purchase_ok(self, record):
        return {'purchase_ok': True}

    @mapping
    def categ_id(self, record):
        if not int(record['id_category_default']):
            return
        category_id = self.binder_for(
            'prestashop.product.category').to_openerp(
                record['id_category_default'], unwrap=True)

        if category_id is not None:
            return {'categ_id': category_id}

        categories = record['associations'].get('categories', {}).get(
            self.backend_record.get_version_ps_key('category'), [])
        if not isinstance(categories, list):
            categories = [categories]
        if not categories:
            return
        category_id = self.binder_for(
            'prestashop.product.category').to_openerp(
                categories[0]['id'], unwrap=True)
        return {'categ_id': category_id}

    @mapping
    def categ_ids(self, record):
        categories = record['associations'].get('categories', {}).get(
            self.backend_record.get_version_ps_key('category'), [])
        if not isinstance(categories, list):
            categories = [categories]
        product_categories = []
        for category in categories:
            category_id = self.binder_for(
                'prestashop.product.category').to_openerp(
                    category['id'], unwrap=True)
            product_categories.append(category_id)

        return {'categ_ids': [(6, 0, product_categories)]}

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}

    @mapping
    def company_id(self, record):
        return {'company_id': self.backend_record.company_id.id}

    @mapping
    def ean13(self, record):
        if self.has_combinations(record):
            return {}
        if record['barcode'] in ['', '0']:
            return {}
        if self.env['barcode.nomenclature'].check_ean(record['ean13']):
            return {'barcode': record['ean13']}
        return {}

    def _get_tax_ids(self, record):
        # if record['id_tax_rules_group'] == '0':
        #     return {}
        tax_group = self.binder_for('prestashop.account.tax.group').to_openerp(
            record['id_tax_rules_group'], unwrap=True, browse=True)
        return tax_group.tax_ids

    @mapping
    def taxes_id(self, record):
        taxes = self._get_tax_ids(record)
        return {'taxes_id': [(6, 0, taxes.ids)]}

    @mapping
    def type(self, record):
        # If the product has combinations, this main product is not a real
        # product. So it is set to a 'service' kind of product. Should better
        # be a 'virtual' product... but it does not exist...
        # The same if the product is a virtual one in prestashop.
        if record['type']['value'] and record['type']['value'] == 'virtual':
            return {"type": 'service'}
        return {"type": 'product'}

    @mapping
    def procure_method(self, record):
        if record['type'] == 'pack':
            return {
                'procure_method': 'make_to_order',
                'supply_method': 'produce',
            }
        return {}

    # @mapping
    # def translatable_fields(self, record):
    #     translatable_fields = [
    #         # ('name', 'name'),
    #         # ('link_rewrite', 'link_rewrite'),
    #         ('meta_title', 'meta_title'),
    #         ('meta_description', 'meta_description'),
    #         ('meta_keywords', 'meta_keywords'),
    #         # ('tags', 'tags'),
    #         # ('description_short_html', 'description_short'),
    #         # ('description_html', 'description'),
    #         # ('available_now', 'available_now'),
    #         # ('available_later', 'available_later'),
    #         # ("description_sale", "description"),
    #         # ('description', 'description_short'),
    #     ]
    #     trans = TranslationPrestashopImporter(self.connector_env)
    #     translated_fields = self.convert_languages(
    #         trans.get_record_by_lang(record.id), translatable_fields)
    #     return translated_fields


@prestashop
class TemplateAdapter(GenericAdapter):
    _model_name = 'prestashop.product.template'
    _prestashop_model = 'products'
    _export_node_name = 'product'


@prestashop
class ProductCategoryAdapter(GenericAdapter):
    _model_name = 'prestashop.product.category'
    _prestashop_model = 'categories'
    _export_node_name = 'category'


@prestashop
class ProductInventoryExport(Exporter):
    _model_name = ['prestashop.product.template']

    def get_filter(self, template):
        binder = self.binder_for()
        prestashop_id = binder.to_backend(template.id)
        return {
            'filter[id_product]': prestashop_id,
            'filter[id_product_attribute]': 0
        }

    def run(self, binding_id, fields):
        """ Export the product inventory to PrestaShop """
        template = self.env[self.model._name].browse(binding_id)
        adapter = self.unit_for(GenericAdapter, '_import_stock_available')
        filter = self.get_filter(template)
        adapter.export_quantity(filter, int(template.quantity))


class ImportInventory(models.TransientModel):
    # In actual connector version is mandatory use a model
    _name = '_import_stock_available'


@prestashop
class ProductInventoryBatchImport(DelayedBatchImport):
    _model_name = ['_import_stock_available']

    def run(self, filters=None, **kwargs):
        if filters is None:
            filters = {}
        filters['display'] = '[id_product,id_product_attribute]'
        return super(ProductInventoryBatchImport, self).run(filters, **kwargs)

    def _run_page(self, filters, **kwargs):
        records = self.backend_adapter.get(filters)
        for record in records['stock_availables']['stock_available']:
            self._import_record(record, **kwargs)
        return records['stock_availables']['stock_available']

    def _import_record(self, record, **kwargs):
        """ Delay the import of the records"""
        import_record.delay(
            self.session,
            '_import_stock_available',
            self.backend_record.id,
            record,
            **kwargs
        )


@prestashop
class ProductInventoryImport(PrestashopImportSynchronizer):
    _model_name = ['_import_stock_available']

    def _get_quantity(self, record):
        filters = {
            'filter[id_product]': record['id_product'],
            'filter[id_product_attribute]': record['id_product_attribute'],
            'display': '[quantity]',
        }
        quantities = self.backend_adapter.get(filters)
        all_qty = 0
        quantities = quantities['stock_availables']['stock_available']
        if isinstance(quantities, dict):
            quantities = [quantities]
        for quantity in quantities:
            all_qty += int(quantity['quantity'])
        return all_qty

    def _get_template(self, record):
        if record['id_product_attribute'] == '0':
            binder = self.binder_for('prestashop.product.template')
            return binder.to_openerp(record['id_product'], unwrap=True)
        binder = self.binder_for('prestashop.product.combination')
        return binder.to_openerp(record['id_product_attribute'], unwrap=True)

    def run(self, record):
        self._check_dependency(
            record['id_product'], 'prestashop.product.template')
        if record['id_product_attribute'] != '0':
            self._check_dependency(
                record['id_product_attribute'],
                'prestashop.product.combination')

        qty = self._get_quantity(record)
        if qty < 0:
            qty = 0
        template_id = self._get_template(record)

        vals = {
            'location_id': self.backend_record.warehouse_id.lot_stock_id.id,
            'product_id': template_id,
            'new_quantity': qty,
        }
        template_qty_id = self.session.env['stock.change.product.qty'].create(
            vals)
        template_qty_id.with_context(
            active_id=template_id).change_product_qty()


@prestashop
class ProductInventoryAdapter(GenericAdapter):
    _model_name = '_import_stock_available'
    _prestashop_model = 'stock_availables'
    _export_node_name = 'stock_available'

    def get(self, options=None):
        api = self.connect()
        return api.get(self._prestashop_model, options=options)

    def export_quantity(self, filters, quantity):
        self.export_quantity_url(
            self.backend_record.location,
            self.backend_record.webservice_key,
            filters,
            quantity
        )

        shops = self.env['prestashop.shop'].search([
            ('backend_id', '=', self.backend_record.id),
            ('default_url', '!=', False),
        ])
        for shop in shops:
            self.export_quantity_url(
                '%s/api' % shop.default_url,
                self.backend_record.webservice_key,
                filters,
                quantity
            )

    def export_quantity_url(self, url, key, filters, quantity):
        api = PrestaShopWebServiceDict(url, key)
        response = api.search(self._prestashop_model, filters)
        for stock_id in response:
            res = api.get(self._prestashop_model, stock_id)
            first_key = res.keys()[0]
            stock = res[first_key]
            stock['quantity'] = int(quantity)
            try:
                api.edit(self._prestashop_model, stock['id'], {
                    self._export_node_name: stock
                })
            except PrestaShopWebServiceError:
                pass
            except ElementTree.ParseError:
                pass


# fields which should not trigger an export of the products
# but an export of their inventory
INVENTORY_FIELDS = ('quantity',)


@on_record_write(model_names=[
    'prestashop.product.template',
    'prestashop.product.combination'
])
def prestashop_product_stock_updated(
        session, model_name, record_id, fields=None):
    if session.context.get('connector_no_export'):
        return
    inventory_fields = list(set(fields).intersection(INVENTORY_FIELDS))
    if inventory_fields:
        export_inventory.delay(session, model_name,
                               record_id, fields=inventory_fields,
                               priority=20)


@job(default_channel='root.prestashop')
def export_inventory(session, model_name, record_id, fields=None):
    """ Export the inventory configuration and quantity of a product. """
    template = session.env[model_name].browse(record_id)
    backend_id = template.backend_id.id
    env = get_environment(session, model_name, backend_id)
    inventory_exporter = env.get_connector_unit(ProductInventoryExport)
    return inventory_exporter.run(record_id, fields)


@job(default_channel='root.prestashop')
def import_inventory(session, backend_id):
    env = get_environment(session, '_import_stock_available', backend_id)
    inventory_importer = env.get_connector_unit(ProductInventoryBatchImport)
    return inventory_importer.run()
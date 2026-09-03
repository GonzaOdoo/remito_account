from odoo import api, fields, models, _
from odoo.exceptions import UserError


class L10nArRemito(models.Model):
    _name = "l10n_ar.remito"
    _description = "Remito Argentino"
    _order = "id desc"

    # === IDENTIFICACIÓN === #

    name = fields.Char(
        string="N.º de Remito",
        required=True,
        copy=False,
        readonly=True,
        default="/",
    )

    # === RELACIONES === #

    invoice_id = fields.Many2one(
        comodel_name="account.move",
        string="Factura",
        copy=False,
        readonly=True,
        index=True,
    )

    picking_ids = fields.Many2many(
        comodel_name="stock.picking",
        relation="l10n_ar_remito_picking_rel",
        column1="remito_id",
        column2="picking_id",
        string="Entregas",
        copy=False,
        readonly=True,
    )

    sale_order_ids = fields.Many2many(
        comodel_name="sale.order",
        string="Órdenes de venta",
        compute="_compute_sale_order_ids",
        readonly=True,
    )

    # === CLIENTE / COMPAÑÍA === #

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Cliente",
        compute="_compute_partner_id",
        store=True,
        readonly=True,
        index=True,
    )

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        readonly=True,
        index=True,
    )

    # === DATOS DEL DOCUMENTO ARGENTINO === #

    l10n_ar_document_type_id = fields.Many2one(
        comodel_name="l10n_latam.document.type",
        string="Tipo de documento",
        readonly=True,
        copy=False,
    )

    l10n_ar_cai_authorization_code = fields.Char(
        string="CAI",
        readonly=True,
        copy=False,
    )

    l10n_ar_cai_expiration_date = fields.Date(
        string="Vencimiento del CAI",
        readonly=True,
        copy=False,
    )

    l10n_ar_sequence_number_start = fields.Char(
        string="Secuencia desde",
        readonly=True,
        copy=False,
    )

    l10n_ar_sequence_number_end = fields.Char(
        string="Secuencia hasta",
        readonly=True,
        copy=False,
    )

    l10n_ar_cai_data = fields.Json(
        string="Datos del CAI",
        copy=False,
        readonly=True,
    )

    # === MÉTODOS COMPUTADOS === #

    @api.depends("invoice_id")
    def _compute_partner_id(self):
        for remito in self:
            remito.partner_id = (
                remito.invoice_id.partner_id.commercial_partner_id
                if remito.invoice_id
                else False
            )

    @api.depends("picking_ids")
    def _compute_sale_order_ids(self):
        for remito in self:
            remito.sale_order_ids = remito.picking_ids.mapped(
                "move_ids.sale_line_id.order_id"
            )

    # === MÉTODOS DE NEGOCIO === #

    def _get_invoice_pickings(self):
        """Devuelve las entregas de clientes realizadas relacionadas con la factura."""
        self.ensure_one()

        if not self.invoice_id:
            return self.env["stock.picking"]

        return (
            self.invoice_id.invoice_line_ids
            .mapped("sale_line_ids.move_ids.picking_id")
            .filtered(
                lambda p:
                    p.state == "done"
                    and p.location_dest_id.usage == "customer"
                    and p.picking_type_id.code == "outgoing"
            )
        )

    def _get_picking_type(self, pickings):
        """Devuelve el tipo de operación utilizado para configurar el Remito."""
        picking_types = pickings.mapped("picking_type_id")

        if not picking_types:
            raise UserError(_(
                "No se encontró ninguna operación de entrega para esta factura."
            ))

        if len(picking_types) > 1:
            raise UserError(_(
                "Las entregas relacionadas con esta factura pertenecen a "
                "diferentes tipos de operación. No pueden incluirse en el "
                "mismo Remito."
            ))

        return picking_types

    def _generate_delivery_guide_number(self, picking_type):
        """Genera el número de Remito utilizando el CAI configurado."""

        if not picking_type.l10n_ar_document_type_id:
            raise UserError(_(
                "El tipo de operación '%s' no tiene configurado un tipo de "
                "documento para Remitos.",
                picking_type.display_name,
            ))

        if not picking_type.l10n_ar_sequence_id:
            raise UserError(_(
                "El tipo de operación '%s' no tiene configurada una secuencia "
                "para Remitos.",
                picking_type.display_name,
            ))

        if not picking_type.l10n_ar_sequence_number_start:
            raise UserError(_(
                "El tipo de operación '%s' no tiene configurado el inicio "
                "de la secuencia del CAI.",
                picking_type.display_name,
            ))

        if not picking_type.l10n_ar_sequence_number_end:
            raise UserError(_(
                "El tipo de operación '%s' no tiene configurado el final "
                "de la secuencia del CAI.",
                picking_type.display_name,
            ))

        new_sequence_number = picking_type.l10n_ar_next_delivery_number

        if not (
            int(picking_type.l10n_ar_sequence_number_start)
            <= new_sequence_number
            <= int(picking_type.l10n_ar_sequence_number_end)
        ):
            raise UserError(_(
                "El número de Remito excede el rango especificado en el CAI. "
                "Actualice el rango o utilice otro CAI con un rango diferente."
            ))

        delivery_guide_number = (
            picking_type.l10n_ar_sequence_id.next_by_id()
        )

        return delivery_guide_number

    def action_generate(self):
        """Genera el Remito."""

        for remito in self:
            if remito.name != "/":
                continue

            if not remito.invoice_id:
                raise UserError(_(
                    "El Remito no tiene una factura asociada."
                ))

            pickings = remito._get_invoice_pickings()

            if not pickings:
                raise UserError(_(
                    "No existen entregas de clientes realizadas relacionadas "
                    "con esta factura."
                ))

            picking_type = remito._get_picking_type(pickings)

            delivery_guide_number = (
                remito._generate_delivery_guide_number(picking_type)
            )

            remito.write({
                "name": delivery_guide_number,
                "picking_ids": [(6, 0, pickings.ids)],
                "l10n_ar_document_type_id": (
                    picking_type.l10n_ar_document_type_id.id
                ),
                "l10n_ar_cai_authorization_code": (
                    picking_type.l10n_ar_cai_authorization_code
                ),
                "l10n_ar_cai_expiration_date": (
                    picking_type.l10n_ar_cai_expiration_date
                ),
                "l10n_ar_sequence_number_start": (
                    picking_type.l10n_ar_sequence_number_start
                ),
                "l10n_ar_sequence_number_end": (
                    picking_type.l10n_ar_sequence_number_end
                ),
                "l10n_ar_cai_data": {
                    "document_type_id": (
                        picking_type.l10n_ar_document_type_id.id
                    ),
                    "cai_authorization_code": (
                        picking_type.l10n_ar_cai_authorization_code
                    ),
                    "cai_expiration_date": (
                        picking_type.l10n_ar_cai_expiration_date.strftime(
                            "%Y-%m-%d"
                        )
                        if picking_type.l10n_ar_cai_expiration_date
                        else False
                    ),
                    "sequence_number_start": (
                        picking_type.l10n_ar_sequence_number_start
                    ),
                    "sequence_number_end": (
                        picking_type.l10n_ar_sequence_number_end
                    ),
                },
            })
            # Verificar si quedan pocos Remitos disponibles.
            picking_type._check_delivery_guides_remaining()
        return True

    def _get_remito_aggregated_lines(self):
        """Agrupa las líneas entregadas por producto final (kit o simple),
        considerando únicamente la cantidad facturada en la factura asociada.
        """
        self.ensure_one()
    
        result = []
        processed = self.env["stock.move.line"]
    
        # Cantidad facturada por cada línea de venta.
        #
        # Una misma sale.order.line puede aparecer relacionada a más de una
        # línea de factura, por lo que acumulamos las cantidades.
        invoiced_qty_by_sale_line = {}
    
        for invoice_line in self.invoice_id.invoice_line_ids:
            for sale_line in invoice_line.sale_line_ids:
                invoiced_qty_by_sale_line[sale_line.id] = (
                    invoiced_qty_by_sale_line.get(sale_line.id, 0.0)
                    + invoice_line.quantity
                )
    
        # Todas las líneas entregadas relacionadas con la factura.
        move_lines = self.picking_ids.mapped("move_line_ids").filtered(
            lambda l:
                l.quantity
                and l.move_id.sale_line_id
                and l.move_id.sale_line_id.id in invoiced_qty_by_sale_line
        )
    
        # ============================================================
        # KITS
        # ============================================================
    
        kit_moves = move_lines.filtered(
            lambda l: l.move_id.bom_line_id
        )
    
        kit_sale_lines = kit_moves.mapped(
            "move_id.sale_line_id"
        )
    
        for sale_line in kit_sale_lines:
            kit_lines = kit_moves.filtered(
                lambda l:
                    l.move_id.sale_line_id == sale_line
            )
    
            invoiced_qty = invoiced_qty_by_sale_line.get(
                sale_line.id,
                0.0,
            )
    
            delivered_qty = sale_line.qty_delivered
    
            # No mostrar más cantidad de la que corresponde a esta factura.
            quantity = min(
                delivered_qty,
                invoiced_qty,
            )
    
            if not quantity:
                continue
            total_delivered_qty = sale_line.qty_delivered
            bultos = (
                sum(kit_lines.mapped("quantity"))
                * quantity
                / total_delivered_qty
                if total_delivered_qty
                else 0.0
            )
            result.append({
                "product_name": sale_line.product_id.display_name,
                "order_name": sale_line.order_id.name,
                "ordered_qty": invoiced_qty,
                "delivered_qty": quantity,
                "uom_name": sale_line.product_uom_id.name,
                "bultos": bultos,
            })
    
            processed |= kit_lines
    
        # ============================================================
        # PRODUCTOS SIMPLES
        # ============================================================
    
        remaining_lines = move_lines - processed
    
        for product in remaining_lines.mapped("product_id"):
            p_lines = remaining_lines.filtered(
                lambda l:
                    l.product_id == product
            )
    
            # Agrupamos por producto, como hacía el método original.
            sale_lines = p_lines.mapped("move_id.sale_line_id")
    
            invoiced_qty = sum(
                invoiced_qty_by_sale_line.get(
                    sale_line.id,
                    0.0,
                )
                for sale_line in sale_lines
            )
    
            delivered_qty = sum(
                p_lines.mapped("quantity")
            )
    
            quantity = min(
                delivered_qty,
                invoiced_qty,
            )
    
            if not quantity:
                continue
    
            move = p_lines[:1].move_id
    
            result.append({
                "product_name": product.display_name,
                "order_name": (
                    move.sale_line_id.order_id.name
                    if move.sale_line_id
                    else ""
                ),
                "ordered_qty": invoiced_qty,
                "delivered_qty": quantity,
                "uom_name": move.product_uom.name if move else "",
                "bultos": quantity,
            })
    
        return result
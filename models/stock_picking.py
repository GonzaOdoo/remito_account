from odoo import api, fields, models, _


class StockPickingType(models.Model):
    _inherit = ["stock.picking.type", "mail.thread", "mail.activity.mixin"]

    l10n_ar_delivery_guides_remaining = fields.Integer(
        string="Remitos disponibles",
        compute="_compute_l10n_ar_delivery_guides_remaining",
    )

    l10n_ar_delivery_guides_warning_threshold = fields.Integer(
        string="Avisar cuando queden",
        default=10,
    )

    l10n_ar_delivery_guides_warning_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="stock_picking_type_delivery_guide_warning_user_rel",
        column1="picking_type_id",
        column2="user_id",
        string="Usuarios a notificar",
        help="Usuarios que recibirán una actividad cuando queden pocos "
             "Remitos disponibles.",
    )

    @api.depends(
        "l10n_ar_sequence_number_start",
        "l10n_ar_sequence_number_end",
        "l10n_ar_next_delivery_number",
    )
    def _compute_l10n_ar_delivery_guides_remaining(self):
        for picking_type in self:
            try:
                start = int(
                    picking_type.l10n_ar_sequence_number_start or 0
                )
                end = int(
                    picking_type.l10n_ar_sequence_number_end or 0
                )
                next_number = (
                    picking_type.l10n_ar_next_delivery_number or 0
                )

                picking_type.l10n_ar_delivery_guides_remaining = max(
                    end - next_number + 1,
                    0,
                )

            except (TypeError, ValueError):
                picking_type.l10n_ar_delivery_guides_remaining = 0

    def _check_delivery_guides_remaining(self):
        self.ensure_one()
    
        remaining = self.l10n_ar_delivery_guides_remaining
        threshold = self.l10n_ar_delivery_guides_warning_threshold
    
        if remaining > threshold:
            return
    
        activity_type = self.env.ref(
            "mail.mail_activity_data_warning",
            raise_if_not_found=False,
        )
    
        if not activity_type:
            return
    
        for user in self.l10n_ar_delivery_guides_warning_user_ids:
            existing_activity = self.env["mail.activity"].search([
                ("res_model", "=", "stock.picking.type"),
                ("res_id", "=", self.id),
                ("activity_type_id", "=", activity_type.id),
                ("user_id", "=", user.id),
            ], limit=1)
    
            if existing_activity:
                continue
    
            self.activity_schedule(
                activity_type_id=activity_type.id,
                user_id=user.id,
                summary=_("Pocos Remitos disponibles"),
                note=_(
                    "Quedan solamente %s Remitos disponibles "
                    "para el tipo de operación '%s'. "
                    "El umbral configurado es de %s."
                ) % (
                    remaining,
                    self.display_name,
                    threshold,
                ),
            )



class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _get_remito_aggregated_lines(self):
        """Agrupa las líneas entregadas por producto final (kit o simple),
        sumando los bultos/componentes en una sola columna."""
        self.ensure_one()
        result = []
        move_lines = self.move_line_ids.filtered(lambda l: l.quantity)
        processed = self.env['stock.move.line']
    
        kit_moves = move_lines.filtered(lambda l: l.move_id.bom_line_id)
        kit_sale_lines = kit_moves.mapped('move_id.sale_line_id')
        
        for sale_line in kit_sale_lines:
            kit_lines = kit_moves.filtered(
                lambda l: l.move_id.sale_line_id == sale_line
            )
            kit_product = sale_line.product_id
        
            result.append({
                'product_name': kit_product.display_name,
                'order_name': sale_line.order_id.name,
                'ordered_qty': sale_line.product_uom_qty,
                'delivered_qty': sale_line.qty_delivered,
                'uom_name': sale_line.product_uom_id.name,
                'bultos': sum(kit_lines.mapped('quantity')),
            })
            processed |= kit_lines

        # Productos simples (sin BOM tipo kit)
        for product in (move_lines - processed).mapped('product_id'):
            p_lines = (move_lines - processed).filtered(lambda l: l.product_id == product)
            move = p_lines[:1].move_id
            result.append({
                'product_name': product.display_name,
                'order_name': move.sale_line_id.order_id.name if move.sale_line_id else '',
                'ordered_qty': sum(p_lines.mapped('move_id.product_uom_qty')),
                'delivered_qty': sum(p_lines.mapped('quantity')),
                'uom_name': move.product_uom.name if move else '',
                'bultos': sum(p_lines.mapped('quantity')),
            })
        return result
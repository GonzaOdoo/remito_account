from odoo import fields, models, _, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)
class AccountMove(models.Model):
    _inherit = "account.move"

    l10n_ar_remito_ids = fields.One2many(
        comodel_name="l10n_ar.remito",
        inverse_name="invoice_id",
        string="Delivery Guides",
        readonly=True,
    )

    l10n_ar_remito_count = fields.Integer(
        compute="_compute_l10n_ar_remito_count",
    )
    
    l10n_ar_remito_warning = fields.Boolean(
        string="Advertencia de Remitos",
        compute="_compute_l10n_ar_remito_warning",
    )

    l10n_ar_remito_warning_message = fields.Char(
        string="Mensaje de advertencia de Remitos",
        compute="_compute_l10n_ar_remito_warning",
    )

    @api.depends(
        "invoice_line_ids.sale_line_ids.move_ids.picking_id",
        "invoice_line_ids.sale_line_ids.move_ids.picking_id.state",
        "invoice_line_ids.sale_line_ids.move_ids.picking_id.location_dest_id",
        "invoice_line_ids.sale_line_ids.move_ids.picking_id.picking_type_id",
        "invoice_line_ids.sale_line_ids.move_ids.picking_id.picking_type_id.l10n_ar_delivery_guides_remaining",
        "invoice_line_ids.sale_line_ids.move_ids.picking_id.picking_type_id.l10n_ar_delivery_guides_warning_threshold",
    )
    def _compute_l10n_ar_remito_warning(self):
        for move in self:
            move.l10n_ar_remito_warning = False
            move.l10n_ar_remito_warning_message = False
    
            if move.move_type not in ("out_invoice", "out_refund"):
                continue
    
            pickings = (
                move.l10n_ar_remito_ids[:1].picking_ids
                if move.l10n_ar_remito_ids
                else (
                    move.invoice_line_ids
                    .mapped("sale_line_ids.move_ids.picking_id")
                    .filtered(
                        lambda p:
                            p.state == "done"
                            and p.location_dest_id.usage == "customer"
                            and p.picking_type_id.code == "outgoing"
                    )
                )
            )
    
            picking_type = pickings[:1].picking_type_id
    
            if not picking_type:
                continue
    
            if (
                picking_type.l10n_ar_delivery_guides_remaining
                <= picking_type.l10n_ar_delivery_guides_warning_threshold
            ):
                move.l10n_ar_remito_warning = True
    
                move.l10n_ar_remito_warning_message = _(
                    "Atención: quedan solamente %s Remitos disponibles "
                    "para '%s'.",
                    picking_type.l10n_ar_delivery_guides_remaining,
                    picking_type.display_name,
                )

    def _compute_l10n_ar_remito_count(self):
        for move in self:
            move.l10n_ar_remito_count = len(move.l10n_ar_remito_ids)

    def l10n_ar_action_create_delivery_guides(self):
        self.ensure_one()

        if self.move_type not in ("out_invoice", "out_refund"):
            raise UserError(_(
                "A delivery guide can only be generated from a "
                "customer invoice or customer credit note."
            ))

        if self.l10n_ar_remito_ids:
            raise UserError(_(
                "A delivery guide has already been generated "
                "for this invoice."
            ))

        remito = self.env["l10n_ar.remito"].create({
            "invoice_id": self.id,
        })

        remito.action_generate()

    def l10n_ar_action_print_delivery_guides(self):
        self.ensure_one()

        report = self.env.ref(
            "report_assistance.action_delivery_guide_report_pdf"
        )

        return report.report_action(self.l10n_ar_remito_ids)
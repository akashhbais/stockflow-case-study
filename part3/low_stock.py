from flask import jsonify
from sqlalchemy import text
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

RECENT_SALES_DAYS = 30


@app.route('/api/companies/<int:company_id>/alerts/low-stock', methods=['GET'])
def get_low_stock_alerts(company_id):
    # check company exists
    company = Company.query.get_or_404(company_id)

    cutoff = datetime.utcnow() - timedelta(days=RECENT_SALES_DAYS)

    # single query using a CTE to avoid N+1 problem.
    # the CTE aggregates sales for the last 30 days per inventory row,
    # then the main query joins everything and filters for low stock.
    query = text('''
        WITH recent_sales AS (
            SELECT
                ih.inventory_id,
                SUM(ABS(ih.quantity_delta)) AS units_sold,
                SUM(ABS(ih.quantity_delta))::FLOAT / :days AS avg_daily_sales
            FROM inventory_history ih
            WHERE ih.change_type = 'sale'
              AND ih.created_at  >= :cutoff
            GROUP BY ih.inventory_id
        )
        SELECT
            p.id                  AS product_id,
            p.name                AS product_name,
            p.sku,
            w.id                  AS warehouse_id,
            w.name                AS warehouse_name,
            i.quantity            AS current_stock,
            p.low_stock_threshold AS threshold,
            CASE
                WHEN rs.avg_daily_sales > 0
                THEN FLOOR(i.quantity / rs.avg_daily_sales)
                ELSE NULL
            END                   AS days_until_stockout,
            s.id                  AS supplier_id,
            s.name                AS supplier_name,
            s.contact_email       AS supplier_email
        FROM inventory i
        JOIN products       p  ON p.id  = i.product_id
        JOIN warehouses     w  ON w.id  = i.warehouse_id
        LEFT JOIN suppliers s  ON s.id  = p.supplier_id
        LEFT JOIN recent_sales rs ON rs.inventory_id = i.id
        WHERE w.company_id          = :company_id
          AND p.is_active           = TRUE
          AND i.quantity            < p.low_stock_threshold
          AND rs.units_sold         IS NOT NULL
        ORDER BY days_until_stockout ASC NULLS LAST
    ''')

    try:
        rows = db.session.execute(query, {
            'company_id': company_id,
            'cutoff':     cutoff,
            'days':       RECENT_SALES_DAYS,
        }).fetchall()

    except Exception:
        logger.exception('Error fetching low stock alerts for company %s', company_id)
        return jsonify({'error': 'Internal server error'}), 500

    alerts = []
    for row in rows:
        alerts.append({
            'product_id':          row.product_id,
            'product_name':        row.product_name,
            'sku':                 row.sku,
            'warehouse_id':        row.warehouse_id,
            'warehouse_name':      row.warehouse_name,
            'current_stock':       row.current_stock,
            'threshold':           row.threshold,
            'days_until_stockout': int(row.days_until_stockout) if row.days_until_stockout is not None else None,
            'supplier': {
                'id':            row.supplier_id,
                'name':          row.supplier_name,
                'contact_email': row.supplier_email,
            } if row.supplier_id else None,
        })

    return jsonify({'alerts': alerts, 'total_alerts': len(alerts)}), 200

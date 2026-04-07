from flask import request, jsonify
from sqlalchemy.exc import IntegrityError
from decimal import Decimal, InvalidOperation
import logging

logger = logging.getLogger(__name__)


@app.route('/api/products', methods=['POST'])
def create_product():
    data = request.get_json(silent=True)

    # basic check that body exists and is valid json
    if not data:
        return jsonify({'error': 'Request body must be valid JSON'}), 400

    # check all required fields are present
    required_fields = ['name', 'sku', 'price', 'warehouse_id', 'initial_quantity']
    missing = [f for f in required_fields if f not in data]
    if missing:
        return jsonify({'error': f'Missing fields: {missing}'}), 400

    # validate price
    try:
        price = Decimal(str(data['price']))
        if price < 0:
            raise ValueError('Price cannot be negative')
    except (InvalidOperation, ValueError) as e:
        return jsonify({'error': str(e)}), 400

    # validate quantity
    try:
        initial_quantity = int(data['initial_quantity'])
        if initial_quantity < 0:
            raise ValueError('Quantity cannot be negative')
    except (ValueError, TypeError):
        return jsonify({'error': 'initial_quantity must be a valid integer'}), 400

    # check warehouse actually exists before doing anything
    warehouse = Warehouse.query.get(data['warehouse_id'])
    if not warehouse:
        return jsonify({'error': 'Warehouse not found'}), 404

    # single transaction, both rows saved together or neither
    try:
        product = Product(
            name=data['name'].strip(),
            sku=data['sku'].strip().upper(),
            price=price,
        )
        db.session.add(product)
        db.session.flush()  # gets product.id without committing yet

        inventory = Inventory(
            product_id=product.id,
            warehouse_id=data['warehouse_id'],
            quantity=initial_quantity,
        )
        db.session.add(inventory)
        db.session.commit()  # one commit, both rows saved

        logger.info('Product created: sku=%s id=%s', product.sku, product.id)
        return jsonify({'message': 'Product created', 'product_id': product.id}), 201

    except IntegrityError as e:
        db.session.rollback()
        if 'sku' in str(e.orig).lower():
            return jsonify({'error': 'A product with this SKU already exists'}), 409
        return jsonify({'error': 'Database error'}), 400

    except Exception:
        db.session.rollback()
        logger.exception('Unexpected error while creating product')
        return jsonify({'error': 'Internal server error'}), 500

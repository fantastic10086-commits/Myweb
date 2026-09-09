"""Prebuild cached product thumbnails without changing product originals."""

import os

from app import app, _ensure_product_thumbnail
from models import Product


def main():
    generated = 0
    skipped = 0
    with app.app_context():
        products = Product.query.filter(Product.image.isnot(None), Product.image != '').all()
        for product in products:
            source_path = os.path.join(app.config['UPLOAD_DIR'], product.image)
            if not os.path.isfile(source_path):
                skipped += 1
                continue
            result_path = _ensure_product_thumbnail(product.image, source_path)
            if result_path != source_path:
                generated += 1
            else:
                skipped += 1
    print(f'thumbnails={generated} skipped={skipped}')


if __name__ == '__main__':
    main()

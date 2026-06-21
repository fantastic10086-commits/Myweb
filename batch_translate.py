#!/usr/bin/env python3
"""Batch translate — single text, robust, no retries."""
import os, sys, time, json, ssl, urllib.request, urllib.parse

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

from app import app, db
from models import Product

ctx = ssl._create_unverified_context()

def translate(text):
    try:
        url = 'https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q=' + urllib.parse.quote(text[:200])
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=6, context=ctx) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        if data and data[0] and isinstance(data[0], list):
            result = ''.join([s[0] for s in data[0] if s and s[0]])
            if result and len(result) < 200:
                return result
    except Exception:
        pass
    return ''

with app.app_context():
    products = Product.query.filter(
        (Product.chinese_name == '') | (Product.chinese_name == None)
    ).all()
    products = [p for p in products if p.name and p.name.strip()]
    total = len(products)
    done = 0
    errs = 0
    committed = 0

    for p in products:
        cn = translate(p.name.strip())
        p.chinese_name = cn
        if not cn:
            errs += 1
        done += 1

        if done % 20 == 0:
            try:
                db.session.commit()
                committed = done
            except Exception:
                db.session.rollback()
            print(f'{done}/{total} ({100*done//total}%)  Err:{errs}')
            time.sleep(0.3)

    if committed < done:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            db.session.commit()

    print(f'\nDONE: {done}/{total} translated, {errs} errors')

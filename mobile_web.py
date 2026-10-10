"""Mobile web shell; business data stays behind the existing authenticated API."""
from flask import render_template, jsonify, send_from_directory
from pathlib import Path
import hashlib


def register_mobile_web(app):
    @app.get('/mobile/')
    def mobile_home():
        assets = Path(app.static_folder) / 'mobile'
        version = hashlib.sha256((assets / 'mobile.js').read_bytes() + (assets / 'mobile.css').read_bytes()).hexdigest()[:16]
        response = app.make_response(render_template('mobile.html', mobile_asset_version=version))
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' blob:; connect-src 'self'; object-src 'none'; "
            "base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
        return response

    @app.get('/mobile/sw.js')
    def mobile_service_worker():
        response = send_from_directory(Path(app.static_folder) / 'mobile', 'sw.js', mimetype='application/javascript')
        response.headers['Cache-Control'] = 'no-cache'
        return response

    @app.get('/mobile/manifest.webmanifest')
    def mobile_manifest():
        response = jsonify(name='PI Manager · 订单照片', short_name='订单照片',
            id='/mobile/', start_url='/mobile/', scope='/mobile/', display='standalone',
            lang='zh-CN', background_color='#f4f6fa', theme_color='#193c60',
            icons=[{'src':'/static/mobile/icon.png','sizes':'1024x1024','type':'image/png','purpose':'any'}])
        response.mimetype = 'application/manifest+json'
        return response

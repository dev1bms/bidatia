"""Masking helpers — applied BEFORE anything reaches result_json.

Raw sample values live only in the Celery task's memory during duplicate
clustering; what gets stored/displayed always passes through here.
See docs/data_risk_profiler/PRIVACY_MODEL.md for the contract.
"""
import re


def mask_email(value):
    value = (value or '').strip()
    if '@' not in value:
        return mask_text(value)
    local, _, domain = value.partition('@')
    tld = domain.rsplit('.', 1)[-1] if '.' in domain else ''
    masked_domain = (domain[:1] + '***' + ('.' + tld if tld else ''))
    return (local[:1] or '*') + '***@' + masked_domain


def mask_text(value):
    """Names, company names, free text: first 2 characters survive."""
    value = ' '.join(str(value or '').split())
    if not value:
        return ''
    return value[:2] + '***'


def mask_vat(value):
    value = re.sub(r'[^A-Za-z0-9]', '', str(value or '')).upper()
    if len(value) <= 4:
        return '***'
    return value[:2] + '***' + value[-2:]


def mask_phone(value):
    digits = re.sub(r'\D', '', str(value or ''))
    return '***' + digits[-2:] if len(digits) >= 2 else '***'


def mask_code(value):
    """Product internal references / barcodes."""
    value = str(value or '').strip()
    if len(value) <= 4:
        return '***'
    return value[:2] + '***' + value[-2:]

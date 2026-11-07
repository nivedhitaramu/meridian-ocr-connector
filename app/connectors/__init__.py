"""Outgoing connectors (#41): how a result is shaped for a customer's system.

A connector is a payload format on a webhook endpoint. Every format reuses the same delivery machinery: one row per
endpoint and job, signing, retries, and the checks that keep requests off private networks. A new ERP, WMS or TMS
target needs only a new entry in `formats.FORMATS`.
"""

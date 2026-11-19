# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0.html)
{
    "name": "RLQ: static folders listed before the workers start",
    "summary": "Server-wide module: the main process of Odoo lists the static folders of every module once, before it forks its workers",
    "version": "18.0.1.0.0",
    "category": "Hidden/Tools",
    "author": "Rencontres Linux au Quebec",
    "website": "https://github.com/Rencontres-Linux-au-Quebec/rlq-admin-tools",
    "license": "AGPL-3",
    "depends": ["base"],
    "data": [],
    "post_load": "post_load",
    "installable": True,
    "auto_install": False,
    "application": False,
}

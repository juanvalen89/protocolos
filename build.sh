#!/usr/bin/env bash
# Script de build para Render (se ejecuta en cada deploy).
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
# Carga MALBEC (protocolo, tarifas, historial) y el usuario inicial SOLO si la
# base está vacía. Nunca pisa ni borra datos existentes.
python manage.py datos_iniciales

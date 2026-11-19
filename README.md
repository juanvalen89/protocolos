# Protocolos de investigación · Centro de Ojos Loria

Aplicación web privada para llevar los protocolos de investigación del sitio:
la coordinadora carga **quién hizo cada procedimiento** en cada visita y el
sistema calcula solo lo demás: lo que le corresponde a cada médico, lo que hay
que cobrarle al sponsor, lo que está facturado y cobrado, y el reparto.

Primer protocolo cargado: **MALBEC (MK-8748-002)**, con su historial hasta el 18/11/2026.

## Roles

- **Coordinadora de estudios**: pacientes (solo el código de sujeto), visitas y
  quién hizo cada procedimiento. **No ve ningún importe** ni entra a las
  pantallas de dinero (verificado en el servidor: `estudios/tests.py`).
- **Dirección**: todo. Tablero, médicos, cobros al sponsor, reparto y Configuración.

Los usuarios se crean en Configuración → Usuarios. Nacen con una clave genérica
y el sistema obliga a cambiarla en el primer ingreso.

## Cómo calcula

- **Médicos**: cada procedimiento cargado toma la tarifa del protocolo
  (Configuración → Protocolos). Saldo = lo que le corresponde − lo pagado.
  Los pagos se guardan en USD y, si se paga en pesos, con el dólar BNA vendedor del día.
- **Cobros al sponsor**: cada visita completa vale el precio del presupuesto;
  aparte van el viático por visita y los condicionales (OCTA, FAF). Una visita
  está *sin facturar* hasta que entra en una factura, y *cobrada* cuando la
  factura se marca cobrada. Las cartas de pago trimestrales (payment letters)
  se cargan en Configuración.
- **Reparto** (regla fija para todos los estudios, sobre lo cobrado):
  neto = cobrado − gastos − pagos a médicos; del neto sale primero el 10% de
  quien trae el estudio y el resto se divide 50 / 40 / 10. A cada uno se le
  devuelve lo que adelantó. Los porcentajes están en Configuración → Socios.
- **Avisos**: visitas del cronograma sin cargar, facturas vencidas y facturas
  con un Request ID distinto al de su carta.

## Sumar otro protocolo

Configuración → Protocolos: cargar el protocolo con sus procedimientos y
tarifas, y después las visitas del cronograma con el precio del presupuesto y
los procedimientos esperados. Con más de un protocolo activo aparece un
selector en el encabezado.

## Correr en desarrollo

```bash
pip install -r requirements.txt
export DJANGO_DEBUG=1
python manage.py migrate
python manage.py datos_iniciales   # MALBEC + usuario jvalenzuela (clave genérica)
python manage.py runserver
python manage.py test
```

## Despliegue en Render

1. En render.com: New → Blueprint → elegir este repositorio (usa `render.yaml`).
2. El build corre las migraciones y `datos_iniciales`, que carga MALBEC y el
   usuario inicial **solo si la base está vacía** (nunca pisa datos).
3. Si el nombre del servicio cambia, ajustar `DJANGO_ALLOWED_HOSTS`.

Misma base técnica que la app de presupuestos: Django, PostgreSQL en Render,
bloqueo de cuenta tras 5 intentos fallidos, HTTPS forzado y secretos por
variables de entorno.
